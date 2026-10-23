import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import VideoCard from "@/components/VideoCard";
import type { Video } from "@/types/api";

const video: Video = {
  id: "vid-1",
  title: "Friday night dance-off entry",
  tags: ["dance"],
  visibility: "public",
  status: "ready",
  is_learn_content: false,
  allow_comments: true,
  view_count: 1200,
  like_count: 12,
  comment_count: 3,
  save_count: 1,
  share_count: 0,
  duration_seconds: 65,
  author: { id: "u1", username: "mover", display_name: "Mover", avatar_url: null, follower_count: 40 },
};

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

function renderCard() {
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter>
        <VideoCard video={video} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("VideoCard", () => {
  it("renders the title, creator, duration and engagement", () => {
    renderCard();

    expect(screen.getByText("Friday night dance-off entry")).toBeInTheDocument();
    expect(screen.getByText("@mover")).toBeInTheDocument();
    expect(screen.getByText("1:05")).toBeInTheDocument();
    expect(screen.getByText("1.2K")).toBeInTheDocument();
    expect(screen.getByText("Save")).toBeInTheDocument();
  });

  it("likes the video through the API and reflects the new state", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);

    renderCard();
    const likeButton = screen.getAllByRole("button").find((button) => button.textContent?.includes("12"));

    expect(likeButton).toBeDefined();
    await userEvent.click(likeButton as HTMLElement);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/v1/videos/vid-1/like"),
        expect.objectContaining({ method: "POST" }),
      );
    });
    await waitFor(() => expect(likeButton).toHaveAttribute("aria-pressed", "true"));
    expect(likeButton?.textContent).toContain("13");
  });

  it("marks a LearnSpace video with a badge", () => {
    renderCard();

    expect(screen.getByText("Learn")).toBeInTheDocument();
  });
});