import { useEffect, useRef, useState } from "react";
import { Eye, Heart, Pause, Play, Volume2, VolumeX } from "lucide-react";

import { api } from "@/lib/api";
import { compactNumber, formatDuration } from "@/lib/utils";
import Avatar from "@/components/ui/Avatar";
import Badge from "@/components/ui/Badge";
import type { Video } from "@/types/api";

function sessionKey(): string {
  const key = "vibespace:session";
  let value = sessionStorage.getItem(key);
  if (!value) {
    value = crypto.randomUUID();
    sessionStorage.setItem(key, value);
  }
  return value;
}

/**
 * Inline player used by the feed and the watch page.
 * A view is reported once per 30 minutes per viewer — the server deduplicates.
 */
export default function VideoPlayer({
  video,
  onViewed,
  className,
  autoplay = false,
}: {
  video: Video;
  onViewed?: (viewCount: number) => void;
  className?: string;
  autoplay?: boolean;
}) {
  const ref = useRef<HTMLVideoElement | null>(null);
  const viewSent = useRef(false);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    viewSent.current = false;
    setError(null);
  }, [video.id]);

  async function reportView(watchedSeconds: number) {
    if (viewSent.current) return;
    viewSent.current = true;
    try {
      const result = await api.post<{ view_count: number }>(
        `/videos/${video.id}/view`,
        undefined,
        { session_key: sessionKey(), watched_seconds: Math.round(watchedSeconds), source: "feed" },
      );
      onViewed?.(result.view_count);
    } catch {
      viewSent.current = false; // allow a later retry
    }
  }

  function toggle() {
    const element = ref.current;
    if (!element) return;
    if (element.paused) {
      void element.play().catch(() => setError("Your browser blocked playback. Tap the video to start."));
    } else {
      element.pause();
    }
  }

  if (!video.playback_url) {
    return (
      <div className={`grid place-items-center rounded-3xl border border-ink-700/70 bg-ink-900 ${className ?? ""}`}>
        <p className="px-6 py-16 text-center text-sm text-haze">
          This video has no playable file yet. Processing may still be running.
        </p>
      </div>
    );
  }

  return (
    <div className={`relative overflow-hidden rounded-3xl border border-ink-800/80 bg-black ${className ?? ""}`}>
      <video
        ref={ref}
        src={video.playback_url}
        poster={video.thumbnail_url ?? undefined}
        className="h-full w-full object-cover"
        playsInline
        muted={muted}
        autoPlay={autoplay}
        loop
        preload="metadata"
        onPlay={() => {
          setPlaying(true);
          window.setTimeout(() => {
            const element = ref.current;
            if (element && !element.paused) void reportView(element.currentTime);
          }, 2500);
        }}
        onPause={() => setPlaying(false)}
        onClick={toggle}
      />

      <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 via-black/30 to-transparent p-4 pt-16">
        <div className="pointer-events-auto flex items-end justify-between gap-3">
          <div className="flex items-center gap-3">
            <Avatar src={video.author?.avatar_url} name={video.author?.display_name ?? video.author?.username} size="sm" />
            <div>
              <p className="text-sm font-medium">@{video.author?.username}</p>
              <p className="text-xs text-haze">
                {compactNumber(video.like_count)} likes · {compactNumber(video.view_count)} views
                {video.duration_seconds ? ` · ${formatDuration(video.duration_seconds)}` : ""}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {video.is_learn_content ? <Badge tone="sky">LearnSpace</Badge> : null}
            <button
              type="button"
              aria-label={muted ? "Unmute" : "Mute"}
              onClick={() => setMuted((value) => !value)}
              className="grid h-9 w-9 place-items-center rounded-full bg-black/50 text-white backdrop-blur"
            >
              {muted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
            </button>
            <button
              type="button"
              aria-label={playing ? "Pause" : "Play"}
              onClick={toggle}
              className="grid h-9 w-9 place-items-center rounded-full bg-white/90 text-ink-950"
            >
              {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            </button>
          </div>
        </div>

        <div className="pointer-events-none mt-3 flex items-center gap-4 text-[11px] text-haze">
          <span className="inline-flex items-center gap-1">
            <Heart className="h-3.5 w-3.5" /> {compactNumber(video.like_count)}
          </span>
          <span className="inline-flex items-center gap-1">
            <Eye className="h-3.5 w-3.5" /> {compactNumber(video.view_count)}
          </span>
        </div>
      </div>

      {error ? (
        <p className="absolute inset-x-4 top-4 rounded-2xl bg-danger/90 px-3 py-2 text-xs text-white">{error}</p>
      ) : null}
    </div>
  );
}