import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import AuthLayout from "@/components/AuthLayout";
import Button from "@/components/ui/Button";
import { ErrorNote } from "@/components/ui/Feedback";
import { FieldLabel, Input } from "@/components/ui/Input";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/utils";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("The two passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      await api.post("/auth/password/reset-confirm", { token, new_password: password });
      setDone(true);
      setTimeout(() => navigate("/login", { replace: true }), 1500);
    } catch (resetError) {
      setError(errorMessage(resetError));
    } finally {
      setBusy(false);
    }
  }

  if (!token) {
    return (
      <AuthLayout title="Reset link missing" subtitle="Open the link from your email to continue.">
        <div className="space-y-4 text-sm text-haze">
          <p>
            This page needs the one-time token from your reset email. Request a fresh link if yours has
            expired.
          </p>
          <Link to="/forgot-password">
            <Button className="w-full">Request a new link</Button>
          </Link>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Choose a new password" subtitle="Signing in with it will end your other sessions.">
      {done ? (
        <p className="text-sm text-lime">Password updated. Taking you to sign in…</p>
      ) : (
        <form className="space-y-4" onSubmit={submit}>
          <div>
            <FieldLabel htmlFor="password">New password</FieldLabel>
            <Input
              id="password"
              type="password"
              required
              minLength={10}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>
          <div>
            <FieldLabel htmlFor="confirm">Confirm new password</FieldLabel>
            <Input
              id="confirm"
              type="password"
              required
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
            />
          </div>
          {error ? <ErrorNote message={error} /> : null}
          <Button type="submit" className="w-full" loading={busy}>
            Update password
          </Button>
        </form>
      )}
    </AuthLayout>
  );
}