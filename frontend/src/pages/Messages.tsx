import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { MessageSquarePlus, Send } from "lucide-react";

import Avatar from "@/components/ui/Avatar";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import { EmptyState, ErrorNote, Spinner } from "@/components/ui/Feedback";
import { Input } from "@/components/ui/Input";
import { useAuth } from "@/context/AuthContext";
import { useConversationMessages, useConversations } from "@/hooks/useMessages";
import { errorMessage, timeAgo } from "@/lib/utils";

export default function Messages() {
  const { conversationId } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const { conversations, loading, error: listError, startConversation } = useConversations(true);
  const { messages, loading: threadLoading, live, send, markRead } = useConversationMessages(
    conversationId ?? null,
    true,
  );
  const [draft, setDraft] = useState("");
  const [newUsername, setNewUsername] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (conversationId) void markRead();
  }, [conversationId, markRead]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  const active = conversations.find((conversation) => conversation.id === conversationId);

  return (
    <div className="space-y-6 animate-fade-up">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">Messages</h1>
          <p className="mt-1 text-sm text-haze">
            {conversationId
              ? live
                ? "Connected for real-time updates."
                : "Real-time unavailable — falling back to polling every 8 seconds."
              : "Direct conversations, with blocking and privacy rules enforced by the API."}
          </p>
        </div>
      </header>

      {error ? <ErrorNote message={error} /> : null}
      {listError ? <ErrorNote message={listError} /> : null}
      {notice ? (
        <p className="rounded-2xl border border-lime/40 bg-lime/10 px-4 py-3 text-sm text-lime">{notice}</p>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[20rem_1fr]">
        <div className="space-y-4">
          <Card className="space-y-3">
            <p className="text-sm font-medium">Start a conversation</p>
            <div className="flex gap-2">
              <Input
                value={newUsername}
                onChange={(event) => setNewUsername(event.target.value)}
                placeholder="username"
              />
              <Button
                size="sm"
                disabled={newUsername.trim().length < 3}
                onClick={() =>
                  startConversation([newUsername.trim()])
                    .then((conversation) => {
                      setNewUsername("");
                      navigate(`/messages/${conversation.id}`);
                    })
                    .catch((startError) => setError(errorMessage(startError)))
                }
              >
                <MessageSquarePlus className="h-4 w-4" />
              </Button>
            </div>
          </Card>

          <Card className="p-2">
            {loading ? (
              <div className="flex justify-center py-8">
                <Spinner />
              </div>
            ) : conversations.length === 0 ? (
              <p className="px-3 py-6 text-center text-xs text-haze">No conversations yet.</p>
            ) : (
              <ul className="space-y-1">
                {conversations.map((conversation) => {
                  const others = conversation.participants.filter((participant) => participant.id !== user?.id);
                  const label = conversation.title ?? others.map((participant) => `@${participant.username}`).join(", ");
                  return (
                    <li key={conversation.id}>
                      <Link
                        to={`/messages/${conversation.id}`}
                        className={`flex items-center gap-3 rounded-2xl px-3 py-2.5 transition ${
                          conversation.id === conversationId ? "bg-violet/15" : "hover:bg-ink-850/70"
                        }`}
                      >
                        <Avatar
                          src={others[0]?.avatar_url}
                          name={others[0]?.display_name ?? others[0]?.username ?? label}
                          size="sm"
                        />
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm">{label || "Conversation"}</p>
                          <p className="truncate text-[11px] text-haze">
                            {conversation.last_message_preview ?? "No messages yet"}
                          </p>
                        </div>
                        {conversation.unread_count > 0 ? (
                          <span className="rounded-full bg-coral px-1.5 py-0.5 text-[10px] font-bold text-ink-950">
                            {conversation.unread_count}
                          </span>
                        ) : (
                          <span className="text-[10px] text-haze">{timeAgo(conversation.last_message_at)}</span>
                        )}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
        </div>

        <Card className="flex min-h-[32rem] flex-col">
          {!conversationId ? (
            <EmptyState title="Pick a conversation" description="Or start a new one with a username." />
          ) : (
            <>
              <header className="mb-4 border-b border-ink-800/70 pb-3">
                <p className="font-display text-base font-semibold">
                  {active?.title ??
                    active?.participants
                      .filter((participant) => participant.id !== user?.id)
                      .map((participant) => `@${participant.username}`)
                      .join(", ") ??
                    "Conversation"}
                </p>
              </header>

              <div className="vs-scroll flex-1 space-y-3 overflow-y-auto pr-1">
                {threadLoading ? (
                  <div className="flex justify-center py-10">
                    <Spinner />
                  </div>
                ) : messages.length === 0 ? (
                  <p className="py-10 text-center text-xs text-haze">No messages yet — say hello.</p>
                ) : (
                  messages.map((message) => {
                    const mine = message.sender_id === user?.id;
                    return (
                      <div key={message.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
                        <div
                          className={`max-w-[80%] rounded-2xl px-3.5 py-2.5 text-sm ${
                            mine ? "bg-violet text-white" : "bg-ink-850 text-white"
                          }`}
                        >
                          {message.body ? <p className="whitespace-pre-line">{message.body}</p> : null}
                          {message.attachment_url ? (
                            <a
                              href={message.attachment_url}
                              target="_blank"
                              rel="noreferrer"
                              className="mt-1 block text-xs underline"
                            >
                              Attachment
                            </a>
                          ) : null}
                          <p className={`mt-1 text-[10px] ${mine ? "text-white/70" : "text-haze"}`}>
                            {timeAgo(message.created_at)}
                            {message.edited_at ? " · edited" : ""}
                          </p>
                        </div>
                      </div>
                    );
                  })
                )}
                <div ref={endRef} />
              </div>

              <form
                className="mt-4 flex gap-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  const body = draft.trim();
                  if (!body) return;
                  setDraft("");
                  send(body).catch((sendError) => setError(errorMessage(sendError)));
                }}
              >
                <Input
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  placeholder="Write a message…"
                  maxLength={4000}
                />
                <Button type="submit" disabled={draft.trim().length === 0}>
                  <Send className="h-4 w-4" />
                </Button>
              </form>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}