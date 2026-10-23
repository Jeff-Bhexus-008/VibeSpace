import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertOctagon, CheckCircle2, ScrollText, ShieldCheck, Tags, Users } from "lucide-react";

import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import { EmptyState, ErrorNote, Spinner } from "@/components/ui/Feedback";
import { FieldLabel, Input } from "@/components/ui/Input";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { errorMessage, timeAgo, titleCase } from "@/lib/utils";
import type { Report } from "@/types/api";

interface Stats {
  users: { total: number; suspended: number; creators: number; moderators: number; admins: number };
  content: { videos: number; removed_videos: number; comments: number; media_assets: number; storage_bytes: number };
  engagement: { total_views: number; messages: number };
  battles: { challenges: number; entries: number; votes: number };
  moderation: { open_reports: number; total_reports: number; actions: number };
}

export default function Admin() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [categoryForm, setCategoryForm] = useState({ slug: "", label: "", kind: "video" });
  const isAdmin = user?.role === "admin";

  const stats = useQuery({ queryKey: ["admin", "stats"], queryFn: () => api.get<Stats>("/admin/stats") });

  const reports = useQuery({
    queryKey: ["admin", "reports"],
    queryFn: () => api.get<{ items: Report[] }>("/moderation/reports", { status: "open", limit: 25 }),
  });

  const anomalies = useQuery({
    queryKey: ["admin", "votes"],
    queryFn: () =>
      api.get<{ anomalies: Array<{ voter_id: string; votes_in_window: number; window_minutes: number; reason: string }> }>(
        "/moderation/votes/suspicious",
      ),
  });

  const accounts = useQuery({
    queryKey: ["admin", "users"],
    queryFn: () => api.get<{ items: Array<Record<string, unknown>> }>("/admin/users", { limit: 25 }),
  });

  const actions = useQuery({
    queryKey: ["admin", "actions"],
    queryFn: () => api.get<{ items: Array<Record<string, unknown>> }>("/moderation/actions", { limit: 15 }),
  });

  const auditLog = useQuery({
    queryKey: ["admin", "audit"],
    queryFn: () => api.get<{ items: Array<Record<string, unknown>> }>("/admin/audit-logs", { limit: 20 }),
  });

  const categories = useQuery({
    queryKey: ["admin", "categories"],
    queryFn: () => api.get<{ items: Array<Record<string, unknown>> }>("/admin/categories", { limit: 50 }),
  });

  const resolve = useMutation({
    mutationFn: ({ id, action }: { id: string; action: string }) =>
      api.post(`/moderation/reports/${id}/resolve`, {
        status: "resolved",
        action,
        note: note || undefined,
      }),
    onSuccess: () => {
      setNote("");
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["admin"] });
    },
    onError: (mutationError) => setError(errorMessage(mutationError)),
  });

  const suspend = useMutation({
    mutationFn: (userId: string) =>
      api.post(`/moderation/users/${userId}/suspend`, { user_id: userId, reason: note || "Policy violation" }),
    onSuccess: () => {
      setNote("");
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["admin"] });
    },
    onError: (mutationError) => setError(errorMessage(mutationError)),
  });

  const reinstate = useMutation({
    mutationFn: (userId: string) => api.post(`/moderation/users/${userId}/reinstate`),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["admin"] }),
    onError: (mutationError) => setError(errorMessage(mutationError)),
  });

  const changeRole = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: string }) =>
      api.patch(`/admin/users/${userId}/role`, undefined, { role }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["admin"] }),
    onError: (mutationError) => setError(errorMessage(mutationError)),
  });

  const createCategory = useMutation({
    mutationFn: () =>
      api.post("/admin/categories", {
        slug: categoryForm.slug.trim().toLowerCase(),
        label: categoryForm.label.trim(),
        kind: categoryForm.kind,
      }),
    onSuccess: () => {
      setCategoryForm({ slug: "", label: "", kind: "video" });
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["admin", "categories"] });
      void queryClient.invalidateQueries({ queryKey: ["categories"] });
    },
    onError: (mutationError) => setError(errorMessage(mutationError)),
  });

  return (
    <div className="space-y-8 animate-fade-up">
      <header>
        <h1 className="flex items-center gap-2 font-display text-2xl font-semibold tracking-tight">
          <ShieldCheck className="h-5 w-5 text-sky" /> {isAdmin ? "Administration" : "Moderation"}
        </h1>
        <p className="mt-1 text-sm text-haze">
          {isAdmin
            ? "Platform statistics, accounts, categories and the full audit trail."
            : "Reports, content actions and voting anomalies. Administrative tools require the admin role."}
        </p>
      </header>

      {error ? <ErrorNote message={error} /> : null}

      {stats.isLoading ? (
        <Spinner />
      ) : stats.data ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile label="Accounts" value={stats.data.users.total} hint={`${stats.data.users.suspended} suspended`} />
          <StatTile label="Videos" value={stats.data.content.videos} hint={`${stats.data.content.removed_videos} removed`} />
          <StatTile label="Open reports" value={stats.data.moderation.open_reports} hint={`${stats.data.moderation.actions} actions logged`} />
          <StatTile label="Battle votes" value={stats.data.battles.votes} hint={`${stats.data.battles.challenges} battles`} />
        </div>
      ) : null}

      <Card className="space-y-4">
        <h2 className="flex items-center gap-2 font-display text-lg font-semibold">
          <AlertOctagon className="h-4 w-4 text-coral" /> Open reports
        </h2>
        <Input
          value={note}
          onChange={(event) => setNote(event.target.value)}
          placeholder="Resolution note (stored with the action)"
        />
        {reports.isLoading ? (
          <Spinner />
        ) : reports.data && reports.data.items.length > 0 ? (
          <ul className="space-y-3">
            {reports.data.items.map((report) => (
              <li key={report.id} className="rounded-2xl border border-ink-800/70 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium">
                      {titleCase(report.target_type)} · {titleCase(report.reason)}
                    </p>
                    <p className="text-[11px] text-haze">
                      reported by @{report.reporter?.username} · {timeAgo(report.created_at)}
                    </p>
                    {typeof report.target_preview?.title === "string" ? (
                      <p className="mt-1 text-xs text-haze">“{report.target_preview.title}”</p>
                    ) : null}
                    {report.details ? <p className="mt-1 text-xs text-haze">{report.details}</p> : null}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="ghost" onClick={() => resolve.mutate({ id: report.id, action: "none" })}>
                      Dismiss
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => resolve.mutate({ id: report.id, action: "content_removed" })}
                    >
                      Remove content
                    </Button>
                    <Button size="sm" variant="danger" onClick={() => resolve.mutate({ id: report.id, action: "user_suspended" })}>
                      Suspend account
                    </Button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No open reports" description="The queue is clear." icon={<CheckCircle2 className="h-6 w-6" />} />
        )}
      </Card>

      <Card className="space-y-4">
        <h2 className="font-display text-lg font-semibold">Suspicious voting</h2>
        {anomalies.data && anomalies.data.anomalies.length > 0 ? (
          <ul className="space-y-2 text-sm">
            {anomalies.data.anomalies.map((anomaly) => (
              <li key={anomaly.voter_id} className="flex items-center justify-between rounded-2xl border border-ink-800/70 px-3 py-2">
                <span className="font-mono text-xs">{anomaly.voter_id.slice(0, 8)}…</span>
                <span className="text-xs text-haze">{anomaly.reason}</span>
                <Badge tone="danger">flagged</Badge>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-haze">No unusual voting bursts in the last 15 minutes.</p>
        )}
      </Card>

      <Card className="space-y-4">
        <h2 className="flex items-center gap-2 font-display text-lg font-semibold">
          <Users className="h-4 w-4 text-violet" /> Accounts
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[36rem] text-sm">
            <thead className="text-left text-[11px] uppercase tracking-wide text-haze">
              <tr>
                <th className="pb-3">Username</th>
                <th className="pb-3">Role</th>
                <th className="pb-3">Status</th>
                <th className="pb-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-800/70">
              {(accounts.data?.items ?? []).map((account) => {
                const id = String(account.id);
                return (
                  <tr key={id}>
                    <td className="py-3">@{String(account.username)}</td>
                    <td className="py-3">{titleCase(String(account.role))}</td>
                    <td className="py-3">
                      {account.is_suspended ? <Badge tone="danger">suspended</Badge> : <Badge tone="lime">active</Badge>}
                    </td>
                    <td className="py-3 text-right">
                      <div className="flex justify-end gap-2">
                        {account.is_suspended ? (
                          <Button size="sm" variant="secondary" onClick={() => reinstate.mutate(id)}>
                            Reinstate
                          </Button>
                        ) : (
                          <Button size="sm" variant="ghost" onClick={() => suspend.mutate(id)}>
                            Suspend
                          </Button>
                        )}
                        {isAdmin ? (
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => changeRole.mutate({ userId: id, role: "creator" })}
                          >
                            Make creator
                          </Button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {isAdmin ? (
          <p className="text-[11px] text-haze">
            Role changes are limited to creators/users here; grant moderator or admin deliberately through the API
            so the change is audited.
          </p>
        ) : null}
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="space-y-4">
          <h2 className="flex items-center gap-2 font-display text-lg font-semibold">
            <ScrollText className="h-4 w-4 text-haze" /> Moderation history
          </h2>
          {actions.data && actions.data.items.length > 0 ? (
            <ul className="space-y-2 text-xs">
              {actions.data.items.map((action) => (
                <li key={String(action.id)} className="rounded-2xl border border-ink-800/70 px-3 py-2">
                  <p className="text-sm">{titleCase(String(action.action_type))}</p>
                  <p className="text-[11px] text-haze">
                    {String(action.target_type)} · {timeAgo(String(action.created_at))}
                    {action.reason ? ` · ${String(action.reason)}` : ""}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-haze">No moderation actions recorded yet.</p>
          )}
        </Card>

        <Card className="space-y-4">
          <h2 className="font-display text-lg font-semibold">Audit log</h2>
          {auditLog.data && auditLog.data.items.length > 0 ? (
            <ul className="space-y-2 font-mono text-[11px]">
              {auditLog.data.items.map((entry) => (
                <li key={String(entry.id)} className="rounded-2xl border border-ink-800/70 px-3 py-2">
                  <span className="text-violet-soft">{String(entry.action)}</span>{" "}
                  {entry.entity_type ? <span className="text-haze">on {String(entry.entity_type)}</span> : null}
                  <span className="block text-haze">{timeAgo(String(entry.created_at))}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-haze">No audited actions yet.</p>
          )}
        </Card>
      </div>

      <Card className="space-y-4">
        <h2 className="flex items-center gap-2 font-display text-lg font-semibold">
          <Tags className="h-4 w-4 text-lime" /> Categories
        </h2>
        <div className="flex flex-wrap gap-2">
          {(categories.data?.items ?? []).map((category) => (
            <span key={String(category.id)} className="vs-chip">
              {String(category.label)} · {String(category.kind)}
            </span>
          ))}
        </div>
        {isAdmin ? (
          <form
            className="grid gap-3 sm:grid-cols-[1fr_1fr_auto_auto]"
            onSubmit={(event) => {
              event.preventDefault();
              createCategory.mutate();
            }}
          >
            <div>
              <FieldLabel htmlFor="slug">Slug</FieldLabel>
              <Input
                id="slug"
                value={categoryForm.slug}
                onChange={(event) => setCategoryForm((previous) => ({ ...previous, slug: event.target.value }))}
                placeholder="street_food"
              />
            </div>
            <div>
              <FieldLabel htmlFor="label">Label</FieldLabel>
              <Input
                id="label"
                value={categoryForm.label}
                onChange={(event) => setCategoryForm((previous) => ({ ...previous, label: event.target.value }))}
                placeholder="Street food"
              />
            </div>
            <div>
              <FieldLabel htmlFor="kind">Kind</FieldLabel>
              <select
                id="kind"
                value={categoryForm.kind}
                onChange={(event) => setCategoryForm((previous) => ({ ...previous, kind: event.target.value }))}
                className="h-11 rounded-2xl border border-ink-700/70 bg-ink-900/80 px-3 text-sm"
              >
                <option value="video">video</option>
                <option value="learn">learn</option>
                <option value="battle">battle</option>
              </select>
            </div>
            <div className="flex items-end">
              <Button
                type="submit"
                loading={createCategory.isPending}
                disabled={categoryForm.slug.length < 2 || categoryForm.label.length < 2}
              >
                Add
              </Button>
            </div>
          </form>
        ) : null}
      </Card>
    </div>
  );
}

function StatTile({ label, value, hint }: { label: string; value: number; hint?: string }) {
  return (
    <Card>
      <p className="text-[11px] uppercase tracking-wide text-haze">{label}</p>
      <p className="mt-1 font-display text-2xl font-semibold">{value}</p>
      {hint ? <p className="mt-1 text-xs text-haze">{hint}</p> : null}
    </Card>
  );
}