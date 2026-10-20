---
name: proteccion
description: Hook de seguridad para Claude Code que frena, antes de ejecutarse, las acciones que pueden romper el proyecto - borrar la base de datos (DROP, TRUNCATE, DELETE sin WHERE, prisma migrate reset, supabase db reset, docker compose down -v), rm -rf sobre el proyecto, el sistema o .git, force push o borrado de main/develop, saltarse los hooks con --no-verify y editar archivos .db o .git. Úsala para activar la protección en un repo o en tu equipo, cuando un comando tuyo sea bloqueado por "🛡️ proteccion", y antes de cualquier operación destructiva sobre datos.
---

# Protección contra acciones destructivas

Esta skill instala un **hook `PreToolUse`** de Claude Code: un script que revisa cada comando de terminal y cada archivo que vas a escribir **antes** de que se ejecute. No depende de que te acuerdes de las reglas: si el comando es peligroso, Claude Code no lo corre.

Tiene dos niveles:

| Nivel | Qué pasa | Ejemplos |
|---|---|---|
| **Bloquear** | No se ejecuta. Claude recibe el motivo | `DROP TABLE`, `DELETE FROM x;` sin `WHERE`, `redis-cli FLUSHALL`, `dropdb`, `prisma migrate reset`, `prisma db push --accept-data-loss`, `supabase db reset`, `rails db:drop`, `artisan migrate:fresh`, `docker compose down -v`, `docker volume rm`, `rm -rf /`, `rm -rf .`, `rm -rf ~`, `rm -rf .git`, borrar `*.db`/`*.sqlite`/`data/`/`migrations/`, `> app.db`, `git push --force` a main/develop (o sin rama), `git push --delete main`, `--no-verify`, `git filter-branch`, `gh repo delete`, `terraform destroy`, editar archivos `.db` o el interior de `.git/` |
| **Preguntar** | Claude Code le pide permiso al usuario | `git reset --hard`, `git clean -f`, `git checkout -- .`, `git branch -D`, force push a una rama de feature, `find -delete`, `kubectl delete`, borrar en el hosting, `npm publish`, editar `.env`, `.claude/settings.json`, los hooks o una migración existente |

Lo normal (`rm -rf node_modules dist`, `git push origin feature/x`, `DELETE ... WHERE`, `prisma migrate dev`, `docker compose down`) pasa sin preguntar.

## Activarla

```bash
bash <ruta-de-esta-skill>/scripts/activar.sh            # en este repo: .claude/settings.json + .claude/hooks/
bash <ruta-de-esta-skill>/scripts/activar.sh --global   # en todos tus proyectos: ~/.claude/
bash <ruta-de-esta-skill>/scripts/activar.sh --estado   # ¿está activa?
bash <ruta-de-esta-skill>/scripts/probar.sh             # 51 casos: lo peligroso se frena, lo normal pasa
```

En un repo del equipo, **commitea `.claude/settings.json` y `.claude/hooks/proteccion.sh`**: así cada persona que lo abra con Claude Code queda protegida sin instalar nada. Los repos que crea el bot del equipo ya vienen con esto.

Después de activarla hay que reiniciar Claude Code (o revisarla en `/hooks`). No necesita `jq`: usa jq, python3 o node si los hay, y si no, lee el JSON con `sed`.

## Qué haces tú cuando te bloquea

1. **No intentes rodearla**: nada de reescribir el comando para que no coincida (otra sintaxis, `eval`, variables, un script aparte, `--no-verify`). Saltarse la protección es justo lo que no debe pasar.
2. **Dile al usuario qué querías hacer y por qué se bloqueó**, en una o dos líneas.
3. **Propón la alternativa segura**: respaldo antes de tocar datos (`pg_dump`, copiar el `.db`), una migración nueva en vez de resetear, `DELETE ... WHERE`, `git push --force-with-lease` a tu propia rama, `git stash` en vez de `reset --hard`, borrar solo la carpeta concreta.
4. Si de verdad hay que hacerlo, **lo corre el usuario**: en Claude Code puede escribir `!comando` para ejecutarlo él mismo, o hacerlo en su terminal.

Cuando sea "Preguntar", explica en tu mensaje qué va a pasar si el usuario acepta (qué se pierde y si se puede recuperar).

## Antes de operaciones con datos (aunque no te bloquee)

- Confirma **contra qué base de datos** estás (local, staging o producción) mirando la URL o las variables, sin mostrar contraseñas.
- Haz o pide un **respaldo** antes de migraciones que borran columnas o tablas.
- Nunca corras seeds, resets o migraciones destructivas contra producción.

## Límites

Es una **red de seguridad, no un sandbox**: revisa el texto de los comandos, así que algo muy ofuscado o un programa que borre datos por dentro no se detecta. Complementa, no reemplaza, los respaldos de la base de datos, la protección de ramas en GitHub y los permisos de Claude Code.

Basada en la idea de `git-guardrails-claude-code` (mattpocock/skills), ampliada a bases de datos, archivos, infraestructura y con nivel "preguntar" en vez de bloquear todo `git push`.
