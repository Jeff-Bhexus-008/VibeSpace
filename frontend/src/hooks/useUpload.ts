import { useEffect, useRef, useState } from "react";

import { api, putToStorage } from "@/lib/api";
import type { MediaAsset, UploadTicket } from "@/types/api";
import { errorMessage } from "@/lib/utils";

export type UploadPhase = "idle" | "requesting" | "uploading" | "processing" | "ready" | "failed";

interface UploadOptions {
  kind: "video" | "image" | "audio";
  purpose: "video" | "entry" | "avatar" | "cover" | "reference" | "message" | "message_image";
}

/**
 * Direct-to-storage upload:
 *  1. ask the API for a short-lived presigned URL (server authorises + picks the key)
 *  2. PUT the bytes straight to object storage with progress
 *  3. tell the API the upload finished, then poll processing until the asset is ready
 */
export function useUpload({ kind, purpose }: UploadOptions) {
  const [phase, setPhase] = useState<UploadPhase>("idle");
  const [progress, setProgress] = useState(0);
  const [asset, setAsset] = useState<MediaAsset | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cancelled = useRef(false);

  useEffect(() => () => void (cancelled.current = true), []);

  async function start(file: File) {
    setError(null);
    setProgress(0);
    setAsset(null);
    setPhase("requesting");
    try {
      const ticket = await api.post<UploadTicket>("/uploads/ticket", {
        kind,
        purpose,
        filename: file.name,
        declared_content_type: file.type || "application/octet-stream",
        size_bytes: file.size,
      });

      setPhase("uploading");
      await putToStorage(ticket.upload_url, file, file.type || "application/octet-stream", (percent) =>
        setProgress(percent),
      );

      setPhase("processing");
      const completed = await api.post<{ asset: MediaAsset; ready: boolean }>("/uploads/complete", {
        asset_id: ticket.asset_id,
      });
      setAsset(completed.asset);

      if (completed.ready) {
        setPhase("ready");
        return completed.asset;
      }

      const ready = await pollUntilReady(ticket.asset_id);
      setAsset(ready);
      setPhase("ready");
      return ready;
    } catch (uploadError) {
      setPhase("failed");
      setError(errorMessage(uploadError));
      return null;
    }
  }

  async function pollUntilReady(assetId: string, attempts = 40): Promise<MediaAsset> {
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      if (cancelled.current) break;
      await new Promise((resolve) => setTimeout(resolve, 3000));
      const status = await api.get<{ asset: MediaAsset; ready: boolean }>(`/uploads/${assetId}`);
      setAsset(status.asset);
      if (status.ready) return status.asset;
      if (status.asset.status === "failed") {
        throw new Error(status.asset.processing_error || "Processing failed. Check the worker logs.");
      }
    }
    throw new Error("Processing is taking longer than expected — check back in a moment.");
  }

  function reset() {
    setPhase("idle");
    setProgress(0);
    setAsset(null);
    setError(null);
  }

  return { phase, progress, asset, error, start, reset };
}