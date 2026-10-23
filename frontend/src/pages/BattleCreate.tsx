import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { Swords } from "lucide-react";

import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import { ErrorNote } from "@/components/ui/Feedback";
import { FieldLabel, Input, Textarea } from "@/components/ui/Input";
import { api } from "@/lib/api";
import { errorMessage, titleCase } from "@/lib/utils";
import type { Challenge, ChallengeFormat } from "@/types/api";

const CATEGORIES = [
  "dance",
  "comedy",
  "music",
  "sports",
  "gaming",
  "coding",
  "education",
  "art",
  "fitness",
  "creativity",
];

const FORMATS: Array<{ value: ChallengeFormat; label: string; blurb: string }> = [
  { value: "open_challenge", label: "Open challenge", blurb: "Anyone eligible can submit an entry." },
  { value: "head_to_head", label: "Head to head", blurb: "You and one invited creator compete directly." },
  { value: "community_challenge", label: "Community challenge", blurb: "A community-wide call to participate." },
  { value: "skill_challenge", label: "Skill challenge", blurb: "Demonstrate a specific skill, scored by votes." },
];

export default function BattleCreate() {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    title: "",
    description: "",
    category: "dance",
    format: "open_challenge" as ChallengeFormat,
    opponent_username: "",
    rules: "",
    entry_requirements: "",
    starts_at: "",
    deadline_at: "",
    voting_ends_at: "",
    is_public: true,
    is_voting_enabled: true,
    votes_per_voter: 1,
    entries_per_user: 1,
    max_entries: "",
    publish: true,
  });

  function update<K extends keyof typeof form>(field: K, value: (typeof form)[K]) {
    setForm((previous) => ({ ...previous, [field]: value }));
  }

  const create = useMutation({
    mutationFn: () =>
      api.post<Challenge>("/challenges", {
        title: form.title.trim(),
        description: form.description.trim() || undefined,
        category: form.category,
        format: form.format,
        opponent_username: form.format === "head_to_head" ? form.opponent_username.trim() : undefined,
        rules: form.rules.trim() || undefined,
        entry_requirements: form.entry_requirements.trim() || undefined,
        starts_at: form.starts_at ? new Date(form.starts_at).toISOString() : undefined,
        deadline_at: form.deadline_at ? new Date(form.deadline_at).toISOString() : undefined,
        voting_ends_at: form.voting_ends_at ? new Date(form.voting_ends_at).toISOString() : undefined,
        is_public: form.is_public,
        is_voting_enabled: form.is_voting_enabled,
        votes_per_voter: Number(form.votes_per_voter),
        entries_per_user: Number(form.entries_per_user),
        max_entries: form.max_entries ? Number(form.max_entries) : undefined,
        publish: form.publish,
      }),
    onSuccess: (challenge) => navigate(`/battles/${challenge.id}`),
    onError: (mutationError) => setError(errorMessage(mutationError)),
  });

  return (
    <div className="space-y-8 animate-fade-up">
      <header className="flex items-center gap-3">
        <span className="grid h-11 w-11 place-items-center rounded-2xl bg-coral/15 text-coral">
          <Swords className="h-5 w-5" />
        </span>
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">Start a Vibe Battle</h1>
          <p className="text-sm text-haze">Set the rules once — the backend enforces deadlines, limits and voting.</p>
        </div>
      </header>

      <form
        className="space-y-6"
        onSubmit={(event) => {
          event.preventDefault();
          setError(null);
          create.mutate();
        }}
      >
        <Card className="space-y-4">
          <div>
            <FieldLabel htmlFor="title">Battle title</FieldLabel>
            <Input
              id="title"
              required
              minLength={3}
              maxLength={160}
              value={form.title}
              onChange={(event) => update("title", event.target.value)}
              placeholder="Friday night dance-off"
            />
          </div>
          <div>
            <FieldLabel htmlFor="description">Description</FieldLabel>
            <Textarea
              id="description"
              value={form.description}
              onChange={(event) => update("description", event.target.value)}
              placeholder="What are you challenging people to do?"
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <FieldLabel htmlFor="category">Category</FieldLabel>
              <select
                id="category"
                value={form.category}
                onChange={(event) => update("category", event.target.value)}
                className="w-full rounded-2xl border border-ink-700/70 bg-ink-900/80 px-4 py-3 text-sm"
              >
                {CATEGORIES.map((category) => (
                  <option key={category} value={category}>
                    {titleCase(category)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <FieldLabel htmlFor="format">Format</FieldLabel>
              <select
                id="format"
                value={form.format}
                onChange={(event) => update("format", event.target.value as ChallengeFormat)}
                className="w-full rounded-2xl border border-ink-700/70 bg-ink-900/80 px-4 py-3 text-sm"
              >
                {FORMATS.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <p className="text-xs text-haze">{FORMATS.find((item) => item.value === form.format)?.blurb}</p>

          {form.format === "head_to_head" ? (
            <div>
              <FieldLabel htmlFor="opponent">Opponent username</FieldLabel>
              <Input
                id="opponent"
                required
                value={form.opponent_username}
                onChange={(event) => update("opponent_username", event.target.value)}
                placeholder="theirhandle"
              />
            </div>
          ) : null}
        </Card>

        <Card className="space-y-4">
          <p className="font-display text-sm font-semibold">Rules and eligibility</p>
          <div>
            <FieldLabel htmlFor="rules">Rules</FieldLabel>
            <Textarea
              id="rules"
              value={form.rules}
              onChange={(event) => update("rules", event.target.value)}
              placeholder="Original performances only, one entry per creator, no reposts…"
            />
          </div>
          <div>
            <FieldLabel htmlFor="requirements">Entry requirements</FieldLabel>
            <Textarea
              id="requirements"
              rows={2}
              value={form.entry_requirements}
              onChange={(event) => update("entry_requirements", event.target.value)}
              placeholder="e.g. show your face at the start, keep it under 60 seconds"
            />
          </div>
        </Card>

        <Card className="space-y-4">
          <p className="font-display text-sm font-semibold">Schedule</p>
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <FieldLabel htmlFor="starts_at">Starts</FieldLabel>
              <Input
                id="starts_at"
                type="datetime-local"
                value={form.starts_at}
                onChange={(event) => update("starts_at", event.target.value)}
              />
            </div>
            <div>
              <FieldLabel htmlFor="deadline_at">Entry deadline</FieldLabel>
              <Input
                id="deadline_at"
                type="datetime-local"
                value={form.deadline_at}
                onChange={(event) => update("deadline_at", event.target.value)}
              />
            </div>
            <div>
              <FieldLabel htmlFor="voting_ends_at">Voting closes</FieldLabel>
              <Input
                id="voting_ends_at"
                type="datetime-local"
                value={form.voting_ends_at}
                onChange={(event) => update("voting_ends_at", event.target.value)}
              />
            </div>
          </div>
          <p className="text-xs text-haze">
            Entries submitted after the deadline are refused by the API, whatever the client sends.
          </p>
        </Card>

        <Card className="space-y-4">
          <p className="font-display text-sm font-semibold">Participation and voting</p>
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <FieldLabel htmlFor="entries_per_user">Entries per creator</FieldLabel>
              <Input
                id="entries_per_user"
                type="number"
                min={1}
                max={10}
                value={form.entries_per_user}
                onChange={(event) => update("entries_per_user", Number(event.target.value))}
              />
            </div>
            <div>
              <FieldLabel htmlFor="max_entries">Entry cap (optional)</FieldLabel>
              <Input
                id="max_entries"
                type="number"
                min={2}
                value={form.max_entries}
                onChange={(event) => update("max_entries", event.target.value)}
                placeholder="unlimited"
              />
            </div>
            <div>
              <FieldLabel htmlFor="votes_per_voter">Votes per voter</FieldLabel>
              <Input
                id="votes_per_voter"
                type="number"
                min={1}
                max={5}
                value={form.votes_per_voter}
                onChange={(event) => update("votes_per_voter", Number(event.target.value))}
              />
            </div>
          </div>

          <div className="space-y-3 text-sm text-haze">
            <Toggle
              label="Public battle"
              hint="Private battles are only visible to the organiser and participants."
              checked={form.is_public}
              onChange={(value) => update("is_public", value)}
            />
            <Toggle
              label="Community voting"
              hint="Votes are counted from the votes table; duplicate votes are blocked by the database."
              checked={form.is_voting_enabled}
              onChange={(value) => update("is_voting_enabled", value)}
            />
            <Toggle
              label="Publish immediately"
              hint="Turn this off to save the battle as a draft and publish later."
              checked={form.publish}
              onChange={(value) => update("publish", value)}
            />
          </div>
        </Card>

        {error ? <ErrorNote message={error} /> : null}

        <div className="flex justify-end gap-3">
          <Button type="submit" size="lg" loading={create.isPending}>
            {form.publish ? "Publish battle" : "Save draft"}
          </Button>
        </div>
      </form>
    </div>
  );
}

function Toggle({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-3">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="mt-1 h-4 w-4 rounded border-ink-700 bg-ink-900 text-violet"
      />
      <span>
        <span className="block text-sm text-white">{label}</span>
        {hint ? <span className="block text-xs text-haze">{hint}</span> : null}
      </span>
    </label>
  );
}