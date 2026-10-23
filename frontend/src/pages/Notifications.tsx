import { Link } from "react-router-dom";
import { Bell, MessageSquare } from "lucide-react";

import Avatar from "@/components/ui/Avatar";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import { EmptyState, Spinner } from "@/components/ui/Feedback";
import { useNotifications } from "@/hooks/useNotifications";
import { timeAgo, titleCase } from "@/lib/utils";

const COPY: Record<string, string> = {
  follow: "started following you",
  like: "liked your video",
  comment: "commented on your video",
  reply: "replied to your comment",
  battle_invite: "invited you to a battle",
  battle_entry: "took part in your battle",
  battle_vote_milestone: "Your battle reached a new voting milestone",
  battle_result: "Battle results are out",
  message: "sent you a message",
  moderation: "A moderation action touched your content",
  system: "VibeSpace update",
};

export default function Notifications() {
  const { notifications, loading, unreadCount, messageCount, live, markRead } = useNotifications(true);

  return (
    <div className="space-y-6 animate-fade-up">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 font-display text-2xl font-semibold tracking-tight">
            <Bell className="h-5 w-5 text-violet" /> Notifications
          </h1>
          <p className="mt-1 text-sm text-haze">
            {unreadCount} unread · {messageCount} unread messages ·{" "}
            {live ? "live updates connected" : "polling every 20s (WebSocket unavailable)"}
          </p>
        </div>
        <div className="flex gap-2">
          <Link to="/messages">
            <Button variant="secondary" size="sm">
              <MessageSquare className="h-4 w-4" /> Inbox
            </Button>
          </Link>
          {unreadCount > 0 ? (
            <Button size="sm" onClick={() => void markRead()}>
              Mark all read
            </Button>
          ) : null}
        </div>
      </header>

      {loading ? (
        <div className="flex justify-center py-16">
          <Spinner className="h-7 w-7" />
        </div>
      ) : notifications.length === 0 ? (
        <EmptyState
          title="Nothing here yet"
          description="Follows, likes, comments, battle invitations and results all land here."
        />
      ) : (
        <ul className="space-y-3">
          {notifications.map((notification) => {
            const link = notification.entity_type === "video" && notification.entity_id
              ? `/watch/${notification.entity_id}`
              : notification.entity_type === "challenge" && notification.entity_id
                ? `/battles/${notification.entity_id}`
                : notification.entity_type === "user" && notification.actor
                  ? `/u/${notification.actor.username}`
                  : null;

            const row = (
              <Card className={`flex items-start gap-3 ${notification.is_read ? "opacity-70" : ""}`}>
                <Avatar
                  src={notification.actor?.avatar_url}
                  name={notification.actor?.display_name ?? notification.actor?.username}
                  size="sm"
                />
                <div className="min-w-0 flex-1">
                  <p className="text-sm">
                    {notification.actor ? <span className="font-medium">@{notification.actor.username} </span> : null}
                    {COPY[notification.type] ?? titleCase(notification.type)}
                    {typeof notification.payload.title === "string" ? `: ${notification.payload.title}` : ""}
                  </p>
                  {typeof notification.payload.excerpt === "string" ? (
                    <p className="mt-1 line-clamp-2 text-xs text-haze">{notification.payload.excerpt}</p>
                  ) : null}
                  <p className="mt-1 text-[11px] text-haze">{timeAgo(notification.created_at)}</p>
                </div>
                {!notification.is_read ? (
                  <button
                    type="button"
                    className="text-[11px] text-violet-soft hover:underline"
                    onClick={() => void markRead([notification.id])}
                  >
                    Mark read
                  </button>
                ) : null}
              </Card>
            );

            return (
              <li key={notification.id}>
                {link ? (
                  <Link to={link} className="block transition hover:brightness-110">
                    {row}
                  </Link>
                ) : (
                  row
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}