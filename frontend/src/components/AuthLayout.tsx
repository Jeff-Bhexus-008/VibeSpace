import type { ReactNode } from "react";
import { Link } from "react-router-dom";

/** Shared chrome for the sign-in / sign-up screens. */
export default function AuthLayout({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        <Link to="/" className="mb-8 flex items-center justify-center gap-2 font-display text-2xl font-semibold">
          <span className="grid h-10 w-10 place-items-center rounded-2xl bg-gradient-to-br from-violet to-coral text-sm">
            VS
          </span>
          VibeSpace
        </Link>
        <div className="animate-fade-up rounded-[2rem] border border-ink-800/80 bg-ink-900/70 p-7 shadow-panel backdrop-blur">
          <h1 className="font-display text-xl font-semibold tracking-tight">{title}</h1>
          {subtitle ? <p className="mt-1 text-sm text-haze">{subtitle}</p> : null}
          <div className="mt-6">{children}</div>
        </div>
      </div>
    </div>
  );
}