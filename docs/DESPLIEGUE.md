# Despliegue

Cómo publicar el dashboard en internet con acceso privado.

## Qué opción elegir

El proyecto es una app **Streamlit** (Python, servidor siempre encendido, WebSockets)
que guarda todo en **archivos** dentro de `cache/` (ADR-006): histórico de ESPN
(~60 MB), modelo del día, ledger y líneas de Betano. Eso decide la plataforma.

| Opción | ¿Sirve? | Motivo |
|---|:---:|---|
| **Vercel** | ✗ | Funciones serverless efímeras: sin disco persistente ni procesos largos. Streamlit no corre. |
| **Firebase** | ✗ | Hosting es estático; App Hosting es para Next.js/Angular. Habría que montar Cloud Run aparte y mover los datos a otro sitio. |
| **Supabase** | ✗ como host | Es base de datos + auth + storage; no ejecuta apps Python. Solo tendría sentido migrando el ledger a Postgres, que hoy no hace falta. |
| Streamlit Community Cloud | ✗ | Gratis, pero el disco se borra en cada reinicio: se perdería el ledger. |
| **VPS** (Hetzner, DigitalOcean, Contabo…) | ✓ | Disco persistente, proceso largo y WebSockets. `cache/` se queda tal cual. 4–6 USD/mes. |

**Elegido: VPS con Docker Compose**, Caddy delante para HTTPS automático y login
de Google con `st.login`. Un VPS de 2 vCPU y 4 GB (p. ej. Hetzner CX22) basta
para entrenar el modelo del día.

## Arquitectura

```
Internet ──443──▶ Caddy (TLS, cabeceras de seguridad) ──▶ app:8501 (Streamlit)
                                                         │
                                         login OIDC ◀────┤  st.login → Google
                                                         └─ ./cache (volumen)
```

- Solo Caddy publica puertos (80 y 443). Streamlit no es accesible directamente.
- El login lo hace Google (contraseña y 2FA nunca pasan por la app). Después,
  la app compara el correo con la lista `[acceso] correos`: cualquier otra cuenta
  de Google ve "no tiene acceso".
- Si falta la configuración de login, el dashboard **no arranca** (falla cerrado).

## Pasos

### 1. Credenciales de Google (una vez)

1. [Google Cloud Console](https://console.cloud.google.com/) → crea un proyecto.
2. *APIs y servicios → Pantalla de consentimiento de OAuth*: tipo **Externo**,
   añade tu correo como usuario de prueba.
3. *Credenciales → Crear credenciales → ID de cliente de OAuth → Aplicación web*.
   - URI de redireccionamiento autorizado: `https://nba.tu-dominio.com/oauth2callback`
   - (Para probar en local, añade también `http://localhost:8501/oauth2callback`.)
4. Guarda el *Client ID* y el *Client secret*.

### 2. Servidor

```bash
# En el VPS (Ubuntu 24.04), como usuario con sudo
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # cierra sesión y vuelve a entrar

# Cortafuegos: solo SSH y web
sudo ufw allow OpenSSH && sudo ufw allow 80,443/tcp && sudo ufw allow 443/udp && sudo ufw enable
```

Recomendado: acceso SSH solo con llave (`PasswordAuthentication no` en
`/etc/ssh/sshd_config`) y `sudo apt install unattended-upgrades`.

Apunta un registro DNS **A** de `nba.tu-dominio.com` a la IP del VPS.

### 3. Aplicación

```bash
git clone https://github.com/SantiagoRicaurte06/N.B.A_Predictor.git
cd N.B.A_Predictor

cp .streamlit/secrets.toml.example .streamlit/secrets.toml
nano .streamlit/secrets.toml      # redirect_uri, cookie_secret, client_id, client_secret, correos
chmod 600 .streamlit/secrets.toml

mkdir -p cache && sudo chown 1000:1000 cache   # el contenedor corre como uid 1000

echo "DOMINIO=nba.tu-dominio.com" > .env
docker compose build
docker compose run --rm app python -m nba_predictor.datos.espn   # histórico, una vez
docker compose up -d
```

Abre `https://nba.tu-dominio.com`: Caddy obtiene el certificado solo y aparece
el botón *Iniciar sesión con Google*.

Si ya tienes un `cache/` en tu equipo con ledger y líneas, cópialo antes de
arrancar: `scp -r cache/ usuario@vps:~/N.B.A_Predictor/`.

### 4. Actualizar y respaldar

```bash
./deploy/actualizar.sh                          # git pull de main + rebuild

# Respaldo diario del ledger y las líneas (crontab -e)
0 4 * * * tar czf ~/respaldo-$(date +\%F).tgz -C ~/N.B.A_Predictor/cache ledger.csv lineas_betano.csv
```

## Uso en local

```bash
# Con login: crea .streamlit/secrets.toml con redirect_uri http://localhost:8501/oauth2callback
streamlit run app/dashboard.py

# Sin login (solo en tu equipo, nunca en el servidor)
NBA_SIN_LOGIN=1 streamlit run app/dashboard.py
```

## Seguridad: qué cubre y qué no

| Medida | Dónde |
|---|---|
| HTTPS obligatorio y HSTS | Caddy |
| Login OIDC con Google (2FA de tu cuenta) | `st.login`, `app/acceso.py` |
| Lista de correos permitidos, correo verificado | `app/acceso.py` |
| Falla cerrado si falta la configuración | `app/acceso.py` |
| Cookie de sesión firmada (`cookie_secret`) | Streamlit |
| Protección XSRF | Streamlit (activa por defecto) |
| Streamlit sin puerto público, contenedor sin root | `docker-compose.yml`, `Dockerfile` |
| Secretos fuera del repositorio | `.gitignore`, montado de solo lectura |

No cubre: límite de intentos en la pantalla de login (lo hace Google), ni
auditoría de accesos. Si algún día hay varios usuarios con datos separados, el
ledger debería pasar a una base de datos (reabrir ADR-006); ahí Supabase sí encaja.
