# Cloudflare R2 video storage — setup

VibeSpace stores uploaded video in **Cloudflare R2** through the backend's existing
S3-compatible storage layer. No new storage code path, no new bucket per user, and no
R2 credentials anywhere in the frontend bundle.

## How upload works

```
Browser                Render API                      Cloudflare R2
   |  POST /api/v1/uploads/ticket  |                          |
   |----------------------------->|  presign PUT (15 min TTL) |
   |<-----------------------------|                          |
   |  PUT file bytes (direct)     |                          |
   |-------------------------------------------------------->|
   |  POST /api/v1/uploads/complete                          |
   |----------------------------->|  HEAD object + byte sniff |
   |                              |------------------------->|
   |                              |  metadata -> Neon        |
   |  POST /api/v1/videos         |                          |
   |----------------------------->|  published video         |
```

Large files never pass through Render. The backend only ever sees metadata and
short-lived signed URLs.

## 1. Create the bucket

Cloudflare dashboard → **R2** → *Create bucket* → name it e.g. `vibespace-media`.
Leave public access **off** unless you configure a custom delivery domain (below).

## 2. Create a least-privilege token

**R2 → Manage R2 API Tokens → Create API token**

- Permissions: **Object Read & Write**
- Scope: **only the `vibespace-media` bucket**
- No admin/all-buckets permissions

The **Access Key ID** and **Secret Access Key** are shown once. Store them only in
Render's environment.

## 3. Environment variables (Render → VibeSpace → Environment)

| Variable | Required | Value |
| --- | --- | --- |
| `R2_ACCOUNT_ID` | yes | Cloudflare account ID (R2 overview page) |
| `R2_ACCESS_KEY_ID` | yes | from the token above |
| `R2_SECRET_ACCESS_KEY` | yes | from the token above |
| `R2_BUCKET_NAME` | yes | `vibespace-media` |
| `R2_PUBLIC_BASE_URL` | optional | public/custom delivery domain, no trailing slash |
| `VIDEO_PROCESSING_ENABLED` | yes on Render free | `false` |

The endpoint is derived automatically as
`https://<R2_ACCOUNT_ID>.r2.cloudflarestorage.com`. The generic `S3_*` variables still
work for AWS S3, MinIO and B2; R2 values take precedence when set.

**Never** put these in Vercel/Vite variables (`VITE_*` values are compiled into the
public bundle).

## 4. Bucket CORS (required for browser uploads)

R2 dashboard → your bucket → **Settings → CORS Policy** → paste:

```json
[
  {
    "AllowedOrigins": ["https://vibe-space-4nzp.vercel.app"],
    "AllowedMethods": ["GET", "PUT", "HEAD"],
    "AllowedHeaders": ["content-type", "content-length"],
    "ExposeHeaders": ["etag"],
    "MaxAgeSeconds": 3600
  }
]
```

This is separate from the API's own `CORS_ORIGINS` setting. Without it the browser's
`PUT` to R2 fails with a CORS error even though the presigned URL is valid.
Add `http://localhost:5173` to `AllowedOrigins` only while developing locally.

## 5. Playback delivery — pick one

**A. Private bucket (default, no extra config).**
No `R2_PUBLIC_BASE_URL`. Playback URLs point at
`https://vibespace-oefq.onrender.com/api/v1/media/{asset_id}/stream`, which authorises
the viewer and 307-redirects to a freshly signed R2 URL on every request. Links in the
database therefore never expire, and byte-range requests (seeking) pass through.

**B. Public delivery domain.**
Connect a custom domain (or enable the rate-limited `r2.dev` subdomain) and set
`R2_PUBLIC_BASE_URL=https://media.yourdomain.com`. Objects are then served directly
from Cloudflare's edge with native range support. Only do this if the uploaded content
is meant to be publicly playable.

## 6. What is and isn't supported without a worker

Render's free instance has no FFmpeg and no Celery worker, so
`VIDEO_PROCESSING_ENABLED=false`:

- MP4 / MOV / WebM / M4V / MKV are accepted and served **as uploaded**
- No transcoding, no thumbnails, no duration probing, no renditions
- Browser playback depends on the codec inside the file — H.264/AAC MP4 and VP8/VP9
  WebM play everywhere; MOV files with ProRes or HEVC will not play in most browsers
- Duration and thumbnail come back empty; the UI falls back gracefully

Setting up a worker host with FFmpeg (the `vibespace-worker` service in `render.yaml`)
restores thumbnails, duration and renditions.

## 7. Verify

```bash
curl https://vibespace-oefq.onrender.com/api/v1/uploads/config/status
# {"storage_configured":true,"storage_backend":"cloudflare_r2","public_delivery":false,...}
```

Then upload through the live Create screen and confirm the object appears under
`video/video/<owner-id>/` in the bucket.
