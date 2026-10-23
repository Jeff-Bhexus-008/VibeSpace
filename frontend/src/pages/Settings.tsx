import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Image as ImageIcon, KeyRound, LogOut, Mail } from "lucide-react";

import Avatar from "@/components/ui/Avatar";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import { ErrorNote, Spinner } from "@/components/ui/Feedback";
import { FieldLabel, Input, Textarea } from "@/components/ui/Input";
import { useAuth } from "@/context/AuthContext";
import { useUpload } from "@/hooks/useUpload";
import { api, ApiError } from "@/lib/api";
import { errorMessage } from "@/lib/utils";

interface ProfileSettings {
  display_name: string | null;
  bio: string | null;
  location: string | null;
  links: string[];
  is_private: boolean;
  allow_messages_from: "everyone" | "followers" | "nobody";
  topic_preferences: string[];
}

interface ProfileDraft {
  display_name: string;
  bio: string;
  location: string;
  links: string;
  is_private: boolean;
  allow_messages_from: ProfileSettings["allow_messages_from"];
  topic_preferences: string;
}

export default function Settings() {
  const { user, refresh, signOut } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const avatarInput = useRef<HTMLInputElement | null>(null);
  const coverInput = useRef<HTMLInputElement | null>(null);
  const avatarUpload = useUpload({ kind: "image", purpose: "avatar" });
  const coverUpload = useUpload({ kind: "image", purpose: "cover" });
  const profileSettings = useQuery({
    queryKey: ["profile-settings", user?.id],
    queryFn: () => api.get<ProfileSettings>("/users/me/profile"),
    enabled: Boolean(user),
  });

  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [profileDraft, setProfileDraft] = useState<ProfileDraft | null>(null);
  const profile: ProfileDraft = profileDraft ?? {
    display_name: profileSettings.data?.display_name ?? user?.display_name ?? "",
    bio: profileSettings.data?.bio ?? user?.bio ?? "",
    location: profileSettings.data?.location ?? "",
    links: profileSettings.data?.links.join(" ") ?? "",
    is_private: profileSettings.data?.is_private ?? false,
    allow_messages_from: profileSettings.data?.allow_messages_from ?? "everyone",
    topic_preferences: profileSettings.data?.topic_preferences.join(", ") ?? "",
  };

  function updateProfile(patch: Partial<ProfileDraft>) {
    setProfileDraft((current) => ({ ...profile, ...current, ...patch }));
  }

  const [passwords, setPasswords] = useState({ current: "", next: "" });
  const [deletePassword, setDeletePassword] = useState("");

  const saveProfile = useMutation({
    mutationFn: () =>
      api.patch("/users/me/profile", {
        display_name: profile.display_name.trim() || undefined,
        bio: profile.bio.trim() || undefined,
        location: profile.location.trim() || undefined,
        links: profile.links
          .split(/[\s,]+/)
          .map((link) => link.trim())
          .filter(Boolean),
        is_private: profile.is_private,
        allow_messages_from: profile.allow_messages_from,
        topic_preferences: profile.topic_preferences
          .split(",")
          .map((topic) => topic.trim())
          .filter(Boolean),
      }),
    onSuccess: async () => {
      setError(null);
      setStatus("Profile saved.");
      await refresh();
      void queryClient.invalidateQueries();
    },
    onError: (mutationError) => setError(errorMessage(mutationError)),
  });

  const changePassword = useMutation({
    mutationFn: () =>
      api.post<{ message: string }>("/auth/password/change", {
        current_password: passwords.current,
        new_password: passwords.next,
      }),
    onSuccess: (result: { message?: string }) => {
      setError(null);
      setStatus(result.message ?? "Password updated.");
      setPasswords({ current: "", next: "" });
    },
    onError: (mutationError) => setError(errorMessage(mutationError)),
  });

  const resendVerification = useMutation({
    mutationFn: () => api.post<{ message: string; dev_verify_link?: string | null }>("/auth/email/verify-request"),
    onSuccess: (result) => {
      setError(null);
      setStatus(
        result.dev_verify_link
          ? `Mail is not configured on this server. Development link: ${result.dev_verify_link}`
          : result.message,
      );
    },
    onError: (mutationError) => setError(errorMessage(mutationError)),
  });

  const signOutEverywhere = useMutation({
    mutationFn: () => api.post<{ message: string }>("/auth/logout-all"),
    onSuccess: async () => {
      await refresh();
      navigate("/login", { replace: true });
    },
    onError: (mutationError) => setError(errorMessage(mutationError)),
  });

  const deleteAccount = useMutation({
    mutationFn: () => api.post("/users/me/delete-account", { password: deletePassword, confirm: true }),
    onSuccess: async () => {
      await signOut();
      navigate("/", { replace: true });
    },
    onError: (mutationError) => setError(errorMessage(mutationError)),
  });

  async function uploadImage(kind: "avatar" | "cover", file: File | undefined) {
    if (!file) return;
    const hook = kind === "avatar" ? avatarUpload : coverUpload;
    setError(null);
    const asset = await hook.start(file);
    if (!asset) {
      setError(hook.error ?? "The image could not be uploaded.");
      return;
    }
    try {
      await api.post(`/users/me/images/${kind}`, { storage_key: asset.storage_key });
      setStatus(kind === "avatar" ? "Profile picture updated." : "Cover image updated.");
      await refresh();
      void queryClient.invalidateQueries();
    } catch (imageError) {
      setError(errorMessage(imageError));
    }
  }

  if (!user) {
    return (
      <div className="flex justify-center py-24">
        <Spinner className="h-8 w-8" />
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-fade-up">
      <header>
        <h1 className="font-display text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-haze">Your profile, security and privacy controls.</p>
      </header>

      {error ? <ErrorNote message={error} /> : null}
      {profileSettings.isError ? <ErrorNote message={errorMessage(profileSettings.error)} /> : null}
      {status ? (
        <p className="rounded-2xl border border-lime/40 bg-lime/10 px-4 py-3 text-sm text-lime">{status}</p>
      ) : null}

      <Card className="space-y-5">
        <h2 className="font-display text-lg font-semibold">Images</h2>
        <div className="flex flex-wrap items-center gap-5">
          <div className="flex items-center gap-3">
            <Avatar src={user.avatar_url} name={user.display_name ?? user.username} size="lg" />
            <div>
              <p className="text-sm">Profile picture</p>
              <p className="text-xs text-haze">Stored in your media bucket, served via signed URLs.</p>
              <input
                ref={avatarInput}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                className="hidden"
                onChange={(event) => void uploadImage("avatar", event.target.files?.[0])}
              />
              <Button
                size="sm"
                variant="secondary"
                className="mt-2"
                loading={avatarUpload.phase === "uploading" || avatarUpload.phase === "requesting"}
                onClick={() => avatarInput.current?.click()}
              >
                <ImageIcon className="h-4 w-4" /> Upload picture
              </Button>
            </div>
          </div>

          <div>
            <p className="text-sm">Cover image</p>
            <p className="text-xs text-haze">Shown at the top of your profile.</p>
            <input
              ref={coverInput}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              className="hidden"
              onChange={(event) => void uploadImage("cover", event.target.files?.[0])}
            />
            <Button
              size="sm"
              variant="secondary"
              className="mt-2"
              loading={coverUpload.phase === "uploading" || coverUpload.phase === "requesting"}
              onClick={() => coverInput.current?.click()}
            >
              <ImageIcon className="h-4 w-4" /> Upload cover
            </Button>
          </div>
        </div>
      </Card>

      <Card className="space-y-4">
        <h2 className="font-display text-lg font-semibold">Profile</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <FieldLabel htmlFor="display_name">Display name</FieldLabel>
            <Input
              id="display_name"
              disabled={!profileSettings.data}
              value={profile.display_name}
              onChange={(event) => updateProfile({ display_name: event.target.value })}
            />
          </div>
          <div>
            <FieldLabel htmlFor="location">Location</FieldLabel>
            <Input
              id="location"
              disabled={!profileSettings.data}
              value={profile.location}
              onChange={(event) => updateProfile({ location: event.target.value })}
              placeholder="Casablanca, MA"
            />
          </div>
        </div>
        <div>
          <FieldLabel htmlFor="bio">Bio</FieldLabel>
          <Textarea
            id="bio"
              disabled={!profileSettings.data}
            value={profile.bio}
              onChange={(event) => updateProfile({ bio: event.target.value })}
            maxLength={500}
          />
        </div>
        <div>
          <FieldLabel htmlFor="links">Links</FieldLabel>
          <Input
            id="links"
            disabled={!profileSettings.data}
            value={profile.links}
            onChange={(event) => updateProfile({ links: event.target.value })}
            placeholder="https://yoursite.com https://github.com/you"
          />
          <p className="mt-1.5 text-xs text-haze">Up to five links, each starting with https://</p>
        </div>
        <div>
          <FieldLabel htmlFor="topics">Topic interests</FieldLabel>
          <Input
            id="topics"
            disabled={!profileSettings.data}
            value={profile.topic_preferences}
            onChange={(event) => updateProfile({ topic_preferences: event.target.value })}
            placeholder="dance, coding, fitness"
          />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="flex items-start gap-3 text-sm text-haze">
            <input
              type="checkbox"
              disabled={!profileSettings.data}
              checked={profile.is_private}
              onChange={(event) => updateProfile({ is_private: event.target.checked })}
              className="mt-1 h-4 w-4 rounded border-ink-700 bg-ink-900 text-violet"
            />
            <span>
              <span className="block text-white">Private profile</span>
              <span className="block text-xs">Hides your profile from public listings.</span>
            </span>
          </label>
          <div>
            <FieldLabel htmlFor="messages">Who can message you</FieldLabel>
            <select
              id="messages"
              disabled={!profileSettings.data}
              value={profile.allow_messages_from}
              onChange={(event) =>
                updateProfile({ allow_messages_from: event.target.value as ProfileDraft["allow_messages_from"] })
              }
              className="w-full rounded-2xl border border-ink-700/70 bg-ink-900/80 px-4 py-3 text-sm"
            >
              <option value="everyone">Everyone</option>
              <option value="followers">People I follow back… followers only</option>
              <option value="nobody">Nobody</option>
            </select>
          </div>
        </div>
        <div className="flex justify-end">
          <Button disabled={!profileSettings.data} loading={saveProfile.isPending} onClick={() => saveProfile.mutate()}>
            Save profile
          </Button>
        </div>
      </Card>

      <Card className="space-y-4">
        <h2 className="flex items-center gap-2 font-display text-lg font-semibold">
          <KeyRound className="h-4 w-4 text-violet" /> Security
        </h2>
        {!user.is_email_verified ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-coral/40 bg-coral/10 px-4 py-3">
            <p className="text-sm text-coral">Your email is not confirmed yet.</p>
            <Button
              size="sm"
              variant="secondary"
              loading={resendVerification.isPending}
              onClick={() => resendVerification.mutate()}
            >
              <Mail className="h-4 w-4" /> Resend confirmation
            </Button>
          </div>
        ) : null}

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <FieldLabel htmlFor="current">Current password</FieldLabel>
            <Input
              id="current"
              type="password"
              value={passwords.current}
              onChange={(event) => setPasswords((previous) => ({ ...previous, current: event.target.value }))}
            />
          </div>
          <div>
            <FieldLabel htmlFor="next">New password</FieldLabel>
            <Input
              id="next"
              type="password"
              minLength={10}
              value={passwords.next}
              onChange={(event) => setPasswords((previous) => ({ ...previous, next: event.target.value }))}
            />
          </div>
        </div>
        <div className="flex flex-wrap gap-3">
          <Button
            loading={changePassword.isPending}
            disabled={!passwords.current || passwords.next.length < 10}
            onClick={() => changePassword.mutate()}
          >
            Update password
          </Button>
          <Button variant="secondary" loading={signOutEverywhere.isPending} onClick={() => signOutEverywhere.mutate()}>
            <LogOut className="h-4 w-4" /> Sign out everywhere
          </Button>
        </div>
      </Card>

      <Card className="space-y-4 border-danger/30">
        <h2 className="flex items-center gap-2 font-display text-lg font-semibold text-danger">
          <AlertTriangle className="h-4 w-4" /> Delete account
        </h2>
        <p className="text-sm text-haze">
          This removes your account, videos and media from storage. It cannot be undone.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-[14rem] flex-1">
            <FieldLabel htmlFor="delete-password">Confirm with your password</FieldLabel>
            <Input
              id="delete-password"
              type="password"
              value={deletePassword}
              onChange={(event) => setDeletePassword(event.target.value)}
            />
          </div>
          <Button
            variant="danger"
            loading={deleteAccount.isPending}
            disabled={deletePassword.length === 0}
            onClick={() => deleteAccount.mutate()}
          >
            Delete my account
          </Button>
        </div>
        {deleteAccount.error instanceof ApiError ? (
          <p className="text-xs text-danger">{deleteAccount.error.message}</p>
        ) : null}
      </Card>
    </div>
  );
}