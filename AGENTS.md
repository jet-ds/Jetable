# Repository Guidelines

## Project Structure & Module Organization
The project is split into two workspaces: the Next.js 14 front end in `apps/web/` and the FastAPI service in `apps/api/`. Shared React components sit under `apps/web/components/`, while hooks and context live in `apps/web/hooks/` and `apps/web/contexts/`. Static assets are stored in `assets/`, with end-user data and SQLite backups in `data/`. Automation helpers for env setup, database tasks, and cleanup live in the root `scripts/` directory.

## Build, Test, and Development Commands
Run `npm install` from the repository root to hydrate both workspaces and prepare the Python virtualenv. Use `npm run dev` for the standard loop; it boots both `scripts/run-api.js` and `scripts/run-web.js`. Start individual stacks with `npm run dev:api` or `npm run dev:web`. Production checks rely on workspace commands: `npm run build --workspace apps/web` compiles the UI, and `npm run start --workspace apps/web` serves the bundle. Database helpers include `npm run db:backup` (copies `data/cc.db` into `data/backups/`) and `npm run db:reset` (recreates the local database). If dependencies drift, `npm run clean` clears Node modules and virtualenvs.

## Coding Style & Naming Conventions
Follow the two-space indentation and single-quote imports used in `apps/web/components/ChatLog.tsx`. Prefer functional components with PascalCase names; colocate related hooks in `apps/web/hooks/useThing.ts`. Tailwind classes should be grouped logically (layout → spacing → typography) to keep diffs readable. Python modules follow PEP 8 with four-space indents; keep router definitions under `app/api/` and update `app/models/__init__.py` when introducing new ORM models.

## Testing Guidelines
There is no formal automated suite today, so treat `npm run build --workspace apps/web` and `curl http://localhost:8080/health` as minimum regression checks. Add focused tests when fixing bugs: place Playwright specs under `apps/web/tests/` and FastAPI tests under `apps/api/tests/`, and expose a script before merging. Name test files `<feature>.spec.ts` (web) or `test_<module>.py` (API) for consistent discovery.

## Commit & Pull Request Guidelines
Commits should be present-tense and imperative (`Handle cancelled Vercel deployments`), mirroring the existing history. Keep subject lines under ~70 characters and add a short body when touching both API and UI. Pull requests must describe user-facing changes, list verification steps (`npm run build`, `curl /health`), and attach screenshots or Loom links for UI tweaks. Link relevant issues and call out breaking changes or manual database steps explicitly.
