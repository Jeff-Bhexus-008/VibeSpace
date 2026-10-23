import type { Config } from "tailwindcss";

export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "hsl(var(--ink-950))",
          900: "hsl(var(--ink-900))",
          850: "hsl(var(--ink-850))",
          800: "hsl(var(--ink-800))",
          700: "hsl(var(--ink-700))",
        },
        haze: "hsl(var(--haze))",
        violet: {
          DEFAULT: "hsl(var(--vibe-violet))",
          soft: "hsl(var(--vibe-violet-soft))",
          deep: "hsl(var(--vibe-violet-deep))",
        },
        lime: "hsl(var(--vibe-lime))",
        coral: "hsl(var(--vibe-coral))",
        sky: "hsl(var(--vibe-sky))",
        danger: "hsl(var(--danger))",
        success: "hsl(var(--success))",
      },
      fontFamily: {
        display: ["var(--font-display)"],
        sans: ["var(--font-body)"],
        mono: ["var(--font-mono)"],
      },
      borderRadius: {
        xl: "1rem",
        "2xl": "1.25rem",
        "3xl": "1.75rem",
      },
      boxShadow: {
        glow: "0 0 0 1px hsl(var(--vibe-violet) / 0.35), 0 18px 60px -30px hsl(var(--vibe-violet) / 0.65)",
        panel: "0 24px 60px -40px hsl(var(--ink-950) / 0.9)",
      },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(12px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-soft": {
          "0%, 100%": { opacity: "0.55" },
          "50%": { opacity: "1" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.4s cubic-bezier(0.22, 1, 0.36, 1) both",
        "pulse-soft": "pulse-soft 2.4s ease-in-out infinite",
        shimmer: "shimmer 1.6s infinite",
      },
    },
  },
  plugins: [],
} satisfies Config;