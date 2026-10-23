import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Flag, Heart, Send } from "lucide-react";

import Avatar from "@/components/ui/Avatar";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import CommentThread from "@/components/CommentThread";
import VideoPlayer from "@/components/VideoPlayer";
import { EmptyState, ErrorNote, Spinner } from "@/components/ui/Feedback";
import { Input, Textarea } from "@/components/ui/Input";
import { useAuth } from "@/context/AuthContext";
import { api, ApiError } from "@/lib/api";
import { compactNumber, errorMessage, titleCase } from "@/lib/utils";
import type { Video } from "@/types/api";

export default function Watch() {
  const { videoId = "" } = useParams();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [liked, setLiked] = useState<boolean | null>(null);
  const [likeCount, setLikeCount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [reportReason, setReportReason] = useState("spam");
  const [reportDetails, setReportDetails] = useState("");

  const video = useQuery({
    queryKey: ["video", videoId],
    queryFn: () => api.get<Video>(`/videos/${videoId}`),
    enabled: Boolean(videoId),
  });

  const like = useMutation({
    mutationFn: (isLiked: boolean) =>
      isLiked ? api.del(`/videos/${videoId}/like`) : api.post(`/videos/${videoId}/like`),
    onSuccess: () => {
      const next = !(liked ?? video.data?.is_liked);
      setLiked(next);
      setLikeCount((previous) => (previous ?? video.data?.like_count ?? 0) + (next ? 1 : -1));
      void queryClient.invalidateQueries({ queryKey: ["video", videoId] });
    },
    onError: (mutationError) => setError(errorMessage(mutationError)),
  });

  const report = useMutation({
    mutationFn: () =>
      api.post("/reports", {
        target_type: "video",
        target_id: videoId,
        reason: reportReason,
        details: reportDetails || undefined,
      }),
    onSuccess: () => {
      setReportOpen(false);
      setReportDetails("");
      setError("Thanks — this video is now with the moderation team.");
    },
    onError: (mutationError) => setError(errorMessage(mutationError)),
  });

  if (video.isLoading) {
    return (
      <div className="flex justify-center py-24">
        <Spinner className="h-8 w-8" />
      </div>
    );
  }

  if (video.isError || !video.data) {
    const notFound = video.error instanceof ApiError && video.error.status === 404;
    return (
      <EmptyState
        title={notFound ? "This video is not available" : "We could not load this video"}
        description={notFound ? "It may have been removed, set to private, or it never existed." : errorMessage(video.error)}
        action={
          <Link to="/feed">
            <Button size="sm">Back to the feed</Button>
          </Link>
        }
      />
    );
  }

  const data = video.data;
  const isLiked = liked ?? Boolean(data.is_liked);
  const totalLikes = likeCount ?? data.like_count;

  return (
    <div className="space-y-8 animate-fade-up">
      <VideoPlayer video={data} className="aspect-video w-full" autoplay />

      <div className="grid gap-8 lg:grid-cols-[1.5fr_1fr]">
        <div className="space-y-6">
          <div>
            <h1 className="font-display text-2xl font-semibold leading-snug tracking-tight">{data.title}</h1>
            <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-haze">
              <span>{compactNumber(data.view_count)} views</span>
              {data.category ? <Badge tone="neutral">{titleCase(data.category)}</Badge> : null}
              {data.is_learn_content ? <Badge tone="sky">LearnSpace</Badge> : null}
              {data.visibility !== "public" ? <Badge tone="coral">{titleCase(data.visibility)}</Badge> : null}
            </div>
            {data.description ? (
              <p className="mt-4 whitespace-pre-line text-sm leading-relaxed text-haze">{data.description}</p>
            ) : null}
            {data.tags.length > 0 ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {data.tags.map((tag) => (
                  <span key={tag} className="vs-chip">
                    #{tag}
                  </span>
                ))}
              </div>
            ) : null}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant={isLiked ? "lime" : "secondary"}
              size="sm"
              onClick={() => (user ? like.mutate(isLiked) : setError("Sign in to like videos."))}
            >
              <Heart className={`h-4 w-4 ${isLiked ? "fill-current" : ""}`} /> {compactNumber(totalLikes)}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() =>
                api
                  .post(`/videos/${videoId}/share`, { channel: "link" })
                  .then(() => {
                    void navigator.clipboard?.writeText(`${window.location.origin}/watch/${videoId}`);
                    setError("Link copied to your clipboard.");
                  })
                  .catch((shareError) => setError(errorMessage(shareError)))
              }
            >
              <Send className="h-4 w-4" /> Share
            </Button>
            {user ? (
              <Button variant="ghost" size="sm" onClick={() => setReportOpen((value) => !value)}>
                <Flag className="h-4 w-4" /> Report
              </Button>
            ) : null}
          </div>

          {reportOpen ? (
            <Card className="space-y-3">
              <p className="text-sm font-medium">Report this video</p>
              <div className="flex flex-wrap gap-2">
                {["spam", "harassment", "violence", "misinformation", "copyright", "other"].map((reason) => (
                  <button
                    key={reason}
                    type="button"
                    onClick={() => setReportReason(reason)}
                    className={`rounded-full border px-3 py-1 text-xs transition ${
                      reportReason === reason ? "border-coral/60 bg-coral/15 text-white" : "border-ink-700/70 text-haze"
                    }`}
                  >
                    {titleCase(reason)}
                  </button>
                ))}
              </div>
              <Textarea
                value={reportDetails}
                onChange={(event) => setReportDetails(event.target.value)}
                placeholder="Anything the moderators should know (optional)"
                rows={3}
              />
              <div className="flex justify-end gap-2">
                <Button variant="ghost" size="sm" onClick={() => setReportOpen(false)}>
                  Cancel
                </Button>
                <Button size="sm" variant="danger" loading={report.isPending} onClick={() => report.mutate()}>
                  Submit report
                </Button>
              </div>
            </Card>
          ) : null}

          {error ? <ErrorNote message={error} /> : null}

          <CommentThread videoId={videoId} allowComments={data.allow_comments} />
        </div>

        <aside className="space-y-4">
          <Card>
            <div className="flex items-center gap-3">
              <Avatar src={data.author?.avatar_url} name={data.author?.display_name ?? data.author?.username} size="lg" />
              <div className="min-w-0">
                <Link to={`/u/${data.author?.username}`} className="block truncate font-display font-semibold hover:text-violet-soft">
                  @{data.author?.username}
                </Link>
                <p className="text-xs text-haze">{compactNumber(data.author?.follower_count ?? 0)} followers</p>
              </div>
            </div>
            <p className="mt-4 text-xs text-haze">
              Engagement: {compactNumber(data.like_count)} likes · {compactNumber(data.comment_count)} comments ·{" "}
              {compactNumber(data.save_count)} saves · {compactNumber(data.share_count)} shares
            </p>
          </Card>

          <Card>
            <p className="text-sm font-medium">Creator tools</p>
            <p className="mt-2 text-xs text-haze">
              Views are counted once per viewer every 30 minutes, so refreshes never inflate the numbers.
            </p>
            {data.is_owner ? (
              <Link to="/creator" className="mt-3 inline-block text-xs text-violet-soft hover:underline">
                Open CreatorSpace →
              </Link>
            ) : null}
          </Card>

          {user ? (
            <Card className="space-y-3">
              <p className="text-sm font-medium">Message this creator</p>
              <MessageStarter username={data.author?.username ?? ""} />
            </Card>
          ) : null}
        </aside>
      </div>
    </div>
  );
}

function MessageStarter({ username }: { username: string }) {
  const [body, setBody] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);

  const start = useMutation({
    mutationFn: () =>
      api.post<{ id: string }>("/conversations", {
        participant_usernames: [username],
        first_message: body.trim(),
      }),
    onSuccess: (conversation) => {
      setConversationId(conversation.id);
      setStatus("Conversation started.");
      setBody("");
    },
    onError: (mutationError) => setStatus(errorMessage(mutationError)),
  });

  return (
    <div className="space-y-2">
      <Input
        value={body}
        onChange={(event) => setBody(event.target.value)}
        placeholder={`Say something to @${username}`}
        maxLength={500}
      />
      <div className="flex items-center justify-between gap-2">
        <Button size="sm" disabled={body.trim().length === 0} loading={start.isPending} onClick={() => start.mutate()}>
          Send
        </Button>
        {conversationId ? (
          <Link to={`/messages/${conversationId}`} className="text-xs text-violet-soft hover:underline">
            Open conversation →
          </Link>
        ) : null}
      </div>
      {status ? <p className="text-xs text-haze">{status}</p> : null}
    </div>
  );
}