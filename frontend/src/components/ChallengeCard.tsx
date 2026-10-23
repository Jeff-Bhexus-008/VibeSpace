import { Link } from "react-router-dom";
import { Clock, Swords, Users } from "lucide-react";

import Avatar from "@/components/ui/Avatar";
import Badge from "@/components/ui/Badge";
import { compactNumber, countdown, titleCase } from "@/lib/utils";
import type { Challenge, ChallengeStatus } from "@/types/api";

const STATUS_TONE: Record<ChallengeStatus, "neutral" | "violet" | "lime" | "coral" | "sky" | "danger"> = {
  draft: "neutral",
  scheduled: "sky",
  open: "lime",
  active: "violet",
  voting: "coral",
  completed: "neutral",
  cancelled: "danger",
};

const FORMAT_LABEL: Record<string, string> = {
  head_to_head: "Head to head",
  open_challenge: "Open challenge",
  community_challenge: "Community challenge",
  skill_challenge: "Skill challenge",
};

export default function ChallengeCard({ challenge }: { challenge: Challenge }) {
  return (
    <Link
      to={`/battles/${challenge.id}`}
      className="group flex flex-col gap-4 rounded-3xl border border-ink-800/80 bg-ink-900/60 p-5 transition hover:border-coral/40"
    >
      <div className="flex items-start justify-between gap-3">
        <Badge tone={STATUS_TONE[challenge.status]}>{titleCase(challenge.status)}</Badge>
        <span className="text-[11px] text-haze">{FORMAT_LABEL[challenge.format] ?? challenge.format}</span>
      </div>

      <div>
        <h3 className="font-display text-base font-semibold leading-snug group-hover:text-white">
          {challenge.title}
        </h3>
        <p className="mt-1 line-clamp-2 text-xs text-haze">{challenge.description ?? "No description provided."}</p>
      </div>

      <div className="flex items-center gap-2 text-xs text-haze">
        <Avatar src={challenge.creator?.avatar_url} name={challenge.creator?.display_name ?? challenge.creator?.username} size="sm" />
        <span>@{challenge.creator?.username}</span>
        {challenge.opponent ? <span className="text-haze">vs @{challenge.opponent.username}</span> : null}
      </div>

      <div className="mt-auto flex flex-wrap items-center gap-4 text-[11px] text-haze">
        <span className="inline-flex items-center gap-1.5">
          <Swords className="h-3.5 w-3.5" /> {compactNumber(challenge.entry_count)} entries
        </span>
        <span className="inline-flex items-center gap-1.5">
          <Users className="h-3.5 w-3.5" /> {compactNumber(challenge.vote_count)} votes
        </span>
        <span className="inline-flex items-center gap-1.5">
          <Clock className="h-3.5 w-3.5" />
          {challenge.status === "completed" ? "Finished" : countdown(challenge.deadline_at, challenge.seconds_remaining)}
        </span>
      </div>
    </Link>
  );
}