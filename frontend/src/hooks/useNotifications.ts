import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { WS_BASE, api } from "@/lib/api";
import type { Notification, Page } from "@/types/api";

/**
 * Notifications: WebSocket push with an automatic polling fallback.
 * `live` tells the UI which channel is currently in use.
 */
export function useNotifications(enabled: boolean) {
  const queryClient = useQueryClient();
  const [live, setLive] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);

  const list = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api.get<Page<Notification>>("/notifications", { limit: 30 }),
    enabled,
  });

  const unread = useQuery({
    queryKey: ["notifications", "unread"],
    queryFn: () => api.get<{ notifications: number; messages: number; conversations: number }>("/notifications/unread"),
    enabled,
    refetchInterval: live ? false : 20_000,
  });

  const refreshAll = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ["notifications"] });
  }, [queryClient]);

  useEffect(() => {
    if (!enabled) return undefined;
    let reconnect: ReturnType<typeof setTimeout> | undefined;
    let closed = false;

    const connect = () => {
      try {
        const socket = new WebSocket(`${WS_BASE}/notifications`);
        socketRef.current = socket;

        socket.onopen = () => setLive(true);
        socket.onmessage = (event) => {
          try {
            const payload = JSON.parse(event.data) as { event?: string };
            if (payload.event === "notification" || payload.event === "message") refreshAll();
          } catch {
            /* ignore malformed frames */
          }
        };
        socket.onclose = () => {
          setLive(false);
          if (!closed) reconnect = setTimeout(connect, 8000);
        };
        socket.onerror = () => socket.close();
      } catch {
        setLive(false);
      }
    };

    connect();
    return () => {
      closed = true;
      if (reconnect) clearTimeout(reconnect);
      socketRef.current?.close();
    };
  }, [enabled, refreshAll]);

  const markRead = useCallback(
    async (ids?: string[]) => {
      await api.post("/notifications/read", ids ? { ids } : { all: true });
      refreshAll();
    },
    [refreshAll],
  );

  return {
    notifications: list.data?.items ?? [],
    loading: list.isLoading,
    unreadCount: unread.data?.notifications ?? 0,
    messageCount: unread.data?.messages ?? 0,
    live,
    markRead,
    refreshAll,
  };
}