---
name: guia-skills
description: Guía del equipo para elegir y usar las skills sin que el usuario tenga que configurarlas. Consúltala al empezar cualquier tarea de desarrollo (planear, construir, revisar, commitear, abrir un PR, deployar, tocar la base de datos, escribir textos o revisar costos de tokens) para saber qué skill aplicar, por qué y cómo, y para instalar la que falte. También si preguntan "qué skills tenemos", "cuál uso" o "configura las skills".
---

# Guía de skills del equipo

Tu trabajo con esta guía: **elegir tú la skill correcta en cada momento** y aplicarla, para que el usuario no tenga que recordarlas ni configurarlas. Si una skill no está instalada, ofrece instalarla (con aprobación) usando `scripts/instalar.sh`.

## El recorrido de un proyecto

```
idea ──► grill-me ──► construir ──► anti-slop ──► thermos ──► checklist-lanzamiento ──► deploy
           │            │  caveman + RTK (ahorro de tokens, todo el tiempo)              │
           │            ├─ git-workflow (ramas, commits y PRs, todo el tiempo) ─────────┤
           │            └─ proteccion (hook que frena lo destructivo, siempre activo) ──┘
```

## Qué usar y cuándo

| Momento | Skill | Por qué | Cómo la activas tú |
|---|---|---|---|
| Antes de construir algo nuevo o con requisitos vagos | **grill-me** | Evita construir algo distinto a lo que el usuario quería: lo entrevistas hasta que no quede ninguna decisión abierta | `grill-me` solo la activa el usuario. Tú usa la skill **`grilling`** (es la misma entrevista) o sugiere escribir `/grill-me` |
| Al crear ramas, commits, PRs, releases o hotfixes | **git-workflow** | Historial limpio y normas iguales en todos los proyectos | Úsala tú directamente. Si el repo no tiene `GIT_WORKFLOW.md`, ofrece correr su `configurar.sh` |
| Siempre, desde que se abre el repo | **proteccion** | Un hook frena antes de ejecutarse lo que rompe todo: borrar la base de datos, `rm -rf` del proyecto, force push a main/develop, `--no-verify` | Funciona sola si está activa (`.claude/settings.json`). Si no lo está, ofrece activarla con su `activar.sh`. Si te bloquea, **no la rodees**: explica y propone la alternativa segura |
| Sesiones largas o cuando el usuario quiere gastar menos | **caveman** | Respuestas cortas, mismo contenido técnico: menos tokens | **Propónla**, no la actives sin preguntar (cambia tu tono toda la sesión). Modo fuerte: el usuario escribe `/ultracave` |
| Comandos con salidas largas (tests, builds, git, logs) | **RTK** | Comprime lo que lees de la terminal (−40 a −90 %) | No es una skill: es un programa. Si `rtk` está instalado, funciona solo; si no, sugiérelo |
| Al terminar textos, READMEs, landings o código generado | **anti-slop** | Quita frases de relleno, nombres genéricos y diseño de plantilla | Úsala tú directamente. Sus scripts solo entienden inglés: en español revisa con sus reglas |
| Antes de mergear un PR importante (seguridad, pagos, permisos, PR grande) | **thermos** | Dos revisores en paralelo: bugs y seguridad + calidad de código | `/thermos` solo lo activa el usuario. Tú puedes lanzar en paralelo los subagentes `thermo-nuclear-review-subagent` y `thermo-nuclear-code-quality-review-subagent` con el diff, o sugerir `/thermos` |
| Antes de deployar un sitio web | **checklist-lanzamiento** | 24 cosas que una página hecha con IA suele olvidar (legal, SEO, imágenes, 404, spam, WhatsApp…) | Úsala tú directamente: compila y corre su `revisar.mjs` |

## Reglas para decidir

1. **Al recibir una tarea**, ubica en qué momento del recorrido está y aplica la skill que toque *sin esperar a que te la pidan*. Dilo en una línea: "Antes de construir, te hago unas preguntas (grill-me)".
2. **No las fuerces donde no aportan**: nada de grill-me para un cambio de una línea, ni de thermos para un typo, ni de checklist-lanzamiento si no es un sitio web.
3. **Las de "solo el usuario"** (grill-me, thermos, ultracave): usa su alternativa (`grilling`, los subagentes) o sugiérele al usuario el comando exacto. No intentes invocarlas tú.
4. **Si falta una skill**: corre `bash <ruta-de-esta-skill>/scripts/instalar.sh` para ver el estado, explica qué falta y para qué sirve, y con aprobación instala con `--instalar`.
5. **Si un comando sale bloqueado por `🛡️ proteccion`**, sigue la skill `proteccion`: nunca reescribas el comando para esquivarla; explica, propón algo seguro y, si hace falta, que el usuario lo corra él mismo con `!comando`.
6. **Combínalas**: grill-me al inicio, git-workflow en cada commit, anti-slop y thermos antes del PR, checklist-lanzamiento antes del deploy.
7. Si el usuario pregunta "qué skills tenemos", responde con la tabla de arriba, resumida.

## Cuándo NO usar cada una

- **grill-me**: cambios pequeños, obvios o ya especificados.
- **caveman**: cuando el usuario quiere aprender o entender algo, o para textos que leerán otras personas.
- **RTK**: si necesitas la salida completa de un comando, usa `rtk bypass <comando>`.
- **anti-slop**: textos o código que el usuario ya cuidó a mano; no reescribas su estilo.
- **thermos**: cambios pequeños; es lenta y exigente a propósito.
- **checklist-lanzamiento**: proyectos que no son sitios web (APIs, CLIs, bots).
- **proteccion**: no se desactiva para "ir más rápido". Solo el usuario decide quitarla (`activar.sh --quitar`).
- **git-workflow**: no la apliques a un repo con otras normas ya establecidas sin preguntar.

## Instalación de todas de una vez

```bash
bash <ruta-de-esta-skill>/scripts/instalar.sh              # estado: qué está y qué falta
bash <ruta-de-esta-skill>/scripts/instalar.sh --instalar   # instala lo que falte (en este proyecto)
bash <ruta-de-esta-skill>/scripts/instalar.sh --instalar --global   # para todos tus proyectos
```

Incluye los subagentes de thermos (el instalador de skills no los copia), **activa el hook de `proteccion`** en `.claude/settings.json` (o en `~/.claude` con `--global`) y, con `--con-rtk`, instala el programa RTK.
