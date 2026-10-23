import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import AuthLayout from "@/components/AuthLayout";
import Button from "@/components/ui/Button";
import { ErrorNote } from "@/components/ui/Feedback";
import { FieldLabel, Input } from "@/components/ui/Input";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/utils";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const [devLink, setDevLink] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const result = await api.post<{ message: string; dev_reset_link?: string | null }>(
        "/auth/password/reset-request",
        { email: email.trim() },
      );
      // The API answers the same way whether or not the address exists.
      setSent(result.message);
      setDevLink(result.dev_reset_link ?? null);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout title="Reset your password" subtitle="We will email a single-use link that expires in an hour.">
      {sent ? (
        <div className="space-y-4 text-sm">
          <p className="text-lime">{sent}</p>
          {devLink ? (
            <p className="break-all rounded-2xl border border-ink-800/80 bg-ink-950/60 p-3 text-xs text-haze">
              Development mode — no mail server configured, use this link:{" "}
              <a className="text-violet-soft underline" href={devLink}>
                {devLink}
              </a>
            </p>
          ) : null}
          <Link to="/login">
            <Button className="w-full" variant="secondary">
              Back to sign in
            </Button>
          </Link>
        </div>
      ) : (
        <form className="space-y-4" onSubmit={submit}>
          <div>
            <FieldLabel htmlFor="email">Email</FieldLabel>
            <Input
              id="email"
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </div>
          {error ? <ErrorNote message={error} /> : null}
          <Button type="submit" className="w-full" loading={busy}>
            Send reset link
          </Button>
        </form>
      )}
    </AuthLayout>
  );
}