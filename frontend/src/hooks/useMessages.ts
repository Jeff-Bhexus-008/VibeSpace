import { useCallback, useEffect, useRef, useState } from "react";

import { WS_BASE, api } from "@/lib/api";
import type { Conversation, Message, Page } from "@/types/api";
import { errorMessage } from "@/lib/utils";

/** Conversations + live chat: WebSocket first, REST polling as the fallback. */
export function useConversations(enabled: boolean) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!enabled) return;
    try {
      const page = await api.get<Page<Conversation>>("/conversations", { limit: 50 });
      setConversations(page.items);
      setError(null);
    } catch (loadError) {
      setError(errorMessage(loadError));
    } finally {
      setLoading(false);
    }
  }, [enabled]);

  useEffect(() => {
    void load();
    if (!enabled) return undefined;
    const timer = setInterval(load, 30_000);
    return () => clearInterval(timer);
  }, [enabled, load]);

  const startConversation = useCallback(
    async (usernames: string[], firstMessage?: string) => {
      const conversation = await api.post<Conversation>("/conversations", {
        participant_usernames: usernames,
        first_message: firstMessage,
      });
      await load();
      return conversation;
    },
    [load],
  );

  return { conversations, loading, error, reload: load, startConversation };
}

export function useConversationMessages(conversationId: string | null, enabled: boolean) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [live, setLive] = useState(false);
  const [loading, setLoading] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!conversationId || !enabled) {
      setMessages([]);
      return undefined;
    }
    let closed = false;
    let timer: ReturnType<typeof setInterval> | undefined;

    const loadHistory = async () => {
      setLoading(true);
      try {
        const page = await api.get<Page<Message>>(`/conversations/${conversationId}/messages`, { limit: 50 });
        setMessages([...page.items].reverse());
      } finally {
        setLoading(false);
      }
    };

    void loadHistory();

    const socket = new WebSocket(`${WS_BASE}/conversations/${conversationId}`);
    socketRef.current = socket;
    socket.onopen = () => {
      setLive(true);
      if (timer) clearInterval(timer);
    };
    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as { event?: string; id?: string; body?: string };
        if (payload.event === "message" || payload.event === "message_sent") {
          void loadHistory();
        }
      } catch {
        /* ignore */
      }
    };
    // Realtime unavailable (proxy, mobile, Redis down): fall back to polling.
    socket.onclose = () => {
      setLive(false);
      if (!closed && !timer) timer = setInterval(loadHistory, 8000);
    };
    socket.onerror = () => socket.close();

    return () => {
      closed = true;
      if (timer) clearInterval(timer);
      socket.close();
    };
  }, [conversationId, enabled]);

  const send = useCallback(
    async (body: string) => {
      if (!conversationId) return;
      if (socketRef.current?.readyState === WebSocket.OPEN) {
        socketRef.current.send(JSON.stringify({ event: "message", body }));
        return;
      }
      await api.post(`/conversations/${conversationId}/messages`, { body });
      const page = await api.get<Page<Message>>(`/conversations/${conversationId}/messages`, { limit: 50 });
      setMessages([...page.items].reverse());
    },
    [conversationId],
  );

  const markRead = useCallback(async () => {
    if (!conversationId) return;
    await api.post(`/conversations/${conversationId}/read`, {});
  }, [conversationId]);

  return { messages, loading, live, send, markRead, reload: () => setMessages((current) => [...current]) };
}