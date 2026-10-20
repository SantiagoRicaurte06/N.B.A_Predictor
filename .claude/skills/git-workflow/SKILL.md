---
name: git-workflow
description: Normas de Git para cualquier proyecto (Git Flow simplificado, Conventional Commits, SemVer, PRs, releases y hotfixes) y su configuración en un repo nuevo con hooks locales, GitHub Actions y plantilla de PR. Úsala al crear ramas, escribir commits o PRs, preparar un release o hotfix, o cuando pidan "configura el git workflow", "normas de git", "convención de commits" o "prepara el repo".
---

# Git workflow

Las normas completas están en [`referencia/GIT_WORKFLOW.md`](referencia/GIT_WORKFLOW.md). Léelas antes de crear ramas, commits, PRs o tags.

## Si el proyecto aún no lo tiene configurado

Señales: no existe `GIT_WORKFLOW.md`, no hay rama `develop` o `git config core.hooksPath` no es `.githooks`.

1. Muestra la vista previa (no modifica nada):
   ```bash
   bash <ruta-de-esta-skill>/scripts/configurar.sh
   ```
2. Explica al desarrollador lo que se va a crear y **pide aprobación**.
3. Aplica:
   ```bash
   bash <ruta-de-esta-skill>/scripts/configurar.sh --aplicar
   ```
   Crea `develop`, copia `GIT_WORKFLOW.md`, agrega la sección a `CLAUDE.md` (o `AGENTS.md`), instala `.github/workflows/commits.yml`, `.github/workflows/pruebas.yml`, `.github/pull_request_template.md`, los hooks `.githooks/commit-msg` y `.githooks/pre-commit`, y completa `.gitignore`. No sobrescribe nada que ya exista.
4. Solo con aprobación explícita:
   - `--push` sube `develop` a GitHub.
   - `--github` (requiere `gh` autenticado) pone `develop` como rama por defecto, borra ramas al integrar, deja squash y merge commit, e intenta proteger `main` y `develop`. En un repo **privado del plan gratuito** GitHub lo rechaza; el script lo informa y la protección queda como acuerdo de equipo (§8).
5. Revisa `pruebas.yml`: detecta Node, Python, Go y Rust; ajústalo si el proyecto usa otros comandos.
6. Haz el commit de la configuración en `chore/git-workflow` y actualiza la tabla de la sección 8 de `GIT_WORKFLOW.md`.

## Trabajo diario

**Antes de empezar un cambio**
1. `git switch develop && git pull` (hotfix: desde `main`).
2. `git switch -c <tipo>/<descripcion-corta>`: `feature/`, `fix/`, `refactor/`, `docs/`, `chore/`. Kebab-case, ≤ 4 palabras, número de issue opcional.

**Al hacer commit**
- `<tipo>(<scope>): <descripción>` en imperativo, minúscula, sin punto final, ≤ 72 caracteres. Tipos: `feat fix refactor perf test docs style build ci chore revert`.
- Cuerpo con el porqué si no es obvio. Footer: `Closes #N`, `BREAKING CHANGE: …`.
- Una unidad lógica por commit; no mezclar refactor con features o fixes.
- Si el cambio no es trivial, **propón el mensaje y el diff antes de ejecutar**.

**Al abrir un PR**
- Título en Conventional Commits; descripción con qué, por qué y cómo probarlo (plantilla).
- `feature/*` → `develop` con **squash**. `release/*` y `hotfix/*` → `main` y `develop` con **merge commit (`--no-ff`)**.

**Release y hotfix**: sigue los pasos de la §4 de `GIT_WORKFLOW.md`. Tags anotados `vX.Y.Z` solo sobre `main`. SemVer: `BREAKING CHANGE` → MAJOR, `feat` → MINOR, `fix` → PATCH.

## Reglas para el asistente

- **No añadir `Co-Authored-By` ni firmas de IA** (`🤖 Generated with…`) en commits, PRs, tags o releases. Los hooks y el CI los rechazan.
- No cambiar `user.name` ni `user.email`.
- **Sin aprobación explícita, no**: `push`, `push --force`, reescribir historial, merges a `main`/`develop` ni crear tags.
- Nunca `--force` sobre `main` o `develop`. En ramas propias, `--force-with-lease`, y antes de reescribir crea `backup/<descripcion>-<yyyymmdd>`.
- Nunca subir `.env`, llaves ni credenciales.
- `git commit --no-verify` solo si el desarrollador lo pide.

## Checklist antes de cada commit

- [ ] Rama correcta (no `main` ni `develop`).
- [ ] Una sola unidad lógica.
- [ ] Compila y las pruebas pasan.
- [ ] Mensaje en Conventional Commits, ≤ 72 caracteres.
- [ ] Sin secretos, archivos temporales ni código de depuración.
- [ ] Sin trailers de coautoría ni firmas de IA.
