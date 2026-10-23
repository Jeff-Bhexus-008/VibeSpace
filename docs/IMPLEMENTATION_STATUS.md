# Implementation Status

Working features, known gaps, external requirements — stated plainly. Anything not listed as
implemented should be treated as not built.

## Implemented end-to-end (real endpoints, real database models)

| Feature | Notes |
| --- | --- |
| Registration / login / sessions | Email+password, Argon2id hashing, HttpOnly JWT access cookie, rotating refresh sessions with reuse detection, logout-all, email verification, password reset/change |
| Profiles | Display name, bio, avatar/cover upload, links, private profiles, follow/unfollow, block |
| Video upload | Presigned direct-to-storage PUT, server-side content sniffing, Celery/FFmpeg processing (thumbnail, duration, renditions), draft/publish lifecycle |
| Vibe Feed | Ranked feed (engagement + recency + follows), following/newest/trending modes, cursor pagination, view counting with 30-minute dedupe |
| Social | Likes, comments with one-level replies, saves/collections, share counting, follows |
| Vibe Battles | Creation (4 formats), state machine with validated transitions, deadline enforcement (API-side), entries, server-verified voting (DB-unique per voter/entry), provisional and finalized standings, disqualification, disputes, invitations, leaderboards |
| LearnSpace | Educational flag + topic taxonomy, dedicated browsing/search |
| CreatorSpace | Per-video metrics (views/unique views/likes/comments), engagement rate, time-series analytics, drafts, moderation notices |
| Messaging | 1:1 conversations, WebSocket delivery with REST polling fallback, read receipts, privacy/block rules |
| Notifications | Follows, likes, comments/replies, battle events, messages; unread counts, mark-read |
| Search & discovery | Cross-entity search (users/videos/battles/learn), trending, leaderboards, categories |
| Moderation & admin | Reports queue with resolution actions, suspicious-vote detection, suspend/reinstate, moderation action history, audit log, platform stats, category management |

## Backend tests

`backend/tests/` — auth (register/login/refresh/CSRF), social (likes/comments/follows), challenges &
voting (deadlines, vote limits, state transitions), uploads (ticket/presign flow), moderation.
DB-backed tests are skipped automatically when no test database is reachable.

## Frontend tests

`vitest` suites: API client (URL building, CSRF header, error envelopes, 401→refresh→retry),
shared formatters, and the VideoCard interaction (renders metadata; like button calls the real
endpoint and reflects the new state). Not a full E2E suite — screens are exercised by their
integration with the tested client layer.

## Known gaps (deliberate scope decisions)

- **Monetization** — not built (no payments, tipping or subscriptions).
- **Native mobile apps** — not included; the responsive web app works on mobile browsers.
- **Federation / SSO / OAuth login providers** — not built; email+password only.
- **Live streaming** — not built; uploads are the only media intake.
- **Local-disk media storage** — not built; S3-compatible storage is required for uploads.
- **Email without SMTP** — verification/reset links are returned in dev-mode API responses only;
  production requires SMTP variables.
- **Complex abuse defences** (CAPTCHA, ML spam scoring) — not built; rate limiting and
  moderation tooling are in place.

## External services required to run

1. PostgreSQL 14+
2. Redis
3. S3-compatible object storage (AWS S3, Cloudflare R2, Backblaze B2, MinIO…)
4. FFmpeg binary (bundled in `backend/Dockerfile`; install manually for bare-metal runs)
5. SMTP server (optional — see above)

## Deploying on Render — checklist

1. Create the blueprint from `render.yaml` (or replicate the services manually).
2. Set `DATABASE_URL` to the Postgres **internal** connection string with scheme
   `postgresql+psycopg://`.
3. Set `REDIS_URL` from the Redis internal connection string.
4. Set a strong `SECRET_KEY`, `CORS_ORIGINS` (frontend URL), `TRUSTED_HOSTS` (API hostname).
5. Set the `S3_*` variables and add bucket CORS allowing PUT from your frontend origin.
6. API health: `/api/v1/health` (liveness) and `/api/v1/health/ready` (database/redis/storage).
7. Frontend static site: build `frontend/`, publish `dist/`, set `VITE_API_BASE_URL` and
   `VITE_WS_BASE_URL` to the API's public URLs.
8. First deploy: migrations run automatically on API boot (`alembic upgrade head`).
9. Create an admin: register normally, then promote the account in Postgres
   (`UPDATE app_users SET role='admin' WHERE email='you@example.com';`) — role changes via the API
   are restricted and audited.