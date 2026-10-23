import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Flame, Sparkles, Swords, Trophy, Users } from "lucide-react";

import Avatar from "@/components/ui/Avatar";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import VideoCard from "@/components/VideoCard";
import { EmptyState, SectionTitle, Spinner } from "@/components/ui/Feedback";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { compactNumber, titleCase } from "@/lib/utils";
import type { Challenge, PublicUser, Video } from "@/types/api";

interface TrendingPayload {
  videos: Video[];
  creators: PublicUser[];
  battles: Array<Record<string, unknown>>;
  learn: Video[];
  generated_at: string;
}

export default function Home() {
  const { user } = useAuth();
  const trending = useQuery({
    queryKey: ["discovery", "trending"],
    queryFn: () => api.get<TrendingPayload>("/discovery/trending"),
  });

  return (
    <div className="space-y-12 animate-fade-up">
      <section className="relative overflow-hidden rounded-[2rem] border border-ink-800/80 bg-ink-900/60 p-8 md:p-12">
        <div className="relative z-10 max-w-2xl">
          <span className="vs-chip">
            <Sparkles className="h-3.5 w-3.5 text-violet" /> Social entertainment, built for participation
          </span>
          <h1 className="mt-5 font-display text-4xl font-semibold leading-tight tracking-tight md:text-5xl">
            Where creators battle, communities vote, and skills get shared.
          </h1>
          <p className="mt-4 max-w-xl text-sm leading-relaxed text-haze md:text-base">
            Publish short videos, start a Vibe Battle in any category, vote on entries and follow the
            leaderboards. Everything you see here is served by the platform's own API.
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            {user ? (
              <>
                <Link to="/feed">
                  <Button size="lg">
                    Open the Vibe Feed <ArrowRight className="h-4 w-4" />
                  </Button>
                </Link>
                <Link to="/battles/new">
                  <Button size="lg" variant="secondary">
                    <Swords className="h-4 w-4" /> Start a battle
                  </Button>
                </Link>
              </>
            ) : (
              <>
                <Link to="/register">
                  <Button size="lg">
                    Create your account <ArrowRight className="h-4 w-4" />
                  </Button>
                </Link>
                <Link to="/feed">
                  <Button size="lg" variant="secondary">
                    Watch first
                  </Button>
                </Link>
              </>
            )}
          </div>
        </div>
        <div className="pointer-events-none absolute -right-20 top-1/2 hidden h-72 w-72 -translate-y-1/2 rounded-full bg-violet/20 blur-3xl md:block" />
      </section>

      {trending.isLoading ? (
        <div className="flex justify-center py-12">
          <Spinner className="h-7 w-7" />
        </div>
      ) : trending.data ? (
        <>
          <section>
            <SectionTitle hint={<span className="inline-flex items-center gap-1"><Flame className="h-3.5 w-3.5" /> last 72 hours</span>}>
              Trending videos
            </SectionTitle>
            {trending.data.videos.length > 0 ? (
              <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
                {trending.data.videos.slice(0, 6).map((video) => (
                  <VideoCard key={video.id} video={video} />
                ))}
              </div>
            ) : (
              <EmptyState
                title="No videos published yet"
                description="Once creators upload, trending content appears here automatically."
                action={
                  <Link to="/create">
                    <Button size="sm">Publish the first video</Button>
                  </Link>
                }
              />
            )}
          </section>

          <section className="grid gap-8 lg:grid-cols-[1.4fr_1fr]">
            <div>
              <SectionTitle hint={<span className="inline-flex items-center gap-1"><Swords className="h-3.5 w-3.5" /> live right now</span>}>
                Active battles
              </SectionTitle>
              {trending.data.battles.length > 0 ? (
                <ul className="space-y-3">
                  {trending.data.battles.map((battle) => (
                    <li key={String(battle.id)}>
                      <Link
                        to={`/battles/${battle.id}`}
                        className="flex items-center justify-between gap-4 rounded-2xl border border-ink-800/80 bg-ink-900/60 px-4 py-3 transition hover:border-coral/40"
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium">{String(battle.title)}</p>
                          <p className="text-xs text-haze">
                            {titleCase(String(battle.category))} · {compactNumber(Number(battle.entry_count))} entries
                          </p>
                        </div>
                        <Badge tone="violet">{compactNumber(Number(battle.vote_count))} votes</Badge>
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState title="No open battles" description="Start one and invite the community." />
              )}
            </div>

            <div>
              <SectionTitle hint={<span className="inline-flex items-center gap-1"><Users className="h-3.5 w-3.5" /> by followers</span>}>
                Creators to follow
              </SectionTitle>
              {trending.data.creators.length > 0 ? (
                <ul className="space-y-3">
                  {trending.data.creators.slice(0, 5).map((creator) => (
                    <li key={creator.id} className="flex items-center gap-3 rounded-2xl border border-ink-800/80 bg-ink-900/60 px-4 py-3">
                      <Avatar src={creator.avatar_url} name={creator.display_name ?? creator.username} size="sm" />
                      <div className="min-w-0 flex-1">
                        <Link to={`/u/${creator.username}`} className="block truncate text-sm font-medium hover:text-violet-soft">
                          @{creator.username}
                        </Link>
                        <p className="text-xs text-haze">{compactNumber(creator.follower_count)} followers</p>
                      </div>
                      <Trophy className="h-4 w-4 text-lime" />
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState title="No creators yet" description="Be the first to publish content." />
              )}
            </div>
          </section>

          {trending.data.learn.length > 0 ? (
            <section>
              <SectionTitle hint={<Link to="/learn" className="text-violet-soft hover:underline">LearnSpace</Link>}>
                Learning highlights
              </SectionTitle>
              <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
                {trending.data.learn.slice(0, 3).map((video) => (
                  <VideoCard key={video.id} video={video} />
                ))}
              </div>
            </section>
          ) : null}
        </>
      ) : (
        <EmptyState
          title="The API did not answer"
          description="Check that the backend is running and VITE_API_BASE_URL points at it."
        />
      )}
    </div>
  );
}