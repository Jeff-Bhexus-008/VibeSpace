import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { GraduationCap } from "lucide-react";

import Button from "@/components/ui/Button";
import VideoCard from "@/components/VideoCard";
import { EmptyState, SectionTitle, Spinner } from "@/components/ui/Feedback";
import { Input } from "@/components/ui/Input";
import { api } from "@/lib/api";
import { titleCase } from "@/lib/utils";
import type { Page, Video } from "@/types/api";

const CATEGORIES = [
  { value: "", label: "All topics" },
  { value: "programming", label: "Programming" },
  { value: "technology", label: "Technology" },
  { value: "business", label: "Business" },
  { value: "academics", label: "Academics" },
  { value: "creative_arts", label: "Creative arts" },
  { value: "personal_development", label: "Personal development" },
  { value: "practical_skills", label: "Practical skills" },
];

/** LearnSpace: educational uploads filtered by category, with real search. */
export default function LearnSpace() {
  const [category, setCategory] = useState("");
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");

  const videos = useQuery({
    queryKey: ["learn", category, submitted],
    queryFn: () =>
      submitted
        ? api.get<{ videos: Page<Video> }>("/search", {
            q: submitted,
            type: "learn",
            learn_category: category || undefined,
            limit: 24,
          })
        : api.get<Page<Video>>("/feed", {
            mode: "learn",
            surface: "learn",
            learn_category: category || undefined,
            limit: 24,
          }),
    select: (data): Page<Video> =>
      "videos" in data && data.videos ? (data.videos as Page<Video>) : (data as Page<Video>),
  });

  return (
    <div className="space-y-8 animate-fade-up">
      <header className="space-y-4">
        <div className="flex items-center gap-3">
          <span className="grid h-11 w-11 place-items-center rounded-2xl bg-sky/15 text-sky">
            <GraduationCap className="h-5 w-5" />
          </span>
          <div>
            <h1 className="font-display text-2xl font-semibold tracking-tight">LearnSpace</h1>
            <p className="text-sm text-haze">Skills, lessons and explainers published by the community.</p>
          </div>
        </div>

        <form
          className="flex flex-col gap-3 sm:flex-row"
          onSubmit={(event) => {
            event.preventDefault();
            setSubmitted(query.trim());
          }}
        >
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search lessons — “python”, “guitar”, “interview prep”"
          />
          <div className="flex gap-2">
            <Button type="submit" disabled={query.trim().length === 0}>
              Search
            </Button>
            {submitted ? (
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setQuery("");
                  setSubmitted("");
                }}
              >
                Clear
              </Button>
            ) : null}
          </div>
        </form>

        <div className="flex flex-wrap gap-2">
          {CATEGORIES.map((item) => (
            <button
              key={item.value || "all"}
              type="button"
              onClick={() => setCategory(item.value)}
              className={`rounded-full border px-3.5 py-1.5 text-xs transition ${
                category === item.value ? "border-sky/50 bg-sky/15 text-white" : "border-ink-700/70 text-haze"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </header>

      <SectionTitle hint={videos.data ? `${videos.data.items.length} lesson(s)` : undefined}>
        {submitted ? `Results for “${submitted}”` : category ? titleCase(category) : "Latest lessons"}
      </SectionTitle>

      {videos.isLoading ? (
        <div className="flex justify-center py-12">
          <Spinner className="h-7 w-7" />
        </div>
      ) : videos.data && videos.data.items.length > 0 ? (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {videos.data.items.map((video) => (
            <VideoCard key={video.id} video={video} />
          ))}
        </div>
      ) : (
        <EmptyState
          title="No lessons published yet"
          description="Published videos marked as LearnSpace content show up here. Organise yours by category to help learners find them."
          action={
            <Link to="/create">
              <Button size="sm">Publish a lesson</Button>
            </Link>
          }
        />
      )}
    </div>
  );
}