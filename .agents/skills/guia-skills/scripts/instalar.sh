#!/usr/bin/env bash
# Muestra qué skills del equipo están instaladas y, con --instalar, instala las que falten.
#   --instalar        instala lo que falte
#   --global          instala para todos tus proyectos (~/.claude) en vez de solo este
#   --agente <nombre> agente destino para `npx skills` (por defecto: claude-code)
#   --con-rtk         también instala el programa RTK (brew o script oficial)
set -euo pipefail

INSTALAR=0; GLOBAL=0; RTK=0; AGENTE=claude-code
while [ $# -gt 0 ]; do
  case "$1" in
    --instalar) INSTALAR=1 ;; --global) GLOBAL=1 ;; --con-rtk) RTK=1 ;;
    --agente) AGENTE="$2"; shift ;;
    -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
    *) echo "Opción desconocida: $1" >&2; exit 2 ;;
  esac
  shift
done

# nombre | fuente para npx skills | skills a instalar | para qué
CATALOGO='grill-me|mattpocock/skills|grill-me grilling|entrevista antes de construir
caveman|JuliusBrussee/caveman|caveman ultracave megacave|respuestas cortas, menos tokens
anti-slop|rand/cc-polymath|anti-slop|quita el contenido con cara de IA
thermos|https://github.com/cursor/plugins/tree/main/thermos|thermos thermo-nuclear-review thermo-nuclear-code-quality-review|doble revisión antes de mergear
checklist-lanzamiento|santiagoricaurte06/discord|checklist-lanzamiento|24 puntos antes de deployar
git-workflow|santiagoricaurte06/discord|git-workflow|normas de ramas, commits y PRs
proteccion|santiagoricaurte06/discord|proteccion|hook que frena borrar la BD, rm -rf y force push
guia-skills|santiagoricaurte06/discord|guia-skills|esta guía'
AGENTES_THERMOS="thermo-nuclear-review-subagent thermo-nuclear-code-quality-review-subagent"

DIR_PROYECTO=".claude"; DIR_GLOBAL="$HOME/.claude"
instalada() { [ -f "$DIR_PROYECTO/skills/$1/SKILL.md" ] || [ -f "$DIR_GLOBAL/skills/$1/SKILL.md" ] || [ -f ".agents/skills/$1/SKILL.md" ]; }
# El hook de proteccion no basta con instalar la skill: hay que activarlo en settings.json.
dir_skill() { local d; for d in "$DIR_PROYECTO/skills/$1" ".agents/skills/$1" "$DIR_GLOBAL/skills/$1"; do [ -d "$d" ] && { echo "$d"; return; }; done; }
hook_ok() { grep -qs 'proteccion\.sh' "$DIR_PROYECTO/settings.json" "$DIR_GLOBAL/settings.json"; }
agente_ok() { [ -f "$DIR_PROYECTO/agents/$1.md" ] || [ -f "$DIR_GLOBAL/agents/$1.md" ]; }

echo "Skills del equipo ($([ "$GLOBAL" = 1 ] && echo "global: $DIR_GLOBAL" || echo "proyecto: $(pwd)"))"
echo
faltan=()
while IFS='|' read -r nombre fuente skills uso; do
  pendientes=()
  for s in $skills; do instalada "$s" || pendientes+=("$s"); done
  if [ "$nombre" = thermos ]; then for a in $AGENTES_THERMOS; do agente_ok "$a" || pendientes+=("agente:$a"); done; fi
  if [ "$nombre" = proteccion ]; then hook_ok || pendientes+=("activar el hook"); fi
  if [ ${#pendientes[@]} -eq 0 ]; then printf '  ✅ %-22s %s\n' "$nombre" "$uso"
  else printf '  ⬜ %-22s %s  (falta: %s)\n' "$nombre" "$uso" "${pendientes[*]}"; faltan+=("$nombre"); fi
done <<< "$CATALOGO"
if command -v rtk >/dev/null 2>&1; then printf '  ✅ %-22s %s\n' "RTK" "comprime la salida de la terminal ($(rtk --version 2>/dev/null))"
else printf '  ⬜ %-22s %s\n' "RTK" "comprime la salida de la terminal (programa aparte: --con-rtk)"; fi

if [ "$INSTALAR" != 1 ]; then
  echo
  if [ ${#faltan[@]} -eq 0 ]; then echo "Todo instalado."; else echo "Para instalar lo que falta: bash $0 --instalar$([ "$GLOBAL" = 1 ] && echo ' --global')   (opcional: --con-rtk)"; fi
  exit 0
fi

echo
FLAGS=(-a "$AGENTE" -y); [ "$GLOBAL" = 1 ] && FLAGS+=(-g)
while IFS='|' read -r nombre fuente skills uso; do
  [[ " ${faltan[*]} " == *" $nombre "* ]] || continue
  echo "→ $nombre"
  # shellcheck disable=SC2086
  npx -y skills@latest add "$fuente" --skill $skills "${FLAGS[@]}" </dev/null >/dev/null 2>&1 \
    && echo "  ✓ skills: $skills" || echo "  ✖ no se pudo instalar (revisa tu conexión o corre: npx skills add $fuente --skill $skills)"
  if [ "$nombre" = proteccion ]; then
    d="$(dir_skill proteccion)"
    if [ -n "$d" ] && bash "$d/scripts/activar.sh" $([ "$GLOBAL" = 1 ] && echo --global) </dev/null >/dev/null; then
      echo "  ✓ hook activo en $([ "$GLOBAL" = 1 ] && echo "$DIR_GLOBAL" || echo "$DIR_PROYECTO")/settings.json"
    else echo "  ✖ no se pudo activar el hook (corre: bash <skill proteccion>/scripts/activar.sh)"; fi
  fi
  if [ "$nombre" = thermos ]; then
    destino="$([ "$GLOBAL" = 1 ] && echo "$DIR_GLOBAL" || echo "$DIR_PROYECTO")/agents"
    mkdir -p "$destino"
    for a in $AGENTES_THERMOS; do
      curl -fsSL "https://raw.githubusercontent.com/cursor/plugins/main/thermos/agents/$a.md" -o "$destino/$a.md" </dev/null \
        && echo "  ✓ subagente: $a" || echo "  ✖ no se pudo bajar el subagente $a"
    done
  fi
done <<< "$CATALOGO"

if [ "$RTK" = 1 ] && ! command -v rtk >/dev/null 2>&1; then
  echo "→ RTK"
  if command -v brew >/dev/null 2>&1; then brew install rtk >/dev/null && echo "  ✓ instalado con brew"
  else curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh >/dev/null && echo "  ✓ instalado en ~/.local/bin"; fi
  echo "  i Conéctalo a tu agente y reinícialo: rtk init -g   (comprueba con: rtk gain)"
fi

echo
echo "Listo. Reinicia el agente para que cargue las skills nuevas. Actualizar más adelante: npx skills@latest update"
