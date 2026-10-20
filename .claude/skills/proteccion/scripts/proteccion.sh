#!/usr/bin/env bash
# Hook PreToolUse de Claude Code: frena acciones que pueden romper el proyecto antes de que se ejecuten.
#   bloquear  → la acción no se ejecuta (borrar la base de datos, rm -rf ., force push a main…)
#   preguntar → Claude Code le pide permiso al usuario (git reset --hard, editar .env…)
# Recibe el JSON del hook por stdin. Funciona con jq, python3 o node; sin ninguno, revisa el JSON en bruto.
set -f

entrada="$(cat)"
leer() {
  if command -v jq >/dev/null 2>&1; then
    jq -r '.tool_name // "", (.tool_input.file_path // .tool_input.notebook_path // ""), (.tool_input.command // "")' <<<"$entrada" 2>/dev/null && return
  fi
  if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import json,sys
d=json.load(sys.stdin); t=d.get("tool_input") or {}
print(d.get("tool_name") or ""); print(t.get("file_path") or t.get("notebook_path") or ""); print(t.get("command") or "")' <<<"$entrada" 2>/dev/null && return
  fi
  if command -v node >/dev/null 2>&1; then
    node -e 'let s="";process.stdin.on("data",c=>s+=c).on("end",()=>{const d=JSON.parse(s),t=d.tool_input||{};
console.log(d.tool_name||"");console.log(t.file_path||t.notebook_path||"");console.log(t.command||"")})' <<<"$entrada" 2>/dev/null && return
  fi
  # Sin intérprete de JSON: se extraen los campos con sed.
  local j; j="$(tr '\n' ' ' <<<"$entrada")"
  campo() { sed -n "s/.*\"$1\"[[:space:]]*:[[:space:]]*\"\(\([^\"\\\\]\|\\\\.\)*\)\".*/\1/p" <<<"$j" | head -n1; }
  printf '%s\n%s\n' "$(campo tool_name)" "$(campo file_path)"
  campo command | sed 's/\\n/ ; /g; s/\\t/ /g; s/\\"/"/g; s/\\\\/\\/g'
}
{ IFS= read -r herramienta; IFS= read -r archivo; comando="$(cat)"; } < <(leer)

responder() { # $1 = deny|ask, $2 = motivo
  local extra='' motivo="${2//\\/\\\\}"; motivo="${motivo//\"/\\\"}"
  [ "$1" = deny ] && extra=' Si de verdad hace falta, el usuario puede correrlo en su terminal (en Claude Code: !comando).'
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"%s","permissionDecisionReason":"🛡️ proteccion: %s.%s"}}\n' "$1" "$motivo" "$extra"
  exit 0
}
bloquear() { responder deny "$1"; }
preguntar() { responder ask "$1"; }

# ── Archivos (Write, Edit, MultiEdit, NotebookEdit) ──────────────────────────
if [ -n "$archivo" ]; then
  a="${archivo,,}"
  [[ $a =~ \.(db|sqlite|sqlite3|db-wal|db-shm|db-journal|mdb)$ ]] && bloquear "No se editan archivos de base de datos a mano ($archivo); usa la app o una migración"
  [[ $a =~ (^|/)\.git/ ]] && bloquear "No se toca el interior de .git ($archivo)"
  [[ $a =~ (^|/)\.env($|\.) && ! $a =~ \.(example|sample|template)$ ]] && preguntar "Vas a modificar un archivo de variables de entorno ($archivo)"
  [[ $a =~ (^|/)\.claude/(settings(\.local)?\.json|hooks/) ]] && preguntar "Vas a cambiar la configuración o los hooks de Claude ($archivo)"
  [[ $a =~ (^|/)migrations?/ && -e $archivo ]] && preguntar "Vas a modificar una migración que ya existe ($archivo); lo normal es crear una nueva"
  exit 0
fi

[ -n "$comando" ] || exit 0
c="${comando,,}"; c="${c//$'\n'/ ; }"; c="${c//$'\t'/ }"
si() { [[ $c =~ $1 ]]; }

# ── rm: borrar todo, la base de datos o el repo ──────────────────────────────
en_rm=0; recursivo=0
for t in $c; do
  t="${t//[\"\']/}"
  fin=0; case "$t" in *';'|*'&&'|*'||'|*'|') fin=1; t="${t%%[;&|]*}" ;; esac
  case "$t" in
    ';'|'&&'|'||'|'|'|'') ;;
    rm|*/rm) en_rm=1; recursivo=0 ;;
    *) if [ $en_rm = 1 ]; then
         case "$t" in
           --recursive|-r|-R) recursivo=1 ;;
           --*) ;;
           -*) [[ $t == *r* ]] && recursivo=1 ;;
           *) if [ $recursivo = 1 ]; then
                case "$t" in
                  /|/\*|\~|\~/|\~/\*|../\*|\$home|\$home/|\$home/\*|\$\{home\}|\$\{home\}/|.|./|./\*|..|../|\*|.git|.git/|*/.git|*/.git/|/etc|/usr|/var|/home|/bin|/boot|/lib|/opt|/root|/srv|\$pwd|\$\{pwd\})
                    bloquear "rm recursivo sobre '$t' borra el proyecto, el sistema o el repo" ;;
                esac
              fi
              [[ $t =~ \.(db|sqlite|sqlite3|db-wal|db-shm|mdb)$ ]] && bloquear "Borrar '$t' elimina la base de datos"
              [[ $t =~ (^|/)(data|db|database|backups?|prisma/migrations|migrations)/?$ ]] && bloquear "Borrar '$t' elimina datos, respaldos o migraciones"
              [[ $t =~ (^|/)\.env$ ]] && preguntar "Vas a borrar el archivo .env" ;;
         esac
       fi ;;
  esac
  [ $fin = 1 ] && en_rm=0
done
si '(^|[[:space:];&|(`])(shred|wipefs)[[:space:]]' && bloquear "shred/wipefs destruyen archivos sin recuperación"
si '(^|[[:space:];&|(`])mkfs' && bloquear "mkfs formatea un disco"
si '(^|[[:space:];&|(`])dd[[:space:]].*of=/dev/' && bloquear "dd sobre un dispositivo borra el disco"
si '(^|[[:space:];&|(`])chmod[[:space:]]+(-[a-z]+[[:space:]]+)*0?777' && bloquear "chmod 777 abre los archivos a cualquiera"
si ':\(\)[[:space:]]*\{' && bloquear "fork bomb"
si '>[[:space:]]*[^[:space:]>&|;]*\.(db|sqlite|sqlite3)([[:space:]]|$|\;)' && bloquear "Redirigir con > sobre la base de datos la deja vacía"
si '(^|[[:space:];&|(`])truncate[[:space:]]+-s' && preguntar "truncate vacía el archivo"
si '(^|[[:space:];&|(`])find[[:space:]].*(-delete|-exec[[:space:]]+rm)' && preguntar "find con -delete puede borrar mucho más de lo que crees"

# ── Bases de datos ───────────────────────────────────────────────────────────
cliente_bd='(psql|mysql|mariadb|sqlite|mongo|redis-cli|sqlcmd|clickhouse|cockroach|turso|d1[[:space:]]+execute|db[[:space:]]+execute|\.sql|node[[:space:]]+-e|python3?[[:space:]]+-c|bun[[:space:]]+-e|--eval|--execute|--command)'
if si "$cliente_bd"; then
  si 'drop[[:space:]]+(database|schema|table|collection|owned)([[:space:]]|$)' && bloquear "DROP elimina la base de datos o tablas completas"
  si 'truncate[[:space:]]+table' && bloquear "TRUNCATE borra todos los registros de la tabla"
  si 'delete[[:space:]]+from[[:space:]]' && ! si '[[:space:]]where[[:space:]]' && bloquear "DELETE sin WHERE borra todos los registros"
  si 'update[[:space:]]+[a-z_\"\`.]+[[:space:]]+set[[:space:]]' && ! si '[[:space:]]where[[:space:]]' && bloquear "UPDATE sin WHERE cambia todos los registros"
  si 'dropdatabase\(|\.drop\(\)|deletemany\(\{\}\)' && bloquear "Eso elimina la base de datos o una colección de Mongo"
  si '(flushall|flushdb)' && bloquear "FLUSHALL/FLUSHDB vacía Redis"
fi
si '(^|[[:space:];&|(`])(dropdb|dropuser)([[:space:]]|$)' && bloquear "dropdb elimina la base de datos"
si 'prisma[[:space:]]+migrate[[:space:]]+reset' && bloquear "prisma migrate reset borra todos los datos"
si 'prisma[[:space:]]+db[[:space:]]+push.*(--force-reset|--accept-data-loss)' && bloquear "prisma db push con --force-reset/--accept-data-loss borra datos"
si 'supabase[[:space:]]+db[[:space:]]+reset' && bloquear "supabase db reset borra la base de datos"
si '(rails|rake|bin/rails)[[:space:]]+db:(drop|reset|purge|schema:load|truncate_all)' && bloquear "Esa tarea de Rails borra la base de datos"
si 'manage\.py[[:space:]]+(flush|reset_db|sqlflush)' && bloquear "Ese comando de Django borra la base de datos"
si 'artisan[[:space:]]+(migrate:fresh|migrate:reset|db:wipe)' && bloquear "Ese comando de Laravel borra la base de datos"
si 'sequelize(-cli)?[[:space:]]+db:(drop|migrate:undo:all|seed:undo:all)' && bloquear "Ese comando de Sequelize borra datos"
si '(drizzle-kit[[:space:]]+drop|typeorm.*schema:drop|knex[[:space:]]+migrate:rollback.*--all)' && bloquear "Ese comando deshace todas las migraciones o borra el esquema"
si 'firebase[[:space:]]+(firestore:delete|database:remove)' && bloquear "Eso borra datos de Firebase"
si '(prisma[[:space:]]+migrate[[:space:]]+deploy|migrate[[:space:]]+up|db:migrate).*(prod|production)' && preguntar "Vas a migrar la base de datos de producción"

# ── Git ──────────────────────────────────────────────────────────────────────
if si '(^|[[:space:];&|(`])git[[:space:]]'; then
  # Sin el texto entre comillas: un mensaje de commit que menciona "--no-verify" o "main" no cuenta.
  c_completo="$c"; c="$(sed -E "s/\"([^\"\\\\]|\\\\.)*\"//g; s/'[^']*'//g" <<<"$c")"
  principales='(main|master|develop|production|prod|release)'
  si '--no-verify|core\.hookspath' && bloquear "No se saltan los hooks del equipo (--no-verify / core.hooksPath)"
  if si 'git[[:space:]]+(-c[[:space:]]+[^[:space:]]+[[:space:]]+)*push([[:space:]]|$)'; then
    forzado=0; destinos=(); tras_push=0
    for t in $c; do
      t="${t%%[;&|]*}"
      [ $tras_push = 0 ] && { [ "$t" = push ] && tras_push=1; continue; }
      case "$t" in
        --force*|-f) forzado=1 ;;
        --*) ;;
        -*) [[ $t == *f* ]] && forzado=1 ;;
        '') break ;;
        *) [[ $t == +* ]] && forzado=1; destinos+=("$t") ;;
      esac
      [[ $t == *';' ]] && break
    done
    if [ $forzado = 1 ]; then
      ramas_push="${destinos[*]:1}"
      { [ -z "$ramas_push" ] || [[ " $ramas_push " =~ [[:space:]:+]$principales([[:space:]]|$) || " $ramas_push " =~ [[:space:]]\+?head([[:space:]:]|$) ]]; } \
        && bloquear "Force push a una rama principal (o sin decir a qué rama) reescribe el historial de todo el equipo"
      preguntar "Force push reescribe el historial remoto de la rama"
    fi
    [[ $c =~ --delete[[:space:]].*$principales || $c =~ [[:space:]]:$principales([[:space:]]|$) ]] && bloquear "Eso borra una rama principal en el remoto"
    si '--mirror' && bloquear "push --mirror puede borrar ramas remotas"
  fi
  si '(filter-branch|filter-repo)' && bloquear "Reescribir todo el historial rompe los clones del equipo"
  si 'git[[:space:]]+(-c[[:space:]]+[^[:space:]]+[[:space:]]+)*reset[[:space:]].*--hard' && preguntar "git reset --hard descarta los cambios sin commitear"
  si 'git[[:space:]]+clean[[:space:]]+(.*[[:space:]])?(-[a-z]*f|--force)' && preguntar "git clean -f borra archivos que no están en git"
  si 'git[[:space:]]+(checkout|restore)[[:space:]]+(--[[:space:]]+)?(\.|\*|:/)([[:space:]]|$)' && preguntar "Eso descarta todos los cambios sin commitear"
  [[ $comando =~ git[[:space:]]+branch[[:space:]].*(-D|--delete[[:space:]]+--force|-[a-zA-Z]*D) ]] && preguntar "Vas a borrar una rama a la fuerza (-D)"
  [[ $c =~ git[[:space:]]+branch[[:space:]].*(-d|--delete)[[:space:]]+(.*[[:space:]])?$principales([[:space:]]|$) ]] && bloquear "No se borran las ramas principales"
  si 'git[[:space:]]+stash[[:space:]]+(clear|drop)' && preguntar "Vas a borrar cambios guardados en el stash"
  si 'git[[:space:]]+update-ref[[:space:]]+-d' && preguntar "Vas a borrar una referencia de git"
  c="$c_completo"
fi

# ── Infraestructura y publicación ────────────────────────────────────────────
si 'docker[[:space:]]+volume[[:space:]]+(rm|prune)' && bloquear "Borrar volúmenes de Docker elimina los datos guardados (bases de datos incluidas)"
si 'docker[[:space:]]+system[[:space:]]+prune.*(--volumes|-a)' && bloquear "docker system prune con volúmenes borra los datos"
si 'docker([[:space:]]+|-)compose.*[[:space:]]down.*([[:space:]]-v([[:space:]]|$)|--volumes)' && bloquear "docker compose down -v borra los volúmenes (la base de datos)"
si 'terraform[[:space:]]+(destroy|apply.*-destroy)' && bloquear "terraform destroy elimina la infraestructura"
si 'kubectl[[:space:]]+delete' && preguntar "kubectl delete elimina recursos del cluster"
si 'gh[[:space:]]+repo[[:space:]]+delete' && bloquear "Borrar el repositorio de GitHub no se puede deshacer"
si '(railway|fly|flyctl|heroku|vercel|netlify)[[:space:]]+.*(delete|destroy|remove|[[:space:]]rm|[[:space:]]down|volumes?[[:space:]]+(rm|delete|destroy))' && preguntar "Vas a borrar o apagar algo del hosting"
si '(npm|yarn|pnpm)[[:space:]]+unpublish' && bloquear "unpublish rompe a quien use el paquete"
si '(^|[[:space:];&|(`])(npm|yarn|pnpm|bun)[[:space:]]+publish' && preguntar "Vas a publicar el paquete"
exit 0
