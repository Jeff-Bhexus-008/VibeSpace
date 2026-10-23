import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Bookmark, Heart, MessageCircle, Play } from "lucide-react";

import Avatar from "@/components/ui/Avatar";
import Badge from "@/components/ui/Badge";
import { api } from "@/lib/api";
import { compactNumber, formatDuration, timeAgo } from "@/lib/utils";
import type { Video } from "@/types/api";

/** Grid card used on Home, Explore, LearnSpace, a creator profile and saved lists. */
export default function VideoCard({ video }: { video: Video }) {
  const queryClient = useQueryClient();
  const [liked, setLiked] = useState(Boolean(video.is_liked));
  const [saved, setSaved] = useState(Boolean(video.is_saved));
  const [likeCount, setLikeCount] = useState(video.like_count);

  const likeMutation = useMutation({
    mutationFn: () => (liked ? api.del(`/videos/${video.id}/like`) : api.post(`/videos/${video.id}/like`)),
    onSuccess: () => {
      setLiked((value) => !value);
      setLikeCount((value) => value + (liked ? -1 : 1));
      void queryClient.invalidateQueries({ queryKey: ["feed"] });
    },
  });

  const saveMutation = useMutation({
    mutationFn: () =>
      saved ? api.del(`/videos/${video.id}/save`) : api.post(`/videos/${video.id}/save`, { collection: "Watch later" }),
    onSuccess: () => setSaved((value) => !value),
  });

  return (
    <article className="group overflow-hidden rounded-3xl border border-ink-800/80 bg-ink-900/60 transition hover:border-violet/40">
      <Link to={`/watch/${video.id}`} className="block">
        <div className="relative aspect-video overflow-hidden bg-ink-850">
          {video.thumbnail_url ? (
            <img
              src={video.thumbnail_url}
              alt={video.title}
              loading="lazy"
              className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]"
            />
          ) : (
            <div className="grid h-full place-items-center text-haze">
              <Play className="h-8 w-8" />
            </div>
          )}
          <div className="absolute bottom-2 right-2 rounded-lg bg-black/70 px-2 py-1 text-[11px] font-medium">
            {formatDuration(video.duration_seconds)}
          </div>
          {video.is_learn_content ? (
            <div className="absolute left-2 top-2">
              <Badge tone="sky">Learn</Badge>
            </div>
          ) : null}
        </div>
      </Link>

      <div className="space-y-3 p-4">
        <Link to={`/watch/${video.id}`} className="line-clamp-2 font-display text-sm font-semibold leading-snug">
          {video.title}
        </Link>

        <div className="flex items-center gap-2">
          <Avatar src={video.author?.avatar_url} name={video.author?.display_name ?? video.author?.username} size="sm" />
          <Link to={`/u/${video.author?.username}`} className="text-xs text-haze hover:text-white">
            @{video.author?.username}
          </Link>
          <span className="ml-auto text-[11px] text-haze">{timeAgo(video.published_at ?? video.created_at)}</span>
        </div>

        <div className="flex items-center justify-between text-xs text-haze">
          <button
            type="button"
            onClick={() => likeMutation.mutate()}
            className={`inline-flex items-center gap-1.5 transition ${liked ? "text-coral" : "hover:text-white"}`}
            aria-pressed={liked}
          >
            <Heart className={`h-4 w-4 ${liked ? "fill-current" : ""}`} /> {compactNumber(likeCount)}
          </button>
          <span className="inline-flex items-center gap-1.5">
            <MessageCircle className="h-4 w-4" /> {compactNumber(video.comment_count)}
          </span>
          <button
            type="button"
            onClick={() => saveMutation.mutate()}
            className={`inline-flex items-center gap-1.5 transition ${saved ? "text-lime" : "hover:text-white"}`}
            aria-pressed={saved}
          >
            <Bookmark className={`h-4 w-4 ${saved ? "fill-current" : ""}`} /> {saved ? "Saved" : "Save"}
          </button>
        </div>
      </div>
    </article>
  );
}