import {
  CheckCircle2,
  Clapperboard,
  Database,
  Film,
  GitBranch,
  Rocket,
  Server,
  ShieldCheck,
  Terminal,
  Zap,
} from "lucide-react";

const stack = [
  { icon: Film, title: "frontend/", body: "React 18 + TypeScript + Vite + Tailwind + React Router + TanStack Query." },
  { icon: Server, title: "backend/", body: "FastAPI + Pydantic + SQLAlchemy + Alembic, modular routes, workers." },
  { icon: Database, title: "PostgreSQL", body: "Normalized models, FKs, unique constraints, indexes, one migration set." },
  { icon: Zap, title: "Redis + workers", body: "Celery jobs for FFmpeg probing, thumbnails, retries, job status." },
  { icon: ShieldCheck, title: "Auth", body: "Argon2 hashing, JWT access + rotating refresh cookies, role-based access." },
  { icon: GitBranch, title: "Deploy", body: "docker-compose for local, render.yaml blueprint, .env.example only." },
];

const runSteps = [
  "cp .env.example .env  → fill in the secrets",
  "docker compose up -d db redis",
  "cd backend && alembic upgrade head && uvicorn app.main:app --reload",
  "cd backend && celery -A app.workers.celery_app worker -l info",
  "cd frontend && npm install && npm run dev",
];

const shipped = [
  "Backend: auth, users/profiles, media uploads with presigned URLs, videos, feed ranking, likes, comments, follows, saves, reports",
  "Vibe Battles: challenges, formats, state machine, entries, fair voting with duplicate-vote constraints, results, leaderboards",
  "LearnSpace categories, search and discovery, notifications, direct messaging with WebSocket + polling fallback",
  "Moderation and admin APIs with audit log, plus backend test suite and frontend tests",
];

export default function ProjectHandoff() {
  return (
    <div className="min-h-screen bg-[hsl(240_20%_5%)] text-[hsl(240_15%_94%)] font-body">
      <div className="mx-auto max-w-5xl px-6 py-14 md:py-20">
        <span className="inline-flex items-center gap-2 rounded-full border border-[hsl(255_60%_30%)] bg-[hsl(255_40%_14%)] px-3 py-1 text-xs tracking-wide text-[hsl(255_80%_82%)]">
          <Rocket className="h-3.5 w-3.5" /> Portable project generated
        </span>

        <h1 className="mt-6 font-display text-4xl font-semibold tracking-tight md:text-6xl">
          VibeSpace
        </h1>
        <p className="mt-4 max-w-2xl text-base leading-relaxed text-[hsl(240_10%_68%)] md:text-lg">
          Social entertainment and video-sharing platform, written as a self-hostable
          codebase: React + TypeScript frontend, FastAPI + PostgreSQL backend, Redis
          workers, S3-compatible media storage and Render deployment files. Nothing here
          depends on Base44 at runtime — this preview is only the workspace shell.
        </p>

        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {stack.map(({ icon: Icon, title, body }) => (
            <div
              key={title}
              className="rounded-2xl border border-[hsl(240_12%_16%)] bg-[hsl(240_16%_8%)] p-5"
            >
              <Icon className="h-5 w-5 text-[hsl(255_80%_72%)]" />
              <h2 className="mt-3 font-heading text-sm font-semibold tracking-wide">{title}</h2>
              <p className="mt-1.5 text-sm leading-relaxed text-[hsl(240_10%_64%)]">{body}</p>
            </div>
          ))}
        </div>

        <div className="mt-14 grid gap-10 md:grid-cols-2">
          <section>
            <h3 className="flex items-center gap-2 font-heading text-sm font-semibold uppercase tracking-wider text-[hsl(240_10%_60%)]">
              <Terminal className="h-4 w-4" /> Run it locally
            </h3>
            <pre className="mt-4 overflow-x-auto rounded-2xl border border-[hsl(240_12%_16%)] bg-[hsl(240_18%_7%)] p-4 text-xs leading-6 text-[hsl(255_40%_84%)]">
{runSteps.join("\n")}
            </pre>
            <p className="mt-3 text-sm text-[hsl(240_10%_60%)]">
              Full instructions, migrations, storage, FFmpeg and deploy steps are in the
              README at the repository root.
            </p>
          </section>

          <section>
            <h3 className="flex items-center gap-2 font-heading text-sm font-semibold uppercase tracking-wider text-[hsl(240_10%_60%)]">
              <Clapperboard className="h-4 w-4" /> Delivered scope
            </h3>
            <ul className="mt-4 space-y-3">
              {shipped.map((item) => (
                <li key={item} className="flex gap-3 text-sm leading-relaxed text-[hsl(240_10%_70%)]">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-[hsl(160_70%_52%)]" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </div>
    </div>
  );
}