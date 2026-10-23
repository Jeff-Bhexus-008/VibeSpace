import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { UploadCloud } from "lucide-react";

import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import UploadPanel from "@/components/UploadPanel";
import { ErrorNote } from "@/components/ui/Feedback";
import { FieldLabel, Input, Textarea } from "@/components/ui/Input";
import { api } from "@/lib/api";
import { errorMessage, titleCase } from "@/lib/utils";
import type { MediaAsset, Video } from "@/types/api";

const VIDEO_CATEGORIES = ["dance", "comedy", "music", "sports", "gaming", "coding", "education", "art", "fitness", "creativity"];
const LEARN_CATEGORIES = [
  "programming",
  "technology",
  "business",
  "academics",
  "creative_arts",
  "personal_development",
  "practical_skills",
];

export default function Create() {
  const navigate = useNavigate();
  const [asset, setAsset] = useState<MediaAsset | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    title: "",
    description: "",
    category: "dance",
    tags: "",
    visibility: "public",
    allow_comments: true,
    is_learn_content: false,
    learn_category: "programming",
    publish: true,
  });

  const storage = useQuery({
    queryKey: ["uploads", "config"],
    queryFn: () =>
      api.get<{
        storage_configured: boolean;
        video_processing_enabled: boolean;
        ffmpeg_available: boolean;
        max_bytes: number;
      }>("/uploads/config/status"),
  });

  const publish = useMutation({
    mutationFn: () =>
      api.post<Video>("/videos", {
        media_asset_id: asset?.id,
        title: form.title.trim(),
        description: form.description.trim() || undefined,
        category: form.category,
        tags: form.tags
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean),
        visibility: form.visibility,
        allow_comments: form.allow_comments,
        is_learn_content: form.is_learn_content,
        learn_category: form.is_learn_content ? form.learn_category : undefined,
        publish: form.publish,
      }),
    onSuccess: (video) => navigate(`/watch/${video.id}`),
    onError: (mutationError) => setError(errorMessage(mutationError)),
  });

  const mediaReady = asset?.status === "ready";

  return (
    <div className="space-y-8 animate-fade-up">
      <header className="flex items-center gap-3">
        <span className="grid h-11 w-11 place-items-center rounded-2xl bg-violet/15 text-violet">
          <UploadCloud className="h-5 w-5" />
        </span>
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">Create</h1>
          <p className="text-sm text-haze">
            Uploads go straight to object storage with a short-lived signed URL; the worker handles the rest.
          </p>
        </div>
      </header>

      {storage.data && !storage.data.storage_configured ? (
        <ErrorNote message="Object storage is not configured on this server yet (S3_BUCKET, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY). Uploads will fail until it is." />
      ) : null}
      {storage.data && !storage.data.ffmpeg_available && storage.data.video_processing_enabled ? (
        <ErrorNote message="FFmpeg is not installed, so thumbnails and renditions cannot be generated. Install it on the worker host." />
      ) : null}

      <Card className="space-y-4">
        <h2 className="font-display text-lg font-semibold">1. Upload the file</h2>
        <UploadPanel purpose="video" onReady={setAsset} />
      </Card>

      <form
        className="space-y-6"
        onSubmit={(event) => {
          event.preventDefault();
          setError(null);
          publish.mutate();
        }}
      >
        <Card className="space-y-4">
          <h2 className="font-display text-lg font-semibold">2. Describe it</h2>
          <div>
            <FieldLabel htmlFor="title">Title</FieldLabel>
            <Input
              id="title"
              required
              minLength={2}
              maxLength={160}
              value={form.title}
              onChange={(event) => setForm((previous) => ({ ...previous, title: event.target.value }))}
              placeholder="60-second salsa routine"
            />
          </div>
          <div>
            <FieldLabel htmlFor="description">Description</FieldLabel>
            <Textarea
              id="description"
              value={form.description}
              onChange={(event) => setForm((previous) => ({ ...previous, description: event.target.value }))}
              placeholder="What should viewers take away from this?"
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <FieldLabel htmlFor="category">Category</FieldLabel>
              <select
                id="category"
                value={form.category}
                onChange={(event) => setForm((previous) => ({ ...previous, category: event.target.value }))}
                className="w-full rounded-2xl border border-ink-700/70 bg-ink-900/80 px-4 py-3 text-sm"
              >
                {VIDEO_CATEGORIES.map((category) => (
                  <option key={category} value={category}>
                    {titleCase(category)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <FieldLabel htmlFor="tags">Tags</FieldLabel>
              <Input
                id="tags"
                value={form.tags}
                onChange={(event) => setForm((previous) => ({ ...previous, tags: event.target.value }))}
                placeholder="dance, tutorial, beginners"
              />
            </div>
          </div>
        </Card>

        <Card className="space-y-4">
          <h2 className="font-display text-lg font-semibold">3. Who can see it</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <FieldLabel htmlFor="visibility">Visibility</FieldLabel>
              <select
                id="visibility"
                value={form.visibility}
                onChange={(event) => setForm((previous) => ({ ...previous, visibility: event.target.value }))}
                className="w-full rounded-2xl border border-ink-700/70 bg-ink-900/80 px-4 py-3 text-sm"
              >
                <option value="public">Public — appears in feeds and search</option>
                <option value="unlisted">Unlisted — only reachable by link</option>
                <option value="private">Private — only you</option>
              </select>
            </div>
            <label className="mt-6 flex items-start gap-3 text-sm text-haze">
              <input
                type="checkbox"
                checked={form.allow_comments}
                onChange={(event) => setForm((previous) => ({ ...previous, allow_comments: event.target.checked }))}
                className="mt-1 h-4 w-4 rounded border-ink-700 bg-ink-900 text-violet"
              />
              <span>
                <span className="block text-white">Allow comments</span>
                <span className="block text-xs">Replies stay one level deep, like the API models them.</span>
              </span>
            </label>
          </div>

          <label className="flex items-start gap-3 text-sm text-haze">
            <input
              type="checkbox"
              checked={form.is_learn_content}
              onChange={(event) => setForm((previous) => ({ ...previous, is_learn_content: event.target.checked }))}
              className="mt-1 h-4 w-4 rounded border-ink-700 bg-ink-900 text-sky"
            />
            <span>
              <span className="block text-white">Publish into LearnSpace</span>
              <span className="block text-xs">Educational content gets its own category and filters.</span>
            </span>
          </label>

          {form.is_learn_content ? (
            <div>
              <FieldLabel htmlFor="learn_category">LearnSpace topic</FieldLabel>
              <select
                id="learn_category"
                value={form.learn_category}
                onChange={(event) => setForm((previous) => ({ ...previous, learn_category: event.target.value }))}
                className="w-full rounded-2xl border border-ink-700/70 bg-ink-900/80 px-4 py-3 text-sm"
              >
                {LEARN_CATEGORIES.map((category) => (
                  <option key={category} value={category}>
                    {titleCase(category)}
                  </option>
                ))}
              </select>
            </div>
          ) : null}
        </Card>

        {error ? <ErrorNote message={error} /> : null}

        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-haze">
            {mediaReady
              ? "Media is processed and ready."
              : asset
                ? `Media status: ${asset.status}. Publishing needs it to be ready.`
                : "Upload a video to continue."}
          </p>
          <div className="flex gap-3">
            <Button
              type="button"
              variant="ghost"
              disabled={!mediaReady || form.title.trim().length < 2}
              onClick={() => {
                setForm((previous) => ({ ...previous, publish: false }));
                publish.mutate();
              }}
            >
              Save as draft
            </Button>
            <Button type="submit" size="lg" loading={publish.isPending} disabled={!mediaReady || form.title.trim().length < 2}>
              Publish
            </Button>
          </div>
        </div>
      </form>
    </div>
  );
}