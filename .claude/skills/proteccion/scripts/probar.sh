#!/usr/bin/env bash
# Prueba el hook con comandos de ejemplo: los peligrosos deben frenarse y los normales pasar.
#   bash probar.sh            (usa el proteccion.sh de esta carpeta)
#   bash probar.sh <ruta>     (prueba otro, por ejemplo .claude/hooks/proteccion.sh)
HOOK="${1:-$(dirname "$0")/proteccion.sh}"
fallos=0
caso() { # $1 esperado (deny|ask|ok), $2 herramienta, $3 comando o archivo
  local json
  if [ "$2" = Bash ]; then json=$(printf '%s' "$3" | python3 -c 'import json,sys;print(json.dumps({"tool_name":"Bash","tool_input":{"command":sys.stdin.read()}}))' 2>/dev/null \
    || node -e 'let s="";process.stdin.on("data",c=>s+=c).on("end",()=>console.log(JSON.stringify({tool_name:"Bash",tool_input:{command:s}})))' <<<"$3")
  else json="{\"tool_name\":\"$2\",\"tool_input\":{\"file_path\":\"$3\"}}"; fi
  local salida; salida=$(bash "$HOOK" <<<"$json")
  local obtenido=ok
  [[ $salida == *'"deny"'* ]] && obtenido=deny; [[ $salida == *'"ask"'* ]] && obtenido=ask
  if [ "$obtenido" = "$1" ]; then printf '  ✓ %-5s %s\n' "$1" "$3"; else printf '  ✖ esperaba %s, salió %s: %s\n' "$1" "$obtenido" "$3"; fallos=$((fallos+1)); fi
}
echo "Bloquea:"
caso deny Bash 'rm -rf /'
caso deny Bash 'rm -rf .'
caso deny Bash 'sudo rm -fr ~'
caso deny Bash 'cd src && rm -rf ../*'
caso deny Bash 'rm -r -f .git'
caso deny Bash 'rm data/db.json data/app.db'
caso deny Bash 'rm -rf prisma/migrations'
caso deny Bash 'psql "$DATABASE_URL" -c "DROP TABLE users;"'
caso deny Bash 'echo "drop database app" | mysql -u root'
caso deny Bash 'sqlite3 app.db "DELETE FROM orders;"'
caso deny Bash 'redis-cli FLUSHALL'
caso deny Bash 'dropdb produccion'
caso deny Bash 'npx prisma migrate reset --force'
caso deny Bash 'npx prisma db push --accept-data-loss'
caso deny Bash 'supabase db reset --linked'
caso deny Bash 'php artisan migrate:fresh'
caso deny Bash 'docker compose down -v'
caso deny Bash 'docker volume rm app_pgdata'
caso deny Bash 'echo "" > data/app.sqlite'
caso deny Bash 'git push --force origin main'
caso deny Bash 'git push -f'
caso deny Bash 'git push origin +develop'
caso deny Bash 'git commit -m "fix: arreglo" --no-verify'
caso deny Bash 'git push origin --delete main'
caso deny Bash 'gh repo delete equipo/app --yes'
caso deny Bash 'terraform destroy -auto-approve'
caso deny Write 'data/app.db'
caso deny Edit '/proyecto/.git/config'
echo "Pide permiso:"
caso ask Bash 'git reset --hard HEAD~3'
caso ask Bash 'git clean -fd'
caso ask Bash 'git checkout -- .'
caso ask Bash 'git branch -D feature/login'
caso ask Bash 'git push --force-with-lease origin feature/login'
caso ask Bash 'npm publish'
caso ask Bash 'find . -name "*.log" -delete'
caso ask Edit '.env'
caso ask Write '.claude/settings.json'
echo "Deja pasar:"
caso ok Bash 'rm -rf node_modules dist'
caso ok Bash 'rm src/viejo.js'
caso ok Bash 'git push origin feature/login'
caso ok Bash 'git push -u origin feature/login'
caso ok Bash 'git commit -m "fix: delete from cart sin errores"'
caso ok Bash 'git branch -d feature/login'
caso ok Bash 'git commit -m "docs: explica por qué no usar --no-verify ni push a main"'
caso ok Bash 'psql -c "DELETE FROM sesiones WHERE expira < now();"'
caso ok Bash 'npx prisma migrate dev --name usuarios'
caso ok Bash 'docker compose down'
caso ok Bash 'npm test'
caso ok Edit 'src/index.js'
caso ok Write '.env.example'
echo
[ $fallos = 0 ] && echo "Todo bien: el hook funciona." || { echo "$fallos casos fallaron."; exit 1; }
