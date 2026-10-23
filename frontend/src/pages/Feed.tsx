import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bookmark, Heart, MessageCircle, Send } from "lucide-react";

import Avatar from "@/components/ui/Avatar";
import Button from "@/components/ui/Button";
import VideoPlayer from "@/components/VideoPlayer";
import { EmptyState, ErrorNote, Spinner } from "@/components/ui/Feedback";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { compactNumber, errorMessage, timeAgo } from "@/lib/utils";
import type { Page, Video } from "@/types/api";

const MODES = [
  { value: "for_you", label: "For you" },
  { value: "following", label: "Following" },
  { value: "new", label: "Newest" },
  { value: "trending", label: "Trending" },
] as const;

export default function Feed() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<(typeof MODES)[number]["value"]>("for_you");
  const [cursor, setCursor] = useState<string | null>(null);
  const [accumulated, setAccumulated] = useState<Video[]>([]);
  const [error, setError] = useState<string | null>(null);

  const feed = useQuery({
    queryKey: ["feed", mode, cursor],
    queryFn: () => api.get<Page<Video>>("/feed", { mode, limit: 8, cursor: cursor ?? undefined }),
    enabled: mode !== "following" || Boolean(user),
  });

  // Replace the cache-reset page, append when the cursor advanced.
  const items = cursor === null ? feed.data?.items ?? [] : accumulated;

  async function loadMore() {
    if (!feed.data?.next_cursor) return;
    setAccumulated(items);
    const next = await api.get<Page<Video>>("/feed", { mode, limit: 8, cursor: feed.data.next_cursor });
    setAccumulated((previous) => [...previous, ...next.items]);
    setCursor(feed.data.next_cursor);
  }

  function changeMode(value: (typeof MODES)[number]["value"]) {
    setMode(value);
    setCursor(null);
    setAccumulated([]);
    void queryClient.invalidateQueries({ queryKey: ["feed"] });
  }

  return (
    <div className="space-y-6 animate-fade-up">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">Vibe Feed</h1>
          <p className="mt-1 text-sm text-haze">
            Ranked by engagement, recency and the creators you follow — a page at a time.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {MODES.map((item) => (
            <button
              key={item.value}
              type="button"
              onClick={() => changeMode(item.value)}
              className={`rounded-full border px-3.5 py-1.5 text-xs font-medium transition ${
                mode === item.value
                  ? "border-violet/50 bg-violet/15 text-white"
                  : "border-ink-700/70 bg-ink-850/70 text-haze hover:text-white"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </header>

      {error ? <ErrorNote message={error} /> : null}

      {feed.isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner className="h-7 w-7" />
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          title={mode === "following" ? "Nothing from the creators you follow yet" : "No videos here yet"}
          description={
            mode === "following"
              ? "Follow a few creators and their newest uploads will appear here."
              : "Publish the first video to get the feed moving."
          }
          action={
            <Link to="/create">
              <Button size="sm">Create a video</Button>
            </Link>
          }
        />
      ) : (
        <div className="space-y-8">
          {items.map((video) => (
            <FeedItem
              key={video.id}
              video={video}
              onError={setError}
              onViewed={(viewCount) =>
                setAccumulated((previous) =>
                  previous.map((item) => (item.id === video.id ? { ...item, view_count: viewCount } : item)),
                )
              }
            />
          ))}

          {feed.data?.has_more ? (
            <div className="flex justify-center">
              <Button variant="secondary" loading={feed.isFetching} onClick={() => void loadMore()}>
                Load more
              </Button>
            </div>
          ) : (
            <p className="pb-6 text-center text-xs text-haze">You have reached the end of this feed.</p>
          )}
        </div>
      )}
    </div>
  );
}

function FeedItem({
  video,
  onViewed,
  onError,
}: {
  video: Video;
  onViewed: (viewCount: number) => void;
  onError: (message: string | null) => void;
}) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [liked, setLiked] = useState(Boolean(video.is_liked));
  const [saved, setSaved] = useState(Boolean(video.is_saved));
  const [likeCount, setLikeCount] = useState(video.like_count);

  const like = useMutation({
    mutationFn: () => (liked ? api.del(`/videos/${video.id}/like`) : api.post(`/videos/${video.id}/like`)),
    onSuccess: () => {
      setLiked((value) => !value);
      setLikeCount((value) => value + (liked ? -1 : 1));
      onError(null);
    },
    onError: (mutationError) => onError(errorMessage(mutationError)),
  });

  const save = useMutation({
    mutationFn: () =>
      saved ? api.del(`/videos/${video.id}/save`) : api.post(`/videos/${video.id}/save`, { collection: "Watch later" }),
    onSuccess: () => {
      setSaved((value) => !value);
      void queryClient.invalidateQueries({ queryKey: ["videos", "saved"] });
    },
    onError: (mutationError) => onError(errorMessage(mutationError)),
  });

  const share = useMutation({
    mutationFn: () => api.post<{ share_count: number }>(`/videos/${video.id}/share`, { channel: "link" }),
    onSuccess: async () => {
      const url = `${window.location.origin}/watch/${video.id}`;
      try {
        await navigator.clipboard.writeText(url);
      } catch {
        /* clipboard blocked — the link is still shown in the address bar */
      }
    },
  });

  return (
    <article className="overflow-hidden rounded-[2rem] border border-ink-800/80 bg-ink-900/50">
      <div className="flex flex-col gap-4 p-4 lg:flex-row">
        <VideoPlayer video={video} onViewed={onViewed} className="aspect-video w-full lg:w-[38rem]" />

        <div className="flex min-w-0 flex-1 flex-col">
          <Link to={`/watch/${video.id}`} className="font-display text-lg font-semibold leading-snug hover:text-violet-soft">
            {video.title}
          </Link>
          <p className="mt-2 line-clamp-3 text-sm text-haze">{video.description ?? "No description provided."}</p>

          <div className="mt-4 flex items-center gap-3">
            <Avatar src={video.author?.avatar_url} name={video.author?.display_name ?? video.author?.username} size="sm" />
            <div className="min-w-0">
              <Link to={`/u/${video.author?.username}`} className="block truncate text-sm hover:text-violet-soft">
                @{video.author?.username}
              </Link>
              <p className="text-[11px] text-haze">
                {compactNumber(video.author?.follower_count ?? 0)} followers · {timeAgo(video.published_at)}
              </p>
            </div>
          </div>

          <div className="mt-auto flex items-center gap-4 pt-5 text-sm text-haze">
            <button
              type="button"
              className={`inline-flex items-center gap-2 transition ${liked ? "text-coral" : "hover:text-white"}`}
              onClick={() => (user ? like.mutate() : onError("Sign in to like videos."))}
              aria-pressed={liked}
            >
              <Heart className={`h-5 w-5 ${liked ? "fill-current" : ""}`} /> {compactNumber(likeCount)}
            </button>
            <Link to={`/watch/${video.id}`} className="inline-flex items-center gap-2 hover:text-white">
              <MessageCircle className="h-5 w-5" /> {compactNumber(video.comment_count)}
            </Link>
            <button
              type="button"
              className={`inline-flex items-center gap-2 transition ${saved ? "text-lime" : "hover:text-white"}`}
              onClick={() => (user ? save.mutate() : onError("Sign in to save videos."))}
              aria-pressed={saved}
            >
              <Bookmark className={`h-5 w-5 ${saved ? "fill-current" : ""}`} /> {saved ? "Saved" : "Save"}
            </button>
            <button
              type="button"
              className="inline-flex items-center gap-2 hover:text-white"
              onClick={() => share.mutate()}
            >
              <Send className="h-5 w-5" /> Share
            </button>
          </div>
        </div>
      </div>
    </article>
  );
}