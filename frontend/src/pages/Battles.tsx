import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { PlusCircle, Swords } from "lucide-react";

import Button from "@/components/ui/Button";
import ChallengeCard from "@/components/ChallengeCard";
import { EmptyState, Spinner } from "@/components/ui/Feedback";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { titleCase } from "@/lib/utils";
import type { Challenge, ChallengeStatus, Page } from "@/types/api";

const STATUS_FILTERS: Array<{ value: ChallengeStatus | ""; label: string }> = [
  { value: "", label: "All" },
  { value: "open", label: "Open" },
  { value: "active", label: "In progress" },
  { value: "voting", label: "Voting" },
  { value: "completed", label: "Completed" },
];

const CATEGORIES = ["", "dance", "comedy", "music", "sports", "gaming", "coding", "education", "art", "fitness", "creativity"];

export default function Battles() {
  const { user } = useAuth();
  const [status, setStatus] = useState<ChallengeStatus | "">("");
  const [category, setCategory] = useState("");
  const [scope, setScope] = useState<"all" | "mine" | "participating">("all");

  const battles = useQuery({
    queryKey: ["battles", status, category, scope],
    queryFn: () =>
      api.get<Page<Challenge>>("/challenges", {
        limit: 24,
        status: status || undefined,
        category: category || undefined,
        mine: scope === "mine" ? true : undefined,
        participating: scope === "participating" ? true : undefined,
      }),
    enabled: scope === "all" || Boolean(user),
  });

  return (
    <div className="space-y-8 animate-fade-up">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Swords className="h-6 w-6 text-coral" />
            <h1 className="font-display text-2xl font-semibold tracking-tight">Vibe Battles</h1>
          </div>
          <p className="mt-1 max-w-2xl text-sm text-haze">
            Head-to-head duels, open challenges and community competitions — with server-verified voting
            and official results.
          </p>
        </div>
        {user ? (
          <Link to="/battles/new">
            <Button>
              <PlusCircle className="h-4 w-4" /> Start a battle
            </Button>
          </Link>
        ) : (
          <Link to="/login">
            <Button variant="secondary">Sign in to compete</Button>
          </Link>
        )}
      </header>

      <div className="space-y-3">
        <div className="flex flex-wrap gap-2">
          {STATUS_FILTERS.map((item) => (
            <button
              key={item.value || "all"}
              type="button"
              onClick={() => setStatus(item.value)}
              className={`rounded-full border px-3.5 py-1.5 text-xs transition ${
                status === item.value ? "border-coral/50 bg-coral/15 text-white" : "border-ink-700/70 text-haze"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {CATEGORIES.map((item) => (
            <button
              key={item || "every"}
              type="button"
              onClick={() => setCategory(item)}
              className={`rounded-full border px-3 py-1 text-[11px] transition ${
                category === item ? "border-violet/50 bg-violet/15 text-white" : "border-ink-700/70 text-haze"
              }`}
            >
              {item ? titleCase(item) : "Every category"}
            </button>
          ))}
          {user ? (
            <div className="ml-auto flex gap-2">
              {(["all", "mine", "participating"] as const).map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setScope(value)}
                  className={`rounded-full border px-3 py-1 text-[11px] transition ${
                    scope === value ? "border-lime/50 bg-lime/15 text-white" : "border-ink-700/70 text-haze"
                  }`}
                >
                  {value === "all" ? "Everyone's" : value === "mine" ? "I organise" : "I joined"}
                </button>
              ))}
            </div>
          ) : null}
        </div>
      </div>

      {battles.isLoading ? (
        <div className="flex justify-center py-14">
          <Spinner className="h-7 w-7" />
        </div>
      ) : battles.data && battles.data.items.length > 0 ? (
        <div className="grid gap-5 md:grid-cols-2">
          {battles.data.items.map((challenge) => (
            <ChallengeCard key={challenge.id} challenge={challenge} />
          ))}
        </div>
      ) : (
        <EmptyState
          title="No battles here"
          description="Try another filter, or start the first challenge in this category."
          icon={<Swords className="h-8 w-8" />}
          action={
            <Link to={user ? "/battles/new" : "/login"}>
              <Button size="sm">{user ? "Start a battle" : "Sign in to start one"}</Button>
            </Link>
          }
        />
      )}
    </div>
  );
}