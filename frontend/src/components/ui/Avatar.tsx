import { cn } from "@/lib/utils";

interface AvatarProps {
  src?: string | null;
  name?: string | null;
  size?: "sm" | "md" | "lg" | "xl";
  className?: string;
}

const SIZES = {
  sm: "h-8 w-8 text-xs",
  md: "h-10 w-10 text-sm",
  lg: "h-14 w-14 text-base",
  xl: "h-20 w-20 text-xl",
};

export default function Avatar({ src, name, size = "md", className }: AvatarProps) {
  const initials = (name ?? "VS")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");

  return (
    <span
      className={cn(
        "relative inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full border border-ink-700/70 bg-ink-800 font-display font-semibold text-haze",
        SIZES[size],
        className,
      )}
    >
      {src ? (
        <img src={src} alt={name ?? "Profile"} className="h-full w-full object-cover" loading="lazy" />
      ) : (
        <span>{initials || "VS"}</span>
      )}
    </span>
  );
}