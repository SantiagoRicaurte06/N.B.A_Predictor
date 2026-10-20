# Git Workflow

Normas de ramas, commits, versiones y colaboración para este repositorio. Todo cambio, sea de una persona o de un asistente de IA, debe seguirlas.

> Idioma de ramas y commits: **inglés** (por defecto). Si el equipo decide usar español, cámbialo aquí y en `.githooks/commit-msg` (variable `IDIOMA`).

---

## 1. Modelo de ramas

Se usa **Git Flow simplificado**.

| Rama | Propósito | Nace de | Se integra en |
|---|---|---|---|
| `main` | Código en producción. Cada commit es una versión publicada. | — | — |
| `develop` | Integración de trabajo terminado para la próxima versión. | `main` | `release/*` |
| `feature/*` | Nueva funcionalidad. | `develop` | `develop` |
| `fix/*` | Corrección de un bug no urgente. | `develop` | `develop` |
| `refactor/*` | Mejora interna sin cambiar comportamiento. | `develop` | `develop` |
| `docs/*` | Solo documentación. | `develop` | `develop` |
| `chore/*` | Configuración, dependencias, tooling, CI. | `develop` | `develop` |
| `release/x.y.z` | Preparar una versión (ajustes finales, changelog). | `develop` | `main` y `develop` |
| `hotfix/x.y.z` | Corrección urgente en producción. | `main` | `main` y `develop` |

```
main      ●───────────────●────────────●
           \             / \          /
release     \       ●───●   \        /
             \     /         \      /
develop       ●───●───●───●───●────●───●
                   \     / \     /
feature             ●───●   ●───●
```

### Nombres de ramas

- Formato: `tipo/descripcion-corta` en minúsculas y kebab-case.
- Máximo ~4 palabras. Sin fechas ni nombres de personas.
- Si hay issue asociado, se puede prefijar su número.

```
feature/user-authentication
feature/42-shift-calendar
fix/expired-token-handling
refactor/api-client
chore/eslint-config
release/1.2.0
hotfix/1.2.1
```

### Reglas

- **Nunca** se hace commit directo a `main` ni a `develop`.
- Una rama = un objetivo. Si aparece trabajo no relacionado, se abre otra rama.
- Las ramas se eliminan después de integrarse.
- Mantener la rama actualizada con `develop` mediante `git rebase develop` (solo si la rama no está compartida) o `git merge develop`.

---

## 2. Commits — Conventional Commits

### Formato

```
<tipo>(<scope opcional>): <descripción>

<cuerpo opcional>

<footer opcional>
```

### Tipos permitidos

| Tipo | Uso |
|---|---|
| `feat` | Nueva funcionalidad para el usuario |
| `fix` | Corrección de un bug |
| `refactor` | Cambio de código que no altera comportamiento |
| `perf` | Mejora de rendimiento |
| `test` | Añadir o corregir tests |
| `docs` | Solo documentación |
| `style` | Formato, espacios, punto y coma (sin cambio lógico) |
| `build` | Sistema de build o dependencias |
| `ci` | Pipelines y configuración de CI/CD |
| `chore` | Mantenimiento que no encaja en lo anterior |
| `revert` | Revertir un commit previo |

### Scope

Opcional. Indica el módulo afectado, en minúsculas y en una palabra: `auth`, `api`, `db`, `ui`, `deps`.

### Descripción (primera línea)

- Modo imperativo: `add`, `fix`, `remove` (no `added`, `fixes`).
- Empieza en minúscula y **sin punto final**.
- Máximo **72 caracteres** en total.
- Describe *qué* cambia, no *cómo*.

### Cuerpo

- Separado por una línea en blanco.
- Explica el *porqué* y el contexto cuando no es obvio.
- Líneas de máximo 72 caracteres.

### Footer

- Referencias: `Closes #42`, `Refs #17`.
- Cambios incompatibles: `BREAKING CHANGE: <descripción>` o `!` tras el tipo.

### Ejemplos válidos

```
feat(auth): add JWT login endpoint
fix(api): return 404 when report does not exist
refactor(db): extract repository layer from services
test(auth): cover expired token scenario
docs: document local development setup
ci: add lint and test workflow
feat(api)!: change pagination to cursor-based

BREAKING CHANGE: `page` query param replaced by `cursor`.
```

### Mensajes prohibidos

`fix`, `changes`, `update`, `stuff`, `wip`, `final`, `final final`, `test`, `asdf`, `cosas`, `.`, o cualquier mensaje que no diga qué cambió.

### Tamaño del commit

- Un commit = una unidad lógica de trabajo que compila y pasa los tests.
- No mezclar refactor con features o fixes en el mismo commit.
- No sobre-dividir: varios cambios pequeños relacionados van juntos.

---

## 3. Pull Requests e integración

- Todo cambio entra a `develop` o `main` mediante Pull Request.
- Título del PR con formato Conventional Commits.
- Descripción mínima: qué cambia, por qué, cómo probarlo (ver `.github/pull_request_template.md`).
- Requisitos antes de integrar: CI en verde, sin conflictos, revisión propia del diff.

| Integración | Estrategia |
|---|---|
| `feature/*`, `fix/*`, etc. → `develop` | **Squash merge** (un commit limpio por PR) |
| `release/*` → `main` | **Merge commit** (`--no-ff`) |
| `hotfix/*` → `main` | **Merge commit** (`--no-ff`) |
| `release/*` / `hotfix/*` → `develop` | **Merge commit** (`--no-ff`) |

---

## 4. Versionado y releases

Se usa **Semantic Versioning**: `MAJOR.MINOR.PATCH`.

- `MAJOR`: cambios incompatibles (`BREAKING CHANGE`).
- `MINOR`: nuevas funcionalidades compatibles (`feat`).
- `PATCH`: correcciones compatibles (`fix`).
- Antes de `1.0.0` el proyecto se considera en desarrollo inicial.

### Proceso de release

```bash
git switch develop && git pull
git switch -c release/1.2.0
# ajustes finales, actualizar CHANGELOG.md y la versión (package.json, pyproject.toml…)
git switch main && git merge --no-ff release/1.2.0
git tag -a v1.2.0 -m "release: v1.2.0"
git switch develop && git merge --no-ff release/1.2.0
git branch -d release/1.2.0
git push origin main develop --follow-tags
```

### Proceso de hotfix

```bash
git switch main && git pull
git switch -c hotfix/1.2.1
# corrección + commit fix(...)
git switch main && git merge --no-ff hotfix/1.2.1
git tag -a v1.2.1 -m "release: v1.2.1"
git switch develop && git merge --no-ff hotfix/1.2.1
git branch -d hotfix/1.2.1
git push origin main develop --follow-tags
```

- Tags siempre anotados (`-a`), con prefijo `v`, solo sobre `main`.

---

## 5. Operaciones peligrosas

- Prohibido `git push --force` sobre `main` y `develop`.
- En ramas propias, si hay que reescribir historial, usar `git push --force-with-lease`.
- Antes de cualquier reescritura (`rebase`, `reset --hard`, `filter-repo`) crear un respaldo:

```bash
git branch backup/<descripcion>-<yyyymmdd>
```

- No hacer commit de secretos, `.env`, credenciales ni archivos generados. Mantener `.gitignore` actualizado.

---

## 6. Uso de asistentes de IA (Claude y otros)

Estas reglas son obligatorias para cualquier asistente de IA que genere commits, ramas o Pull Requests en este repositorio.

- **No añadir coautorías.** Prohibido incluir `Co-Authored-By: <IA> <...>` o cualquier otro trailer de coautoría en los commits.
- **No añadir firmas ni menciones de generación automática** en commits, PRs, tags o releases (por ejemplo `🤖 Generated with Claude Code` o similares).
- El autor y committer es siempre el desarrollador del repositorio, con la configuración de `user.name` y `user.email` existente. No modificarla.
- Seguir exactamente las normas de ramas y commits de este documento.
- No hacer `push`, `force-push`, reescritura de historial, merges a `main`/`develop` ni crear tags sin aprobación explícita del desarrollador.
- Proponer el mensaje del commit y el diff antes de ejecutar cuando el cambio no sea trivial.

> Esta sección también está en `CLAUDE.md` (o `AGENTS.md`) para que los asistentes la apliquen automáticamente.

---

## 7. Checklist antes de cada commit

- [ ] Estoy en la rama correcta (no `main` ni `develop`).
- [ ] El cambio es una sola unidad lógica.
- [ ] El código compila y los tests pasan.
- [ ] El mensaje sigue Conventional Commits y tiene ≤ 72 caracteres.
- [ ] No hay secretos, archivos temporales ni código de depuración.
- [ ] No hay trailers de coautoría ni firmas de IA.

---

## 8. Cómo se hacen cumplir estas reglas

Hay tres capas. Usa todas las que tu plan de GitHub permita.

| Capa | Qué fuerza | Dónde | Costo |
|---|---|---|---|
| **Hooks locales** (`.githooks/`) | Formato de commits, sin trailers de IA, sin commits directos a `main`/`develop` | En cada máquina, tras `git config core.hooksPath .githooks` | Gratis, cualquier repo |
| **CI** (`.github/workflows/`) | Título del PR en Conventional Commits, commits sin trailers de IA, pruebas en cada PR | GitHub Actions | Gratis (con minutos incluidos) |
| **Protección de ramas / rulesets** | Solo PR hacia `main`/`develop`, checks en verde obligatorios, sin force push ni borrado | Ajustes del repo en GitHub | Gratis en **repos públicos**; en **privados** requiere GitHub Pro, Team o superior |

### Si el repositorio es privado en el plan gratuito

GitHub responde `403 Upgrade to GitHub Pro or make this repository public to enable this feature.` al activar la protección de ramas. Entonces:

- Lo que **sí** queda forzado: hooks locales, checks del PR, rama por defecto `develop` y borrado de ramas al integrar.
- Lo que queda como **acuerdo de equipo**: que `main`/`develop` solo cambien por PR, checks en verde antes de integrar, sin force push y la estrategia de merge.
- **Revisa esta decisión cuando entre más gente a escribir código.** Con varios autores un acuerdo deja de ser suficiente, y el costo de GitHub Pro es bajo frente a un historial reescrito por accidente sobre `main`.

### Estado en este repositorio

| Regla | Estado |
|---|---|
| Hooks locales instalados | ☐ |
| CI de commits y pruebas | ☐ |
| Rama por defecto `develop` | ☐ |
| Borrado de ramas al integrar | ☐ |
| Protección de `main` y `develop` | ☐ forzada · ☐ acuerdo de equipo |

_Actualiza esta tabla al configurar el repositorio._
