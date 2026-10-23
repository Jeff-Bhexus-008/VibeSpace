import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock, Flag, ThumbsUp, Trophy, UserPlus, Users } from "lucide-react";

import Avatar from "@/components/ui/Avatar";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import UploadPanel from "@/components/UploadPanel";
import { EmptyState, ErrorNote, Spinner } from "@/components/ui/Feedback";
import { FieldLabel, Input } from "@/components/ui/Input";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { compactNumber, countdown, errorMessage, timeAgo, titleCase } from "@/lib/utils";
import type { Challenge, ChallengeEntry, MediaAsset, Page, StandingRow } from "@/types/api";

export default function BattleDetail() {
  const { challengeId = "" } = useParams();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [inviteUsername, setInviteUsername] = useState("");
  const [entryForm, setEntryForm] = useState<{ asset: MediaAsset | null; title: string }>({
    asset: null,
    title: "",
  });
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);

  const battle = useQuery({
    queryKey: ["battle", challengeId],
    queryFn: () => api.get<Challenge>(`/challenges/${challengeId}`),
    enabled: Boolean(challengeId),
  });

  const entries = useQuery({
    queryKey: ["battle", challengeId, "entries"],
    queryFn: () => api.get<Page<ChallengeEntry>>(`/challenges/${challengeId}/entries`, { limit: 50 }),
    enabled: Boolean(challengeId),
  });

  const standings = useQuery({
    queryKey: ["battle", challengeId, "standings"],
    queryFn: () =>
      api.get<{ is_final: boolean; rows: StandingRow[]; note: string | null }>(`/challenges/${challengeId}/standings`),
    enabled: Boolean(challengeId),
  });

  const participants = useQuery({
    queryKey: ["battle", challengeId, "participants"],
    queryFn: () => api.get<Page<{ id: string; user_id: string; role: string; user?: { username: string } | null }>>(
      `/challenges/${challengeId}/participants`,
      { limit: 50 },
    ),
    enabled: Boolean(challengeId),
  });

  // Local countdown so the deadline ticks visibly without extra requests.
  useEffect(() => {
    if (!battle.data?.deadline_at) return undefined;
    const deadline = new Date(battle.data.deadline_at).getTime();
    const tick = () => setSecondsLeft(Math.max(0, Math.floor((deadline - Date.now()) / 1000)));
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [battle.data?.deadline_at]);

  const refreshBattle = () => {
    void queryClient.invalidateQueries({ queryKey: ["battle", challengeId] });
  };

  const join = useMutation({
    mutationFn: () => api.post<{ message: string }>(`/challenges/${challengeId}/join`),
    onSuccess: (result: { message?: string }) => {
      setNotice(result.message ?? "Joined.");
      refreshBattle();
    },
    onError: (mutationError) => setError(errorMessage(mutationError)),
  });

  const leave = useMutation({
    mutationFn: () => api.del(`/challenges/${challengeId}/join`),
    onSuccess: () => {
      setNotice("You left this battle.");
      refreshBattle();
    },
    onError: (mutationError) => setError(errorMessage(mutationError)),
  });

  const invite = useMutation({
    mutationFn: () =>
      api.post<{ message: string }>(`/challenges/${challengeId}/invite`, undefined, { username: inviteUsername }),
    onSuccess: (result: { message?: string }) => {
      setNotice(result.message ?? "Invitation sent.");
      setInviteUsername("");
      refreshBattle();
    },
    onError: (mutationError) => setError(errorMessage(mutationError)),
  });

  const submitEntry = useMutation({
    mutationFn: () =>
      api.post<ChallengeEntry>(`/challenges/${challengeId}/entries`, {
        media_asset_id: entryForm.asset?.id,
        title: entryForm.title.trim(),
      }),
    onSuccess: () => {
      setNotice("Entry submitted.");
      setEntryForm({ asset: null, title: "" });
      void queryClient.invalidateQueries({ queryKey: ["battle", challengeId] });
    },
    onError: (mutationError) => setError(errorMessage(mutationError)),
  });

  const vote = useMutation({
    mutationFn: (entryId: string) => api.post(`/challenges/${challengeId}/vote`, { entry_id: entryId }),
    onSuccess: () => {
      setNotice("Vote recorded.");
      void queryClient.invalidateQueries({ queryKey: ["battle", challengeId] });
    },
    onError: (mutationError) => setError(errorMessage(mutationError)),
  });

  const changeState = useMutation({
    mutationFn: (status: string) => api.post(`/challenges/${challengeId}/state`, { status }),
    onSuccess: () => {
      setNotice("Battle state updated.");
      refreshBattle();
    },
    onError: (mutationError) => setError(errorMessage(mutationError)),
  });

  const finalize = useMutation({
    mutationFn: () => api.post(`/challenges/${challengeId}/finalize`),
    onSuccess: () => {
      setNotice("Official results published.");
      void queryClient.invalidateQueries({ queryKey: ["battle", challengeId] });
    },
    onError: (mutationError) => setError(errorMessage(mutationError)),
  });

  const disqualify = useMutation({
    mutationFn: ({ entryId, reason }: { entryId: string; reason: string }) =>
      api.post(`/challenges/${challengeId}/entries/${entryId}/disqualify`, undefined, { reason }),
    onSuccess: () => {
      setNotice("Entry disqualified.");
      void queryClient.invalidateQueries({ queryKey: ["battle", challengeId] });
    },
    onError: (mutationError) => setError(errorMessage(mutationError)),
  });

  const dispute = useMutation({
    mutationFn: () =>
      api.post(`/challenges/${challengeId}/disputes`, {
        reason: "suspicious_votes",
        details: "I would like the moderation team to review the voting on this battle.",
      }),
    onSuccess: () => setNotice("Dispute submitted to the moderation team."),
    onError: (mutationError) => setError(errorMessage(mutationError)),
  });

  if (battle.isLoading) {
    return (
      <div className="flex justify-center py-24">
        <Spinner className="h-8 w-8" />
      </div>
    );
  }

  if (battle.isError || !battle.data) {
    return (
      <EmptyState
        title="This battle is not available"
        description={errorMessage(battle.error)}
        action={
          <Link to="/battles">
            <Button size="sm">Browse battles</Button>
          </Link>
        }
      />
    );
  }

  const data = battle.data;
  const isStaff = user?.role === "moderator" || user?.role === "admin";
  const live = data.status === "open" || data.status === "active" || data.status === "voting";

  return (
    <div className="space-y-8 animate-fade-up">
      <header className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <Badge tone={live ? "violet" : data.status === "completed" ? "lime" : "neutral"}>
            {titleCase(data.status)}
          </Badge>
          <span className="vs-chip">{titleCase(data.category)}</span>
          <span className="vs-chip">{titleCase(data.format)}</span>
          {data.is_public ? null : <span className="vs-chip">Private</span>}
        </div>

        <h1 className="font-display text-3xl font-semibold leading-tight tracking-tight">{data.title}</h1>
        {data.description ? <p className="max-w-3xl text-sm leading-relaxed text-haze">{data.description}</p> : null}

        <div className="flex flex-wrap items-center gap-5 text-xs text-haze">
          <span className="inline-flex items-center gap-2">
            <Avatar src={data.creator?.avatar_url} name={data.creator?.username} size="sm" />
            <Link to={`/u/${data.creator?.username}`} className="hover:text-white">
              @{data.creator?.username}
            </Link>
            {data.opponent ? <span>vs @{data.opponent.username}</span> : null}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Clock className="h-3.5 w-3.5" />
            {data.status === "completed" ? "Finished" : countdown(data.deadline_at, secondsLeft ?? data.seconds_remaining)}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Users className="h-3.5 w-3.5" /> {compactNumber(data.participant_count)} participants
          </span>
          <span className="inline-flex items-center gap-1.5">
            <ThumbsUp className="h-3.5 w-3.5" /> {compactNumber(data.vote_count)} votes
          </span>
        </div>
      </header>

      {error ? <ErrorNote message={error} /> : null}
      {notice ? (
        <p className="rounded-2xl border border-lime/40 bg-lime/10 px-4 py-3 text-sm text-lime">{notice}</p>
      ) : null}

      <div className="flex flex-wrap gap-3">
        {user ? (
          data.has_joined ? (
            <Button variant="secondary" size="sm" loading={leave.isPending} onClick={() => leave.mutate()}>
              Leave battle
            </Button>
          ) : (
            <Button size="sm" loading={join.isPending} onClick={() => join.mutate()} disabled={!live}>
              <UserPlus className="h-4 w-4" /> {live ? "Join this battle" : "Not open"}
            </Button>
          )
        ) : (
          <Link to="/login">
            <Button size="sm" variant="secondary">
              Sign in to join
            </Button>
          </Link>
        )}
        {user ? (
          <Button variant="ghost" size="sm" loading={dispute.isPending} onClick={() => dispute.mutate()}>
            <Flag className="h-4 w-4" /> Dispute the result
          </Button>
        ) : null}
      </div>

      <div className="grid gap-8 lg:grid-cols-[1.5fr_1fr]">
        <div className="space-y-6">
          <section>
            <h2 className="mb-4 font-display text-lg font-semibold">Entries</h2>
            {entries.isLoading ? (
              <Spinner />
            ) : entries.data && entries.data.items.length > 0 ? (
              <div className="grid gap-5 sm:grid-cols-2">
                {entries.data.items.map((entry) => (
                  <article key={entry.id} className="overflow-hidden rounded-3xl border border-ink-800/80 bg-ink-900/60">
                    {entry.playback_url ? (
                      <video
                        src={entry.playback_url}
                        poster={entry.thumbnail_url ?? undefined}
                        controls
                        playsInline
                        className="aspect-video w-full bg-black object-cover"
                      />
                    ) : (
                      <div className="grid aspect-video place-items-center bg-ink-850 text-haze">
                        Preview unavailable
                      </div>
                    )}
                    <div className="space-y-2 p-4">
                      <div className="flex items-start justify-between gap-2">
                        <h3 className="font-display text-sm font-semibold">{entry.title}</h3>
                        {entry.status !== "submitted" && entry.status !== "approved" ? (
                          <Badge tone="danger">{titleCase(entry.status)}</Badge>
                        ) : null}
                      </div>
                      <p className="text-xs text-haze">
                        @{entry.user?.username} · {timeAgo(entry.submitted_at)} · {compactNumber(entry.vote_count)} votes
                      </p>
                      {entry.disqualification_reason ? (
                        <p className="text-xs text-danger">{entry.disqualification_reason}</p>
                      ) : null}
                      <div className="flex flex-wrap gap-2 pt-1">
                        {data.is_voting_enabled && data.accepts_votes ? (
                          user ? (
                            <Button
                              size="sm"
                              variant={entry.has_voted ? "lime" : "secondary"}
                              disabled={entry.has_voted || entry.is_owner || vote.isPending}
                              onClick={() => vote.mutate(entry.id)}
                            >
                              <ThumbsUp className="h-4 w-4" /> {entry.has_voted ? "Voted" : "Vote"}
                            </Button>
                          ) : (
                            <Link to="/login">
                              <Button size="sm" variant="secondary">
                                Sign in to vote
                              </Button>
                            </Link>
                          )
                        ) : null}
                        {isStaff && entry.status !== "disqualified" ? (
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() =>
                              disqualify.mutate({ entryId: entry.id, reason: "Entry does not meet the battle rules" })
                            }
                          >
                            Disqualify
                          </Button>
                        ) : null}
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <EmptyState
                title="No entries yet"
                description={
                  data.accepts_entries
                    ? "Entries are open — be the first to submit."
                    : "Entries are closed for this battle."
                }
              />
            )}
          </section>

          {user && data.accepts_entries ? (
            <Card className="space-y-4">
              <h2 className="font-display text-lg font-semibold">Submit your entry</h2>
              <UploadPanel purpose="entry" onReady={(asset) => setEntryForm((previous) => ({ ...previous, asset }))} />
              <div>
                <FieldLabel htmlFor="entry-title">Entry title</FieldLabel>
                <Input
                  id="entry-title"
                  value={entryForm.title}
                  onChange={(event) => setEntryForm((previous) => ({ ...previous, title: event.target.value }))}
                  placeholder="My 30-second routine"
                />
              </div>
              <div className="flex items-center justify-between">
                <p className="text-xs text-haze">
                  {entryForm.asset ? "Video ready to submit." : "Upload a video first."}
                </p>
                <Button
                  size="sm"
                  loading={submitEntry.isPending}
                  disabled={!entryForm.asset || entryForm.title.trim().length < 2}
                  onClick={() => submitEntry.mutate()}
                >
                  Submit entry
                </Button>
              </div>
            </Card>
          ) : null}
        </div>

        <aside className="space-y-6">
          <Card>
            <h2 className="mb-4 flex items-center gap-2 font-display text-lg font-semibold">
              <Trophy className="h-4 w-4 text-lime" /> Standings
            </h2>
            <p className="mb-4 text-xs text-haze">{standings.data?.note ?? "Waiting for the first entries."}</p>
            {standings.data?.rows.length ? (
              <ol className="space-y-2">
                {standings.data.rows.map((row) => (
                  <li key={row.entry_id} className="rounded-2xl border border-ink-800/70 px-3 py-2">
                    <div className="flex items-center justify-between gap-2 text-sm">
                      <span className="truncate">
                        #{row.rank} {row.title}
                      </span>
                      <span className="text-xs text-haze">{compactNumber(row.vote_count)} votes</span>
                    </div>
                    {row.username ? <p className="text-[11px] text-haze">@{row.username}</p> : null}
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-xs text-haze">No ranked entries yet.</p>
            )}
            {standings.data?.is_final ? <Badge tone="lime" className="mt-4">Official result</Badge> : <Badge className="mt-4">Provisional</Badge>}
          </Card>

          <Card>
            <h2 className="mb-4 font-display text-lg font-semibold">Participants</h2>
            {participants.data?.items.length ? (
              <ul className="space-y-2 text-sm">
                {participants.data.items.map((participant) => (
                  <li key={participant.id} className="flex items-center justify-between">
                    <Link to={`/u/${participant.user?.username}`} className="hover:text-violet-soft">
                      @{participant.user?.username}
                    </Link>
                    <span className="text-[11px] uppercase tracking-wide text-haze">{participant.role}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-haze">No participants yet.</p>
            )}
          </Card>

          {data.rules || data.entry_requirements ? (
            <Card className="space-y-3 text-sm text-haze">
              <h2 className="font-display text-lg font-semibold text-white">Rules</h2>
              {data.rules ? <p className="whitespace-pre-line">{data.rules}</p> : null}
              {data.entry_requirements ? (
                <p>
                  <span className="text-white">Entry requirements: </span>
                  {data.entry_requirements}
                </p>
              ) : null}
            </Card>
          ) : null}

          {data.is_owner ? (
            <Card className="space-y-4">
              <h2 className="font-display text-lg font-semibold">Organiser tools</h2>
              <div className="flex flex-wrap gap-2">
                {data.status === "open" ? (
                  <Button size="sm" variant="secondary" onClick={() => changeState.mutate("active")}>
                    Mark in progress
                  </Button>
                ) : null}
                {data.status === "open" || data.status === "active" ? (
                  <Button size="sm" variant="secondary" onClick={() => changeState.mutate("voting")}>
                    Open voting
                  </Button>
                ) : null}
                {data.status === "draft" ? (
                  <Button size="sm" variant="secondary" onClick={() => changeState.mutate("open")}>
                    Publish
                  </Button>
                ) : null}
                {data.status !== "completed" && data.status !== "cancelled" ? (
                  <Button size="sm" variant="ghost" onClick={() => changeState.mutate("cancelled")}>
                    Cancel battle
                  </Button>
                ) : null}
              </div>

              <div>
                <FieldLabel htmlFor="invite">Invite a creator</FieldLabel>
                <div className="flex gap-2">
                  <Input
                    id="invite"
                    value={inviteUsername}
                    onChange={(event) => setInviteUsername(event.target.value)}
                    placeholder="username"
                  />
                  <Button
                    size="sm"
                    disabled={inviteUsername.trim().length < 3}
                    loading={invite.isPending}
                    onClick={() => invite.mutate()}
                  >
                    Invite
                  </Button>
                </div>
              </div>
            </Card>
          ) : null}

          {isStaff && data.status !== "completed" ? (
            <Card className="space-y-3">
              <h2 className="font-display text-lg font-semibold">Moderation</h2>
              <p className="text-xs text-haze">
                Publishing results recalculates standings from the votes table and freezes the battle.
              </p>
              <Button size="sm" variant="lime" loading={finalize.isPending} onClick={() => finalize.mutate()}>
                Publish official results
              </Button>
            </Card>
          ) : null}
        </aside>
      </div>
    </div>
  );
}