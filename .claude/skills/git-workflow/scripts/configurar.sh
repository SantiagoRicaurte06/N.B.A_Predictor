#!/usr/bin/env bash
# Configura el Git workflow en el repositorio actual.
# Por defecto solo muestra lo que haría. Opciones:
#   --aplicar   escribe los archivos y la configuración local
#   --push      además sube la rama develop a origin (requiere --aplicar)
#   --github    además configura GitHub con `gh`: rama por defecto develop, borrar ramas al integrar,
#               squash y merge commit permitidos, e intenta proteger main y develop (requiere --aplicar)
# Es idempotente: no sobrescribe archivos que ya existen.
set -euo pipefail

APLICAR=0; PUSH=0; GITHUB=0
for a in "$@"; do
  case "$a" in
    --aplicar) APLICAR=1 ;; --push) PUSH=1 ;; --github) GITHUB=1 ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "Opción desconocida: $a" >&2; exit 2 ;;
  esac
done

SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
P="$SKILL/plantillas"
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "✖ No estás dentro de un repositorio git. Usa: git init" >&2; exit 1; }
cd "$(git rev-parse --show-toplevel)"

hacer() { # descripción, comando...
  local desc="$1"; shift
  if [ "$APLICAR" = 1 ]; then echo "  ✓ $desc"; "$@"; else echo "  • $desc"; fi
}
copiar() { # origen, destino
  if [ -e "$2" ]; then echo "  = $2 ya existe (no se toca)"; return; fi
  hacer "crear $2" bash -c 'mkdir -p "$(dirname "$2")" && cp "$1" "$2"' _ "$1" "$2"
}

[ "$APLICAR" = 1 ] && echo "Aplicando Git workflow en $(pwd)" || echo "Vista previa (nada se modifica; usa --aplicar)"

echo; echo "1. Ramas"
if ! git rev-parse --verify -q HEAD >/dev/null; then
  echo "  ! El repositorio no tiene commits. Haz el commit inicial en main primero:"
  echo "    git switch -c main && git add . && git commit -m \"chore: initial commit\""
  [ "$APLICAR" = 1 ] && exit 1
else
  if git rev-parse --verify -q main >/dev/null; then BASE=main
  elif git rev-parse --verify -q master >/dev/null; then BASE=master; echo "  ! La rama principal se llama master. Recomendado: git branch -m master main"
  else BASE=$(git symbolic-ref --short HEAD); echo "  ! No existe main; se usará '$BASE' como base"; fi
  if git rev-parse --verify -q develop >/dev/null; then echo "  = develop ya existe"
  else hacer "crear develop desde $BASE" git branch develop "$BASE"; fi
  if [ "$PUSH" = 1 ]; then hacer "subir develop a origin" git push -u origin develop; fi
fi

echo; echo "2. Documentación"
copiar "$SKILL/referencia/GIT_WORKFLOW.md" "GIT_WORKFLOW.md"
INSTR=CLAUDE.md; [ -f AGENTS.md ] && [ ! -f CLAUDE.md ] && INSTR=AGENTS.md
if [ -f "$INSTR" ] && grep -q '^## Git workflow' "$INSTR"; then echo "  = $INSTR ya tiene la sección Git workflow"
else hacer "agregar la sección Git workflow a $INSTR" bash -c 'printf "\n" >> "$1"; cat "$2" >> "$1"' _ "$INSTR" "$P/claude-md.md"; fi

echo; echo "3. GitHub Actions y plantilla de PR"
copiar "$P/github/workflows/commits.yml" ".github/workflows/commits.yml"
copiar "$P/github/workflows/pruebas.yml" ".github/workflows/pruebas.yml"
copiar "$P/github/pull_request_template.md" ".github/pull_request_template.md"

echo; echo "4. Hooks locales"
copiar "$P/githooks/commit-msg" ".githooks/commit-msg"
copiar "$P/githooks/pre-commit" ".githooks/pre-commit"
hacer "hacer ejecutables los hooks" chmod +x .githooks/commit-msg .githooks/pre-commit
if [ "$(git config --get core.hooksPath || true)" = ".githooks" ]; then echo "  = core.hooksPath ya apunta a .githooks"
else hacer "activar los hooks (git config core.hooksPath .githooks)" git config core.hooksPath .githooks; fi
echo "  i Cada persona que clone el repo debe correr una vez: git config core.hooksPath .githooks"

echo; echo "5. .gitignore"
faltan=()
for linea in ".env" ".env.*" "!.env.example" "node_modules/" ".DS_Store" "*.log" "dist/" "build/" "coverage/" "__pycache__/" ".venv/"; do
  grep -qxF -- "$linea" .gitignore 2>/dev/null || faltan+=("$linea")
done
if [ ${#faltan[@]} -eq 0 ]; then echo "  = .gitignore completo"
else hacer "agregar a .gitignore: ${faltan[*]}" bash -c 'printf "%s\n" "$@" >> .gitignore' _ "${faltan[@]}"; fi

if [ "$GITHUB" = 1 ]; then
  echo; echo "6. GitHub"
  if ! command -v gh >/dev/null || ! gh auth status >/dev/null 2>&1; then
    echo "  ! Necesitas GitHub CLI autenticado (gh auth login). Se omite este paso."
  elif [ "$APLICAR" != 1 ]; then
    echo "  • rama por defecto develop · borrar ramas al integrar · squash y merge commit · proteger main y develop"
  else
    REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
    gh repo edit "$REPO" --default-branch develop --delete-branch-on-merge --enable-squash-merge --enable-merge-commit --enable-rebase-merge=false >/dev/null \
      && echo "  ✓ $REPO: rama por defecto develop, borrar ramas al integrar, squash y merge commit"
    for rama in "$BASE" develop; do
      salida=$(gh api -X PUT "repos/$REPO/branches/$rama/protection" --input - 2>&1 <<'JSON' || true
{"required_status_checks":{"strict":true,"contexts":["Título en Conventional Commits","Sin trailers de coautoría","Pruebas"]},
 "enforce_admins":false,"required_pull_request_reviews":{"required_approving_review_count":0},
 "restrictions":null,"allow_force_pushes":false,"allow_deletions":false}
JSON
)
      if printf '%s' "$salida" | grep -q 'Upgrade to GitHub Pro'; then
        echo "  ! $rama: el repo es privado en el plan gratuito; la protección queda como acuerdo de equipo (GIT_WORKFLOW.md §8)"
      elif printf '%s' "$salida" | grep -qi '"message"'; then
        echo "  ! $rama: no se pudo proteger: $(printf '%s' "$salida" | grep -o '"message":"[^"]*"' | head -1)"
      else
        echo "  ✓ $rama protegida: solo por PR, checks en verde, sin force push ni borrado"
      fi
    done
  fi
fi

echo
if [ "$APLICAR" = 1 ]; then
  echo "Listo. Siguientes pasos:"
  echo "  1. Revisa los cambios: git status"
  echo "  2. Haz commit en una rama: git switch -c chore/git-workflow && git add -A && git commit -m \"chore: add git workflow\""
  echo "  3. Actualiza la tabla de la sección 8 de GIT_WORKFLOW.md con lo que quedó forzado"
else
  echo "Para aplicar: bash $0 --aplicar   (opcional: --push --github)"
fi
