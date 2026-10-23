import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";

import Avatar from "@/components/ui/Avatar";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import VideoCard from "@/components/VideoCard";
import { EmptyState, SectionTitle, Spinner } from "@/components/ui/Feedback";
import { Input } from "@/components/ui/Input";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { compactNumber, titleCase } from "@/lib/utils";
import type { Challenge, Page, PublicUser, Video } from "@/types/api";

const TABS = [
  { value: "all", label: "Everything" },
  { value: "videos", label: "Videos" },
  { value: "users", label: "Creators" },
  { value: "challenges", label: "Battles" },
] as const;

const LEADERBOARDS = ["creators", "videos", "battles", "winners", "participation"] as const;

interface SearchResult {
  query: string;
  users?: Page<PublicUser>;
  videos?: Page<Video>;
  challenges?: { items: Challenge[]; has_more: boolean };
}

export default function Explore() {
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [tab, setTab] = useState<(typeof TABS)[number]["value"]>("all");
  const [board, setBoard] = useState<(typeof LEADERBOARDS)[number]>("creators");

  const search = useQuery({
    queryKey: ["search", submitted, tab],
    queryFn: () => api.get<SearchResult>("/search", { q: submitted, type: tab, limit: 12 }),
    enabled: submitted.length > 0,
  });

  const trending = useQuery({
    queryKey: ["discovery", "trending"],
    queryFn: () => api.get<{ videos: Video[] }>("/discovery/trending"),
  });

  const leaderboard = useQuery({
    queryKey: ["leaderboard", board],
    queryFn: () => api.get<{ scope: string; is_final: boolean; note: string; items: Array<Record<string, unknown>> }>(
      `/leaderboards/${board}`,
      { limit: 10 },
    ),
  });

  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: () => api.get<{ items: Array<{ slug: string; label: string; kind: string }> }>("/categories"),
  });

  return (
    <div className="space-y-10 animate-fade-up">
      <header className="space-y-4">
        <h1 className="font-display text-2xl font-semibold tracking-tight">Explore</h1>
        <form
          className="flex flex-col gap-3 sm:flex-row"
          onSubmit={(event) => {
            event.preventDefault();
            setSubmitted(query.trim());
          }}
        >
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-haze" />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search creators, videos, battles or skills"
              className="pl-10"
            />
          </div>
          <Button type="submit" disabled={query.trim().length === 0}>
            Search
          </Button>
        </form>
        <div className="flex flex-wrap gap-2">
          {TABS.map((item) => (
            <button
              key={item.value}
              type="button"
              onClick={() => setTab(item.value)}
              className={`rounded-full border px-3.5 py-1.5 text-xs transition ${
                tab === item.value ? "border-violet/50 bg-violet/15 text-white" : "border-ink-700/70 text-haze"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </header>

      {submitted ? (
        <section>
          <SectionTitle hint={search.data ? `${search.data.videos?.items.length ?? 0} videos` : undefined}>
            Results for “{submitted}”
          </SectionTitle>
          {search.isLoading ? (
            <div className="flex justify-center py-10">
              <Spinner />
            </div>
          ) : search.data ? (
            <div className="space-y-8">
              {search.data.videos && search.data.videos.items.length > 0 ? (
                <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
                  {search.data.videos.items.map((video) => (
                    <VideoCard key={video.id} video={video} />
                  ))}
                </div>
              ) : null}

              {search.data.users && search.data.users.items.length > 0 ? (
                <Card>
                  <p className="mb-3 text-sm font-medium">Creators</p>
                  <ul className="divide-y divide-ink-800/70">
                    {search.data.users.items.map((creator) => (
                      <li key={creator.id} className="flex items-center gap-3 py-3">
                        <Avatar src={creator.avatar_url} name={creator.display_name ?? creator.username} size="sm" />
                        <Link to={`/u/${creator.username}`} className="flex-1 truncate text-sm hover:text-violet-soft">
                          @{creator.username}
                        </Link>
                        <span className="text-xs text-haze">{compactNumber(creator.follower_count)} followers</span>
                      </li>
                    ))}
                  </ul>
                </Card>
              ) : null}

              {search.data.challenges && search.data.challenges.items.length > 0 ? (
                <Card>
                  <p className="mb-3 text-sm font-medium">Battles</p>
                  <ul className="space-y-2">
                    {search.data.challenges.items.map((challenge) => (
                      <li key={challenge.id}>
                        <Link
                          to={`/battles/${challenge.id}`}
                          className="flex items-center justify-between rounded-2xl border border-ink-800/70 px-4 py-3 text-sm hover:border-coral/40"
                        >
                          <span className="truncate">{challenge.title}</span>
                          <span className="text-xs text-haze">{titleCase(challenge.status)}</span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </Card>
              ) : null}

              {!search.data.videos?.items.length && !search.data.users?.items.length && !search.data.challenges?.items.length ? (
                <EmptyState title="No matches" description="Try a different keyword, or browse the categories below." />
              ) : null}
            </div>
          ) : null}
        </section>
      ) : (
        <section>
          <SectionTitle hint="curated from real activity">Trending now</SectionTitle>
          {trending.isLoading ? (
            <div className="flex justify-center py-10">
              <Spinner />
            </div>
          ) : trending.data && trending.data.videos.length > 0 ? (
            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {trending.data.videos.slice(0, 9).map((video) => (
                <VideoCard key={video.id} video={video} />
              ))}
            </div>
          ) : (
            <EmptyState title="Nothing trending yet" description="Publish or watch a few videos to warm this up." />
          )}
        </section>
      )}

      <section>
        <SectionTitle
          hint={
            <div className="flex flex-wrap gap-2">
              {LEADERBOARDS.map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setBoard(item)}
                  className={`rounded-full border px-3 py-1 text-[11px] transition ${
                    board === item ? "border-lime/50 bg-lime/15 text-white" : "border-ink-700/70 text-haze"
                  }`}
                >
                  {titleCase(item)}
                </button>
              ))}
            </div>
          }
        >
          Leaderboards
        </SectionTitle>
        {leaderboard.isLoading ? (
          <div className="flex justify-center py-8">
            <Spinner />
          </div>
        ) : leaderboard.data ? (
          <Card>
            <p className="mb-4 text-xs text-haze">
              {leaderboard.data.note} {leaderboard.data.is_final ? "" : "(provisional)"}
            </p>
            <ol className="space-y-2">
              {leaderboard.data.items.map((row) => (
                <li
                  key={String(row.rank)}
                  className="flex items-center gap-3 rounded-2xl border border-ink-800/70 px-4 py-2.5 text-sm"
                >
                  <span className="w-6 font-display text-haze">#{String(row.rank)}</span>
                  <span className="flex-1 truncate">
                    {String(
                      (row.creator as PublicUser | undefined)?.username
                        ? `@${(row.creator as PublicUser).username}`
                        : row.title ?? row.winning_entry_title ?? row.challenge_id ?? "",
                    )}
                  </span>
                  <span className="text-xs text-haze">
                    {compactNumber(
                      Number(row.score ?? row.like_count ?? row.vote_count ?? row.entries ?? 0),
                    )}
                  </span>
                </li>
              ))}
              {leaderboard.data.items.length === 0 ? (
                <li className="rounded-2xl border border-dashed border-ink-700/70 px-4 py-6 text-center text-xs text-haze">
                  Not enough data yet to rank this board.
                </li>
              ) : null}
            </ol>
          </Card>
        ) : null}
      </section>

      <section>
        <SectionTitle hint="categories managed in the admin console">Browse categories</SectionTitle>
        <div className="flex flex-wrap gap-2">
          {(categories.data?.items ?? []).map((category) => (
            <span key={`${category.kind}-${category.slug}`} className="vs-chip">
              {category.label}
            </span>
          ))}
        </div>
      </section>
    </div>
  );
}