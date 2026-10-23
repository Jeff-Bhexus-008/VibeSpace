import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { BarChart3, Eye, Film, Heart, Info } from "lucide-react";

import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import { EmptyState, Spinner } from "@/components/ui/Feedback";
import { api } from "@/lib/api";
import { compactNumber, timeAgo, titleCase } from "@/lib/utils";
import type { AnalyticsSeries, CreatorSummary } from "@/types/api";

interface CreatorVideoRow {
  id: string;
  title: string;
  status: string;
  visibility: string;
  thumbnail_url?: string | null;
  view_count: number;
  unique_view_count: number;
  like_count: number;
  comment_count: number;
  save_count: number;
  share_count: number;
  published_at?: string | null;
}

export default function CreatorDashboard() {
  const [range, setRange] = useState(30);
  const [sort, setSort] = useState<"recent" | "views" | "likes" | "comments">("recent");

  const summary = useQuery({
    queryKey: ["creator", "summary"],
    queryFn: () => api.get<CreatorSummary>("/creator/summary"),
  });

  const videos = useQuery({
    queryKey: ["creator", "videos", sort],
    queryFn: () => api.get<{ items: CreatorVideoRow[] }>("/creator/videos", { sort, limit: 25 }),
  });

  const drafts = useQuery({
    queryKey: ["creator", "drafts"],
    queryFn: () => api.get<{ items: CreatorVideoRow[] }>("/creator/drafts", { limit: 10 }),
  });

  const analytics = useQuery({
    queryKey: ["creator", "analytics", range],
    queryFn: () => api.get<AnalyticsSeries>("/creator/analytics", { range_days: range }),
  });

  const notices = useQuery({
    queryKey: ["creator", "notices"],
    queryFn: () => api.get<{ items: Array<{ id: string; action_type: string; reason?: string | null; created_at?: string | null; target_title?: string | null }> }>(
      "/creator/moderation-notices",
      { limit: 10 },
    ),
  });

  return (
    <div className="space-y-8 animate-fade-up">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 font-display text-2xl font-semibold tracking-tight">
            <BarChart3 className="h-5 w-5 text-lime" /> CreatorSpace
          </h1>
          <p className="mt-1 text-sm text-haze">
            Every number here is computed by the API from stored rows — nothing is estimated.
          </p>
        </div>
        <Link to="/create">
          <Button size="sm">Publish something new</Button>
        </Link>
      </header>

      {summary.isLoading ? (
        <div className="flex justify-center py-12">
          <Spinner className="h-7 w-7" />
        </div>
      ) : summary.data ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Metric label="Videos" value={summary.data.video_count} hint={`${summary.data.published_count} published`} />
          <Metric label="Total views" value={summary.data.total_views} hint={`${summary.data.unique_views} unique`} />
          <Metric label="Likes" value={summary.data.total_likes} hint={`${summary.data.total_comments} comments`} />
          <Metric
            label="Engagement"
            value={summary.data.engagement_rate}
            suffix="%"
            hint={`${compactNumber(summary.data.follower_count)} followers`}
          />
        </div>
      ) : null}

      <Card className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-display text-lg font-semibold">Activity</h2>
          <div className="flex gap-2">
            {[7, 30, 90].map((days) => (
              <button
                key={days}
                type="button"
                onClick={() => setRange(days)}
                className={`rounded-full border px-3 py-1 text-[11px] transition ${
                  range === days ? "border-lime/50 bg-lime/15 text-white" : "border-ink-700/70 text-haze"
                }`}
              >
                {days} days
              </button>
            ))}
          </div>
        </div>

        {analytics.isLoading ? (
          <Spinner />
        ) : analytics.data?.has_data ? (
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={analytics.data.points}>
                <CartesianGrid stroke="hsl(var(--ink-800))" strokeDasharray="4 4" />
                <XAxis dataKey="day" stroke="hsl(var(--haze))" fontSize={11} />
                <YAxis stroke="hsl(var(--haze))" fontSize={11} allowDecimals={false} />
                <Tooltip
                  contentStyle={{
                    background: "hsl(var(--ink-900))",
                    border: "1px solid hsl(var(--ink-700))",
                    borderRadius: 14,
                    fontSize: 12,
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line type="monotone" dataKey="views" stroke="hsl(var(--vibe-violet))" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="likes" stroke="hsl(var(--vibe-coral))" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="comments" stroke="hsl(var(--vibe-sky))" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <EmptyState
            title="No analytics yet"
            description="Views, likes and comments appear here once people interact with your published videos."
            icon={<Eye className="h-6 w-6" />}
          />
        )}
      </Card>

      <Card>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-display text-lg font-semibold">Your videos</h2>
          <div className="flex gap-2">
            {(["recent", "views", "likes", "comments"] as const).map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setSort(value)}
                className={`rounded-full border px-3 py-1 text-[11px] transition ${
                  sort === value ? "border-violet/50 bg-violet/15 text-white" : "border-ink-700/70 text-haze"
                }`}
              >
                {titleCase(value)}
              </button>
            ))}
          </div>
        </div>

        {videos.isLoading ? (
          <Spinner />
        ) : videos.data && videos.data.items.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[42rem] text-sm">
              <thead className="text-left text-[11px] uppercase tracking-wide text-haze">
                <tr>
                  <th className="pb-3">Video</th>
                  <th className="pb-3">Status</th>
                  <th className="pb-3 text-right">Views</th>
                  <th className="pb-3 text-right">Unique</th>
                  <th className="pb-3 text-right">Likes</th>
                  <th className="pb-3 text-right">Comments</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-800/70">
                {videos.data.items.map((video) => (
                  <tr key={video.id}>
                    <td className="py-3">
                      <Link to={`/watch/${video.id}`} className="flex items-center gap-3 hover:text-violet-soft">
                        {video.thumbnail_url ? (
                          <img src={video.thumbnail_url} alt="" className="h-10 w-16 rounded-lg object-cover" />
                        ) : (
                          <span className="grid h-10 w-16 place-items-center rounded-lg bg-ink-850 text-haze">
                            <Film className="h-4 w-4" />
                          </span>
                        )}
                        <span className="line-clamp-1 max-w-xs">{video.title}</span>
                      </Link>
                    </td>
                    <td className="py-3">
                      <Badge tone={video.published_at ? "lime" : "neutral"}>
                        {video.published_at ? "published" : "draft"}
                      </Badge>
                    </td>
                    <td className="py-3 text-right">{compactNumber(video.view_count)}</td>
                    <td className="py-3 text-right">{compactNumber(video.unique_view_count)}</td>
                    <td className="py-3 text-right">{compactNumber(video.like_count)}</td>
                    <td className="py-3 text-right">{compactNumber(video.comment_count)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="You have not published anything yet"
            description="Upload a video and it will appear here with live metrics."
            action={
              <Link to="/create">
                <Button size="sm">Publish a video</Button>
              </Link>
            }
          />
        )}
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <h2 className="mb-4 font-display text-lg font-semibold">Drafts and unlisted</h2>
          {drafts.data && drafts.data.items.length > 0 ? (
            <ul className="space-y-2 text-sm">
              {drafts.data.items.map((video) => (
                <li key={video.id} className="flex items-center justify-between gap-3 rounded-2xl border border-ink-800/70 px-3 py-2">
                  <Link to={`/watch/${video.id}`} className="truncate hover:text-violet-soft">
                    {video.title}
                  </Link>
                  <span className="text-[11px] text-haze">{titleCase(video.visibility)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-haze">No unpublished videos.</p>
          )}
        </Card>

        <Card>
          <h2 className="mb-4 flex items-center gap-2 font-display text-lg font-semibold">
            <Info className="h-4 w-4 text-coral" /> Moderation notices
          </h2>
          {notices.data && notices.data.items.length > 0 ? (
            <ul className="space-y-2 text-sm">
              {notices.data.items.map((notice) => (
                <li key={notice.id} className="rounded-2xl border border-ink-800/70 px-3 py-2">
                  <p className="text-sm">{titleCase(notice.action_type)}</p>
                  <p className="text-[11px] text-haze">
                    {notice.target_title ? `${notice.target_title} · ` : ""}
                    {timeAgo(notice.created_at)}
                  </p>
                  {notice.reason ? <p className="mt-1 text-xs text-haze">{notice.reason}</p> : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-haze">No moderation actions on your content.</p>
          )}
        </Card>
      </div>

      <Card className="flex flex-wrap items-center gap-3 text-xs text-haze">
        <Heart className="h-4 w-4 text-coral" />
        Monetisation is not part of this build. The creator metrics above are the foundation it would use.
      </Card>
    </div>
  );
}

function Metric({
  label,
  value,
  hint,
  suffix,
}: {
  label: string;
  value: number;
  hint?: string;
  suffix?: string;
}) {
  return (
    <Card>
      <p className="text-[11px] uppercase tracking-wide text-haze">{label}</p>
      <p className="mt-1 font-display text-2xl font-semibold">
        {compactNumber(value)}
        {suffix ?? ""}
      </p>
      {hint ? <p className="mt-1 text-xs text-haze">{hint}</p> : null}
    </Card>
  );
}