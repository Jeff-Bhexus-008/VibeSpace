import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CornerDownRight, Send } from "lucide-react";

import Avatar from "@/components/ui/Avatar";
import Button from "@/components/ui/Button";
import { Textarea } from "@/components/ui/Input";
import { EmptyState, ErrorNote, Spinner } from "@/components/ui/Feedback";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { errorMessage, timeAgo } from "@/lib/utils";
import type { Comment, Page } from "@/types/api";

/** Comments with one level of replies, exactly as the API models them. */
export default function CommentThread({ videoId, allowComments }: { videoId: string; allowComments: boolean }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [body, setBody] = useState("");
  const [replyTo, setReplyTo] = useState<Comment | null>(null);
  const [error, setError] = useState<string | null>(null);

  const comments = useQuery({
    queryKey: ["comments", videoId],
    queryFn: () => api.get<Page<Comment>>(`/videos/${videoId}/comments`, { limit: 30 }),
  });

  const createComment = useMutation({
    mutationFn: () =>
      api.post<Comment>(`/videos/${videoId}/comments`, {
        body: body.trim(),
        parent_id: replyTo?.id,
      }),
    onSuccess: () => {
      setBody("");
      setReplyTo(null);
      void queryClient.invalidateQueries({ queryKey: ["comments", videoId] });
    },
    onError: (mutationError) => setError(errorMessage(mutationError)),
  });

  const removeComment = useMutation({
    mutationFn: (commentId: string) => api.del(`/comments/${commentId}`),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["comments", videoId] }),
  });

  if (!allowComments) {
    return <p className="rounded-2xl border border-ink-800/70 bg-ink-900/50 p-4 text-sm text-haze">Comments are turned off for this video.</p>;
  }

  return (
    <section className="space-y-5">
      {user ? (
        <div className="space-y-3">
          {replyTo ? (
            <p className="flex items-center gap-2 text-xs text-haze">
              <CornerDownRight className="h-3.5 w-3.5" /> Replying to @{replyTo.author?.username}
              <button type="button" className="text-violet-soft underline" onClick={() => setReplyTo(null)}>
                cancel
              </button>
            </p>
          ) : null}
          <Textarea
            value={body}
            onChange={(event) => setBody(event.target.value)}
            placeholder={replyTo ? "Write a reply…" : "Add a comment…"}
            rows={3}
            maxLength={2000}
          />
          {error ? <ErrorNote message={error} /> : null}
          <div className="flex justify-end">
            <Button
              size="sm"
              disabled={body.trim().length === 0}
              loading={createComment.isPending}
              onClick={() => createComment.mutate()}
            >
              <Send className="h-4 w-4" /> {replyTo ? "Reply" : "Comment"}
            </Button>
          </div>
        </div>
      ) : (
        <p className="rounded-2xl border border-ink-800/70 bg-ink-900/50 p-4 text-sm text-haze">
          <Link to="/login" className="text-violet-soft underline">
            Sign in
          </Link>{" "}
          to join the conversation.
        </p>
      )}

      {comments.isLoading ? (
        <div className="flex justify-center py-6">
          <Spinner />
        </div>
      ) : comments.data && comments.data.items.length > 0 ? (
        <ul className="space-y-4">
          {comments.data.items.map((comment) => (
            <li key={comment.id} className="flex gap-3">
              <Avatar src={comment.author?.avatar_url} name={comment.author?.display_name ?? comment.author?.username} size="sm" />
              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-2 text-sm">
                  <span className="font-medium">@{comment.author?.username}</span>
                  <span className="text-[11px] text-haze">{timeAgo(comment.created_at)}</span>
                </p>
                <p className="mt-1 whitespace-pre-line text-sm text-haze">{comment.body}</p>
                <div className="mt-1.5 flex items-center gap-4 text-[11px] text-haze">
                  {user ? (
                    <button type="button" className="hover:text-white" onClick={() => setReplyTo(comment)}>
                      Reply
                    </button>
                  ) : null}
                  {comment.is_owner ? (
                    <button
                      type="button"
                      className="text-danger hover:underline"
                      onClick={() => removeComment.mutate(comment.id)}
                    >
                      Delete
                    </button>
                  ) : null}
                  {comment.reply_count > 0 ? <Replies commentId={comment.id} /> : null}
                </div>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState title="No comments yet" description="Be the first to react to this video." />
      )}
    </section>
  );
}

function Replies({ commentId }: { commentId: string }) {
  const [open, setOpen] = useState(false);
  const replies = useQuery({
    queryKey: ["replies", commentId],
    queryFn: () => api.get<Page<Comment>>(`/comments/${commentId}/replies`, { limit: 20 }),
    enabled: open,
  });

  return (
    <div className="w-full">
      <button type="button" className="hover:text-white" onClick={() => setOpen((value) => !value)}>
        {open ? "Hide replies" : "Show replies"}
      </button>
      {open ? (
        replies.isLoading ? (
          <Spinner className="h-4 w-4" />
        ) : (
          <ul className="mt-3 space-y-3 border-l border-ink-800 pl-2">
            {replies.data?.items.map((reply) => (
              <li key={reply.id} className="text-xs text-haze">
                <span className="font-medium text-white">@{reply.author?.username}</span> · {reply.body}
              </li>
            ))}
          </ul>
        )
      ) : null}
    </div>
  );
}