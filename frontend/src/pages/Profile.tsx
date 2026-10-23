import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bookmark, ExternalLink, Settings2, ShieldOff, UserCheck, UserPlus } from "lucide-react";

import Avatar from "@/components/ui/Avatar";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import VideoCard from "@/components/VideoCard";
import { EmptyState, ErrorNote, Spinner } from "@/components/ui/Feedback";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { compactNumber, errorMessage, titleCase } from "@/lib/utils";
import type { Page, PublicUser, Video } from "@/types/api";

export default function Profile() {
  const { username } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"videos" | "saved">("videos");
  const [error, setError] = useState<string | null>(null);

  const target = username ?? user?.username ?? "";
  const isSelf = Boolean(user && target === user.username);

  const profile = useQuery({
    queryKey: ["profile", target],
    queryFn: () => api.get<PublicUser>(`/users/${target}`),
    enabled: Boolean(target),
  });

  const videos = useQuery({
    queryKey: ["profile", target, "videos"],
    queryFn: () => api.get<Page<Video>>(`/users/${target}/videos`, { limit: 24 }),
    enabled: Boolean(target) && tab === "videos",
  });

  const saved = useQuery({
    queryKey: ["videos", "saved"],
    queryFn: () => api.get<Page<Video>>("/videos/saved", { limit: 24 }),
    enabled: isSelf && tab === "saved",
  });

  const follow = useMutation({
    mutationFn: (following: boolean) =>
      following ? api.del(`/users/${target}/follow`) : api.post(`/users/${target}/follow`),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["profile", target] }),
    onError: (mutationError) => setError(errorMessage(mutationError)),
  });

  const block = useMutation({
    mutationFn: () => api.post(`/users/${target}/block`, {}),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["profile", target] });
    },
    onError: (mutationError) => setError(errorMessage(mutationError)),
  });

  if (profile.isLoading) {
    return (
      <div className="flex justify-center py-24">
        <Spinner className="h-8 w-8" />
      </div>
    );
  }

  if (profile.isError || !profile.data) {
    return (
      <EmptyState
        title="Profile not found"
        description={errorMessage(profile.error)}
        action={
          <Link to="/explore">
            <Button size="sm">Find creators</Button>
          </Link>
        }
      />
    );
  }

  const data = profile.data;
  const shown = tab === "saved" ? saved.data?.items ?? [] : videos.data?.items ?? [];
  const loadingList = tab === "saved" ? saved.isLoading : videos.isLoading;

  return (
    <div className="space-y-8 animate-fade-up">
      <div className="overflow-hidden rounded-[2rem] border border-ink-800/80 bg-ink-900/60">
        <div className="relative h-40 bg-gradient-to-r from-violet/30 via-ink-850 to-coral/20 sm:h-52">
          {data.cover_url ? (
            <img src={data.cover_url} alt="Cover" className="h-full w-full object-cover" />
          ) : null}
        </div>

        <div className="relative px-5 pb-6 sm:px-8">
          <div className="-mt-12 flex flex-wrap items-end justify-between gap-4">
            <div className="flex items-end gap-4">
              <Avatar src={data.avatar_url} name={data.display_name ?? data.username} size="xl" className="ring-4 ring-ink-950" />
              <div className="pb-1">
                <h1 className="font-display text-2xl font-semibold tracking-tight">
                  {data.display_name ?? data.username}
                </h1>
                <p className="text-sm text-haze">
                  @{data.username}
                  {data.location ? ` · ${data.location}` : ""}
                </p>
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              {data.role !== "user" ? <Badge tone="violet">{titleCase(data.role)}</Badge> : null}
              {isSelf ? (
                <>
                  <Button size="sm" variant="secondary" onClick={() => navigate("/settings")}>
                    <Settings2 className="h-4 w-4" /> Edit profile
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => navigate("/creator")}>
                    CreatorSpace
                  </Button>
                </>
              ) : user ? (
                <>
                  <Button
                    size="sm"
                    variant={data.is_following ? "secondary" : "primary"}
                    loading={follow.isPending}
                    onClick={() => follow.mutate(Boolean(data.is_following))}
                  >
                    {data.is_following ? <UserCheck className="h-4 w-4" /> : <UserPlus className="h-4 w-4" />}
                    {data.is_following ? "Following" : "Follow"}
                  </Button>
                  <Button size="sm" variant="ghost" loading={block.isPending} onClick={() => block.mutate()}>
                    <ShieldOff className="h-4 w-4" /> Block
                  </Button>
                </>
              ) : (
                <Link to="/login">
                  <Button size="sm">Sign in to follow</Button>
                </Link>
              )}
            </div>
          </div>

          {error ? (
            <div className="mt-5">
              <ErrorNote message={error} />
            </div>
          ) : null}

          <div className="mt-5 flex flex-wrap gap-6 text-sm">
            <Stat label="Videos" value={data.video_count} />
            <Stat label="Followers" value={data.follower_count} />
            <Stat label="Following" value={data.following_count} />
            <Stat label="Likes" value={data.total_likes} />
          </div>

          {data.bio ? <p className="mt-5 max-w-2xl whitespace-pre-line text-sm leading-relaxed text-haze">{data.bio}</p> : null}

          {data.links.length > 0 ? (
            <ul className="mt-4 flex flex-wrap gap-3 text-xs">
              {data.links.map((link) => (
                <li key={link}>
                  <a
                    href={link}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-violet-soft hover:underline"
                  >
                    {link.replace(/^https?:\/\//, "").slice(0, 40)} <ExternalLink className="h-3 w-3" />
                  </a>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>

      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => setTab("videos")}
          className={`rounded-full border px-4 py-1.5 text-xs transition ${
            tab === "videos" ? "border-violet/50 bg-violet/15 text-white" : "border-ink-700/70 text-haze"
          }`}
        >
          Videos
        </button>
        {isSelf ? (
          <button
            type="button"
            onClick={() => setTab("saved")}
            className={`inline-flex items-center gap-1.5 rounded-full border px-4 py-1.5 text-xs transition ${
              tab === "saved" ? "border-lime/50 bg-lime/15 text-white" : "border-ink-700/70 text-haze"
            }`}
          >
            <Bookmark className="h-3.5 w-3.5" /> Saved
          </button>
        ) : null}
      </div>

      {loadingList ? (
        <div className="flex justify-center py-14">
          <Spinner className="h-7 w-7" />
        </div>
      ) : shown.length > 0 ? (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {shown.map((video) => (
            <VideoCard key={video.id} video={video} />
          ))}
        </div>
      ) : (
        <EmptyState
          title={tab === "saved" ? "Nothing saved yet" : "No videos published"}
          description={
            tab === "saved"
              ? "Saved videos are private to your account."
              : isSelf
                ? "Your published videos appear here."
                : "This creator has not published anything yet."
          }
          action={
            isSelf ? (
              <Link to="/create">
                <Button size="sm">Publish a video</Button>
              </Link>
            ) : undefined
          }
        />
      )}

      {isSelf && !user?.is_email_verified ? (
        <Card className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-haze">
            Confirm your email address to unlock publishing, battles and voting.
          </p>
          <Link to="/verify-email">
            <Button size="sm" variant="secondary">
              Confirm email
            </Button>
          </Link>
        </Card>
      ) : null}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <p className="font-display text-lg font-semibold">{compactNumber(value)}</p>
      <p className="text-[11px] uppercase tracking-wide text-haze">{label}</p>
    </div>
  );
}