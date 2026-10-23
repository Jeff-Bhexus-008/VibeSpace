# VibeSpace

A self-hostable social entertainment platform: short-form video, head-to-head **Vibe Battles** with
community voting, a **LearnSpace** for educational content, creator analytics, direct messaging and
full moderation tooling.

This repository is **fully independent of Base44** — no Base44 SDKs, authentication, databases, APIs or
server functions are used anywhere in the application. See `docs/INDEPENDENCE_AUDIT.md`.

## Stack

| Layer     | Technology                                                                 |
| --------- | -------------------------------------------------------------------------- |
| Frontend  | React 18, TypeScript, Vite, Tailwind CSS, React Router, TanStack Query     |
| Backend   | Python, FastAPI, Pydantic, SQLAlchemy, Alembic                              |
| Database  | PostgreSQL                                                                  |
| Messaging | Redis (background jobs + cache), WebSockets for live chat                  |
| Media     | S3-compatible object storage, FFmpeg (thumbnails + renditions)            |
| Infra     | Docker / Docker Compose, Render (`render.yaml`)                             |

## Repository layout

```
frontend/    React + TypeScript app (independently runnable)
backend/     FastAPI application, models, migrations, Celery workers, tests
docs/        Independence audit and implementation status
docker-compose.yml   Postgres + Redis + API + worker + frontend dev stack
render.yaml          Render deployment blueprint
.env.example         Every environment variable, with placeholders
```

## Quick start (Docker Compose)

```bash
cp .env.example .env          # then edit values (see below)
docker compose up --build
```

- Frontend: http://localhost:5173
- API: http://localhost:8000 (interactive docs at `/docs`)
- Postgres on `localhost:5432`, Redis on `localhost:6379`

The compose stack runs Postgres, Redis, the API, the Celery worker and the frontend dev server.

## Manual setup (without Docker)

**Backend** — Python 3.11+, FFmpeg installed on the host:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload          # API on :8000
# second terminal:
celery -A app.workers.celery_app worker -l info
```

**Frontend**:

```bash
cd frontend
npm install
npm run dev                           # Vite dev server on :5173
```

Both apps read their configuration from environment variables / `.env` files — nothing is hardcoded.
The frontend expects the API at `VITE_API_BASE_URL` (default `http://localhost:8000/api/v1`).

## Environment variables

See `.env.example` for the complete list with placeholders. The essentials:

| Variable              | Purpose                                              |
| --------------------- | ---------------------------------------------------- |
| `SECRET_KEY`          | Signs JWTs and CSRF tokens — set a long random value |
| `DATABASE_URL`        | Postgres DSN, scheme `postgresql+psycopg://…`        |
| `REDIS_URL`           | Redis connection string                              |
| `S3_*`                | Bucket, keys, endpoint, region for object storage    |
| `FFMPEG_BINARY`       | Path to ffmpeg (`ffmpeg` when on PATH)               |
| `SMTP_*`              | Optional; when unset, verification/reset links are printed in dev mode only |
| `PUBLIC_APP_URL` / `CORS_ORIGINS` | Your frontend origin(s)                   |

**No credentials are hardcoded.** S3 keys, secrets and SMTP passwords only ever come from the
environment.

## Running tests

```bash
# Backend (needs a reachable Postgres for DB-backed tests; otherwise tests are skipped)
cd backend && pytest

# Frontend
cd frontend
npm run typecheck
npm test
```

## Deploying to Render

`render.yaml` at the repo root is a complete blueprint (Postgres, Redis, API, Celery worker, static
frontend). Either use the Render dashboard's "Deploy from repo" with a blueprint, or create the
services manually:

1. **Postgres** — create it, then set `DATABASE_URL` on the API and worker to its *internal*
   connection string, with the scheme replaced by `postgresql+psycopg://` (e.g.
   `postgresql+psycopg://user:pass@host:5432/db`).
2. **Redis** — set `REDIS_URL` from its internal connection string.
3. **API (Docker)** — points at `backend/Dockerfile`, health check `/api/v1/health`. Runs
   `alembic upgrade head` on boot (single instance; for scaled-out setups, run migrations from a
   one-off shell first).
4. **Worker (Docker)** — same image; command `celery -A app.workers.celery_app worker -l info`.
5. **Frontend (Static site)** — build `cd frontend && npm install && npm run build`, publish
   `frontend/dist`; set `VITE_API_BASE_URL` to the API's public URL and `VITE_WS_BASE_URL` to its
   `wss://…/ws` equivalent.
6. **Object storage** — any S3-compatible bucket (AWS S3, Cloudflare R2, Backblaze B2, MinIO). Set the
   `S3_*` variables and configure the bucket's CORS to allow PUT from your frontend origin.
   Never store user uploads on Render's ephemeral disk — the app always routes media through the
   S3-compatible bucket, which is why uploads keep working across deploys.
7. **Secrets** — set `SECRET_KEY` to a strong random value; set `ENVIRONMENT=production`.
8. **Plans** — PostgreSQL and Redis on Render are paid add-ons beyond the free tier (the worker
   service also requires a paid instance type; static sites are free). Set them up once in the
   dashboard when the blueprint prompts for the `sync: false` variables.

Requirements/limits worth knowing:

- Uploads need a real S3-compatible bucket; without it the upload flow refuses to start.
- Video thumbnails/renditions require FFmpeg — it is installed in `backend/Dockerfile`, so the
  Render/Docker path works out of the box.
- Email delivery requires SMTP variables; without them, email verification and password reset fall
  back to development links in the API response (dev only).

## Pushing to GitHub

```bash
cd <your-repo>
git init
git add frontend backend docs docker-compose.yml render.yaml .env.example README.md
git commit -m "VibeSpace: portable FastAPI + React implementation"
git remote add origin git@github.com:<you>/vibespace.git
git push -u origin main
```

`.env` is git-ignored — only `.env.example` (placeholders) is committed, so no secrets can be
pushed. If you exported this repo from a Base44 workspace, the Base44 builder files (`src/`,
`base44/`, root `package.json`, etc.) are not needed by the portable project and can be left out.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `npm run dev` reaches nothing / CORS errors in console | Backend not running or `VITE_API_BASE_URL` wrong; also set `CORS_ORIGINS` to your frontend origin on the backend |
| 401 on every request after login | Cookies blocked — use `http://localhost` (not `127.0.0.1`) so the cookie domain matches, or check browser cookie settings |
| `relation "users" does not exist` | Run `alembic upgrade head` from `backend/` (the API also does this on Docker boot) |
| Upload fails with "storage is not configured" | `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` are missing; for MinIO/R2 also set `S3_ENDPOINT_URL` and `S3_USE_PATH_STYLE` |
| Upload works but video never leaves "processing" | The Celery worker is not running, or FFmpeg is missing on the worker host (`ffmpeg -version`) |
| Emails never arrive | `SMTP_*` not set; in development the API response includes a one-time link instead |
| WebSocket chat falls back to polling | Expected behind proxies without WebSocket support; polling keeps it working |
| `sqlalchemy.exc ArgumentError` on startup | `DATABASE_URL` scheme must be `postgresql+psycopg://` (Render's `postgres://` needs rewriting) |
| Frontend blank after Render deploy | Static-site rewrite missing → keep the `routes` block from `render.yaml` |

## Feature status

Every feature listed in the brief is implemented end-to-end against real API endpoints and database
models — registration/login/profiles, uploads, the Vibe Feed, likes/comments/follows/shares, Vibe
Battles (creation → entries → voting → results → leaderboards), LearnSpace, CreatorSpace analytics,
messaging, notifications, search and moderation. What is deliberately **not** included: monetization
and native mobile builds. Honest per-feature detail lives in `docs/IMPLEMENTATION_STATUS.md`.