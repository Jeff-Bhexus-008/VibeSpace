# Migrations

VibeSpace uses Alembic with SQLAlchemy models in `app/models/`.

## Local

```bash
cd backend
export DATABASE_URL=postgresql+psycopg://vibespace:vibespace@localhost:5432/vibespace
alembic upgrade head          # apply every migration
alembic downgrade -1          # roll the last one back
alembic current               # show the applied revision
```

## Production / Render

Migrations run as part of the deployment command (`alembic upgrade head && uvicorn …`)
or from a one-off shell:

```bash
alembic upgrade head
```

Rules of thumb:

- Never edit a migration that has already run in production — add a new revision.
- Keep migrations backwards compatible with the previous app version so a rollback of the
  web service does not break the database.
- `alembic upgrade head` takes an advisory lock; run it once per release, not from every
  worker.

## Creating a new revision

```bash
alembic revision --autogenerate -m "add video series table"
```

Review the generated file before committing: autogenerate does not detect data migrations
or changes to `postgresql_where` partial indexes reliably.