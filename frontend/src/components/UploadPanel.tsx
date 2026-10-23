import { useRef, useState } from "react";
import { Film, Image as ImageIcon, UploadCloud } from "lucide-react";

import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { ErrorNote, Spinner } from "@/components/ui/Feedback";
import { useUpload, type UploadPhase } from "@/hooks/useUpload";
import { cn, formatDuration } from "@/lib/utils";
import type { MediaAsset } from "@/types/api";

const PHASE_COPY: Record<UploadPhase, string> = {
  idle: "Waiting for a file",
  requesting: "Authorising upload…",
  uploading: "Uploading to storage…",
  processing: "Processing video (probe, thumbnail, renditions)…",
  ready: "Ready to publish",
  failed: "Upload failed",
};

/**
 * Uploads a video straight to object storage using a presigned URL
 * (bytes never pass through the API), then reports the finished asset back.
 */
export default function UploadPanel({
  purpose = "video",
  onReady,
}: {
  purpose?: "video" | "entry" | "reference";
  onReady?: (asset: MediaAsset) => void;
}) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const { phase, progress, asset, error, start, reset } = useUpload({ kind: "video", purpose });
  const [dragging, setDragging] = useState(false);

  async function handleFiles(files: FileList | null) {
    const file = files?.[0];
    if (!file) return;
    const uploaded = await start(file);
    if (uploaded && onReady) onReady(uploaded);
  }

  return (
    <div className="space-y-4">
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          void handleFiles(event.dataTransfer.files);
        }}
        className={cn(
          "flex flex-col items-center justify-center gap-3 rounded-3xl border-2 border-dashed px-6 py-10 text-center transition",
          dragging ? "border-violet bg-violet/10" : "border-ink-700/70 bg-ink-900/40",
        )}
      >
        <UploadCloud className="h-8 w-8 text-violet" />
        <div>
          <p className="font-display text-sm font-semibold">Drop a video here</p>
          <p className="mt-1 text-xs text-haze">MP4, MOV, WEBM or MKV — up to 250 MB by default.</p>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept="video/mp4,video/quicktime,video/webm,video/x-matroska"
          className="hidden"
          onChange={(event) => void handleFiles(event.target.files)}
        />
        <Button size="sm" variant="secondary" onClick={() => inputRef.current?.click()} loading={phase === "requesting"}>
          Choose a file
        </Button>
      </div>

      <div className="flex items-center justify-between text-xs text-haze">
        <span className="inline-flex items-center gap-2">
          {phase === "processing" ? <Spinner className="h-4 w-4" /> : null}
          {PHASE_COPY[phase]}
        </span>
        {asset ? (
          <Badge tone={phase === "ready" ? "lime" : phase === "failed" ? "danger" : "violet"}>
            {asset.status}
          </Badge>
        ) : null}
      </div>

      {phase === "uploading" ? (
        <div className="h-2 overflow-hidden rounded-full bg-ink-800">
          <div className="h-full rounded-full bg-violet transition-all" style={{ width: `${progress}%` }} />
        </div>
      ) : null}

      {error ? <ErrorNote message={error} /> : null}

      {asset && phase === "ready" ? (
        <div className="flex items-center gap-4 rounded-2xl border border-ink-800/80 bg-ink-900/60 p-3">
          {asset.thumbnail_url ? (
            <img src={asset.thumbnail_url} alt="Thumbnail" className="h-16 w-24 rounded-xl object-cover" />
          ) : (
            <div className="grid h-16 w-24 place-items-center rounded-xl bg-ink-850 text-haze">
              <Film className="h-5 w-5" />
            </div>
          )}
          <div className="text-xs text-haze">
            <p className="text-sm text-white">{formatDuration(asset.duration_seconds)}</p>
            <p>
              {asset.width}×{asset.height} · {asset.renditions.length} rendition(s)
            </p>
            <p className="mt-1 inline-flex items-center gap-1">
              <ImageIcon className="h-3.5 w-3.5" /> thumbnail generated
            </p>
          </div>
          <Button size="sm" variant="ghost" className="ml-auto" onClick={reset}>
            Replace
          </Button>
        </div>
      ) : null}
    </div>
  );
}