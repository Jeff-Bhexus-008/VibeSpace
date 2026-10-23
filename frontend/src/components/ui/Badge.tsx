import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

type Tone = "neutral" | "violet" | "lime" | "coral" | "sky" | "danger";

const TONES: Record<Tone, string> = {
  neutral: "border-ink-700/70 bg-ink-850/80 text-haze",
  violet: "border-violet/40 bg-violet/15 text-violet-soft",
  lime: "border-lime/40 bg-lime/15 text-lime",
  coral: "border-coral/40 bg-coral/15 text-coral",
  sky: "border-sky/40 bg-sky/15 text-sky",
  danger: "border-danger/40 bg-danger/15 text-danger",
};

export default function Badge({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}