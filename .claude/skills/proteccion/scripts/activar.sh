#!/usr/bin/env bash
# Activa el hook de protección en Claude Code: copia proteccion.sh a .claude/hooks y lo registra en settings.json.
#   bash activar.sh            en este proyecto (.claude/, se commitea y lo recibe todo el equipo)
#   bash activar.sh --global   para todos tus proyectos (~/.claude/)
#   bash activar.sh --estado   solo dice si está activo
#   bash activar.sh --quitar   lo desactiva
set -euo pipefail

MODO=activar; DESTINO=".claude"; RUTA='"$CLAUDE_PROJECT_DIR"/.claude/hooks/proteccion.sh'
for arg in "$@"; do
  case "$arg" in
    --global) DESTINO="$HOME/.claude"; RUTA='"$HOME"/.claude/hooks/proteccion.sh' ;;
    --estado) MODO=estado ;; --quitar) MODO=quitar ;;
    -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
    *) echo "Opción desconocida: $arg" >&2; exit 2 ;;
  esac
done
AQUI="$(cd "$(dirname "$0")" && pwd)"
AJUSTES="$DESTINO/settings.json"
COMANDO="bash $RUTA"

activo() { [ -f "$AJUSTES" ] && grep -q 'proteccion\.sh' "$AJUSTES" && [ -f "$DESTINO/hooks/proteccion.sh" ]; }
if [ "$MODO" = estado ]; then
  if activo; then echo "🛡️  proteccion activa en $DESTINO"; exit 0; else echo "⬜ proteccion no está activa en $DESTINO"; exit 1; fi
fi

# Edita settings.json con node o python3 (sin dependencias). $1 = activar|quitar
editar() {
  local script_js='const fs=require("fs"),[,f,cmd,modo]=process.argv;
let s={};try{s=JSON.parse(fs.readFileSync(f,"utf8"))}catch(e){if(fs.existsSync(f)&&fs.readFileSync(f,"utf8").trim()){console.error("settings.json no es JSON válido");process.exit(1)}}
s.hooks??={};let pre=(s.hooks.PreToolUse??=[]);
pre=pre.map(m=>({...m,hooks:(m.hooks||[]).filter(h=>!String(h.command||"").includes("proteccion.sh"))})).filter(m=>m.hooks.length);
if(modo==="activar")pre.push({matcher:"Bash|Write|Edit|MultiEdit|NotebookEdit",hooks:[{type:"command",command:cmd,timeout:10}]});
if(pre.length)s.hooks.PreToolUse=pre;else delete s.hooks.PreToolUse;
if(!Object.keys(s.hooks).length)delete s.hooks;
fs.writeFileSync(f,JSON.stringify(s,null,2)+"\n");'
  local script_py='import json,os,sys
f,cmd,modo=sys.argv[1:4]; s={}
if os.path.exists(f) and open(f).read().strip(): s=json.load(open(f))
h=s.setdefault("hooks",{}); pre=h.get("PreToolUse",[])
pre=[dict(m,hooks=[x for x in m.get("hooks",[]) if "proteccion.sh" not in str(x.get("command",""))]) for m in pre]
pre=[m for m in pre if m["hooks"]]
if modo=="activar": pre.append({"matcher":"Bash|Write|Edit|MultiEdit|NotebookEdit","hooks":[{"type":"command","command":cmd,"timeout":10}]})
if pre: h["PreToolUse"]=pre
else: h.pop("PreToolUse",None)
if not h: s.pop("hooks")
open(f,"w").write(json.dumps(s,indent=2,ensure_ascii=False)+"\n")'
  if command -v node >/dev/null 2>&1; then node -e "$script_js" "$AJUSTES" "$COMANDO" "$1"
  elif command -v python3 >/dev/null 2>&1; then python3 -c "$script_py" "$AJUSTES" "$COMANDO" "$1"
  elif [ "$1" = activar ] && [ ! -s "$AJUSTES" ]; then
    printf '{\n  "hooks": {\n    "PreToolUse": [\n      { "matcher": "Bash|Write|Edit|MultiEdit|NotebookEdit", "hooks": [ { "type": "command", "command": "%s", "timeout": 10 } ] }\n    ]\n  }\n}\n' "${COMANDO//\"/\\\"}" > "$AJUSTES"
  else
    echo "No encontré node ni python3 para editar $AJUSTES. Agrega a mano en hooks.PreToolUse:" >&2
    echo "  { \"matcher\": \"Bash|Write|Edit|MultiEdit|NotebookEdit\", \"hooks\": [ { \"type\": \"command\", \"command\": \"${COMANDO//\"/\\\"}\" } ] }" >&2
    exit 1
  fi
}

mkdir -p "$DESTINO/hooks"
if [ "$MODO" = quitar ]; then
  [ -f "$AJUSTES" ] && editar quitar
  rm -f "$DESTINO/hooks/proteccion.sh"
  echo "proteccion desactivada en $DESTINO (reinicia Claude Code)."
  exit 0
fi
cp "$AQUI/proteccion.sh" "$DESTINO/hooks/proteccion.sh"
chmod +x "$DESTINO/hooks/proteccion.sh"
editar activar
echo "🛡️  proteccion activa en $DESTINO: frena borrar la base de datos, rm -rf, force push a main y similares."
[ "$DESTINO" = .claude ] && echo "   Commitea .claude/settings.json y .claude/hooks/ para que el equipo también la tenga."
echo "   Reinicia Claude Code (o abre /hooks) para que cargue el hook. Prueba: bash $AQUI/probar.sh .claude/hooks/proteccion.sh"
