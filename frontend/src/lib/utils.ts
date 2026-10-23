import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function compactNumber(value: number | null | undefined): string {
  const amount = value ?? 0;
  if (amount < 1000) return String(amount);
  if (amount < 1_000_000) return `${(amount / 1000).toFixed(amount < 10_000 ? 1 : 0)}K`;
  return `${(amount / 1_000_000).toFixed(1)}M`;
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "just now";
  const then = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`).getTime();
  const seconds = Math.max(1, Math.floor((Date.now() - then) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 604_800) return `${Math.floor(seconds / 86_400)}d ago`;
  if (seconds < 2_592_000) return `${Math.floor(seconds / 604_800)}w ago`;
  return new Date(then).toLocaleDateString();
}

export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds) return "--:--";
  const total = Math.round(seconds);
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

export function countdown(target: string | null | undefined, secondsRemaining?: number | null): string {
  let remaining = secondsRemaining ?? null;
  if (remaining === null && target) {
    remaining = Math.max(0, Math.floor((new Date(target).getTime() - Date.now()) / 1000));
  }
  if (remaining === null) return "No deadline";
  if (remaining <= 0) return "Closed";
  const days = Math.floor(remaining / 86_400);
  const hours = Math.floor((remaining % 86_400) / 3600);
  const minutes = Math.floor((remaining % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h left`;
  if (hours > 0) return `${hours}h ${minutes}m left`;
  return `${minutes}m left`;
}

export function titleCase(value: string | null | undefined): string {
  if (!value) return "";
  return value
    .replace(/[_-]+/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(" ");
}

export function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return "Something went wrong. Please try again.";
}