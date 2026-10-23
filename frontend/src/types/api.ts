/** Shapes returned by the VibeSpace API (kept in one place so pages stay readable). */

export interface Page<T> {
  items: T[];
  next_cursor?: string | null;
  has_more: boolean;
  total?: number | null;
}

export type Role = "user" | "creator" | "moderator" | "admin";

export interface SessionUser {
  id: string;
  username: string;
  email: string;
  role: Role;
  is_email_verified: boolean;
  display_name?: string | null;
  avatar_url?: string | null;
  cover_url?: string | null;
  bio?: string | null;
  follower_count: number;
  following_count: number;
  video_count: number;
  created_at?: string | null;
}

export interface PublicUser {
  id: string;
  username: string;
  display_name?: string | null;
  bio?: string | null;
  avatar_url?: string | null;
  cover_url?: string | null;
  location?: string | null;
  links: string[];
  role: Role;
  follower_count: number;
  following_count: number;
  video_count: number;
  total_likes: number;
  is_private: boolean;
  is_following?: boolean | null;
  is_followed_by?: boolean | null;
  is_blocked?: boolean | null;
  is_self?: boolean | null;
  created_at?: string | null;
}

export interface Video {
  id: string;
  title: string;
  description?: string | null;
  category?: string | null;
  tags: string[];
  visibility: "public" | "unlisted" | "private";
  status: "draft" | "processing" | "ready" | "removed";
  is_learn_content: boolean;
  learn_category?: string | null;
  allow_comments: boolean;
  view_count: number;
  like_count: number;
  comment_count: number;
  save_count: number;
  share_count: number;
  duration_seconds?: number | null;
  thumbnail_url?: string | null;
  playback_url?: string | null;
  published_at?: string | null;
  created_at?: string | null;
  author?: { id: string; username: string; display_name?: string | null; avatar_url?: string | null; follower_count: number } | null;
  is_liked?: boolean | null;
  is_saved?: boolean | null;
  is_owner?: boolean | null;
}

export interface Comment {
  id: string;
  video_id: string;
  parent_id?: string | null;
  body: string;
  like_count: number;
  reply_count: number;
  is_removed: boolean;
  created_at?: string | null;
  author?: { id: string; username: string; display_name?: string | null; avatar_url?: string | null } | null;
  is_owner?: boolean | null;
}

export type ChallengeStatus = "draft" | "scheduled" | "open" | "active" | "voting" | "completed" | "cancelled";
export type ChallengeFormat = "head_to_head" | "open_challenge" | "community_challenge" | "skill_challenge";

export interface Challenge {
  id: string;
  title: string;
  description?: string | null;
  category: string;
  format: ChallengeFormat;
  status: ChallengeStatus;
  rules?: string | null;
  entry_requirements?: string | null;
  is_public: boolean;
  is_voting_enabled: boolean;
  votes_per_voter: number;
  entries_per_user: number;
  max_entries?: number | null;
  starts_at?: string | null;
  deadline_at?: string | null;
  voting_ends_at?: string | null;
  completed_at?: string | null;
  entry_count: number;
  vote_count: number;
  participant_count: number;
  reference_media_url?: string | null;
  creator?: { id: string; username: string; display_name?: string | null; avatar_url?: string | null } | null;
  opponent?: { id: string; username: string; display_name?: string | null; avatar_url?: string | null } | null;
  winner_entry_id?: string | null;
  is_owner?: boolean | null;
  has_joined?: boolean | null;
  has_voted?: boolean | null;
  accepts_entries?: boolean | null;
  accepts_votes?: boolean | null;
  seconds_remaining?: number | null;
  created_at?: string | null;
}

export interface ChallengeEntry {
  id: string;
  challenge_id: string;
  title: string;
  description?: string | null;
  status: "submitted" | "approved" | "disqualified" | "withdrawn";
  vote_count: number;
  like_count: number;
  comment_count: number;
  score: number;
  submitted_at?: string | null;
  thumbnail_url?: string | null;
  playback_url?: string | null;
  disqualification_reason?: string | null;
  user?: { id: string; username: string; display_name?: string | null; avatar_url?: string | null } | null;
  is_owner?: boolean | null;
  has_voted?: boolean | null;
}

export interface StandingRow {
  entry_id: string;
  title: string;
  rank: number;
  vote_count: number;
  final_score: number;
  is_final: boolean;
  username?: string | null;
  thumbnail_url?: string | null;
}

export interface UploadTicket {
  asset_id: string;
  storage_key: string;
  upload_url: string;
  method: string;
  headers: Record<string, string>;
  expires_in: number;
  max_bytes: number;
}

export interface MediaAsset {
  id: string;
  kind: "video" | "image" | "audio";
  status: "pending" | "uploading" | "uploaded" | "processing" | "ready" | "failed";
  storage_key: string;
  size_bytes?: number | null;
  duration_seconds?: number | null;
  width?: number | null;
  height?: number | null;
  detected_content_type?: string | null;
  thumbnail_url?: string | null;
  playback_url?: string | null;
  renditions: Array<{ label: string; key: string; height: number }>;
  processing_error?: string | null;
  created_at?: string | null;
}

export interface Notification {
  id: string;
  type: string;
  entity_type?: string | null;
  entity_id?: string | null;
  payload: Record<string, unknown>;
  is_read: boolean;
  read_at?: string | null;
  created_at?: string | null;
  actor?: PublicUser | null;
}

export interface Conversation {
  id: string;
  is_group: boolean;
  title?: string | null;
  last_message_at?: string | null;
  unread_count: number;
  participants: PublicUser[];
  last_message_preview?: string | null;
}

export interface Message {
  id: string;
  conversation_id: string;
  sender_id?: string | null;
  body?: string | null;
  attachment_url?: string | null;
  attachment_kind?: string | null;
  shared_video_id?: string | null;
  edited_at?: string | null;
  created_at?: string | null;
  sender?: PublicUser | null;
}

export interface CreatorSummary {
  video_count: number;
  published_count: number;
  draft_count: number;
  processing_count: number;
  total_views: number;
  unique_views: number;
  total_likes: number;
  total_comments: number;
  total_saves: number;
  total_shares: number;
  follower_count: number;
  engagement_rate: number;
  has_data: boolean;
}

export interface AnalyticsSeries {
  range_days: number;
  points: Array<{ day: string; views: number; likes: number; comments: number; follows: number; uploads: number }>;
  totals: Record<string, number>;
  has_data: boolean;
}

export interface Report {
  id: string;
  target_type: string;
  target_id: string;
  reason: string;
  details?: string | null;
  status: "open" | "reviewing" | "resolved" | "dismissed";
  resolution_note?: string | null;
  created_at?: string | null;
  reporter?: PublicUser | null;
  target_preview?: Record<string, unknown> | null;
}