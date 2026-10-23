import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import AuthLayout from "@/components/AuthLayout";
import Button from "@/components/ui/Button";
import { ErrorNote } from "@/components/ui/Feedback";
import { FieldLabel, Input } from "@/components/ui/Input";
import { useAuth } from "@/context/AuthContext";
import { errorMessage } from "@/lib/utils";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ username: "", email: "", password: "", confirm: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function update(field: keyof typeof form, value: string) {
    setForm((previous) => ({ ...previous, [field]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (form.password !== form.confirm) {
      setError("The two passwords do not match.");
      return;
    }
    if (form.password.length < 10) {
      setError("Use at least 10 characters, mixing letters and numbers.");
      return;
    }

    setBusy(true);
    try {
      const result = await register({
        username: form.username.trim(),
        email: form.email.trim(),
        password: form.password,
      });
      navigate("/verify-email", {
        replace: true,
        state: { sent: result.verification_email_sent, devLink: result.dev_verify_link },
      });
    } catch (registerError) {
      setError(errorMessage(registerError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout title="Join VibeSpace" subtitle="Create an account to publish, compete and learn.">
      <form className="space-y-4" onSubmit={submit}>
        <div>
          <FieldLabel htmlFor="username">Username</FieldLabel>
          <Input
            id="username"
            required
            minLength={3}
            maxLength={32}
            pattern="[A-Za-z0-9_]+"
            value={form.username}
            onChange={(event) => update("username", event.target.value)}
            placeholder="vibemaster"
          />
          <p className="mt-1.5 text-xs text-haze">Letters, numbers and underscores. This is your @handle.</p>
        </div>
        <div>
          <FieldLabel htmlFor="email">Email</FieldLabel>
          <Input
            id="email"
            type="email"
            required
            value={form.email}
            onChange={(event) => update("email", event.target.value)}
          />
        </div>
        <div>
          <FieldLabel htmlFor="password">Password</FieldLabel>
          <Input
            id="password"
            type="password"
            required
            minLength={10}
            value={form.password}
            onChange={(event) => update("password", event.target.value)}
          />
        </div>
        <div>
          <FieldLabel htmlFor="confirm">Confirm password</FieldLabel>
          <Input
            id="confirm"
            type="password"
            required
            value={form.confirm}
            onChange={(event) => update("confirm", event.target.value)}
          />
        </div>
        {error ? <ErrorNote message={error} /> : null}
        <Button type="submit" className="w-full" loading={busy}>
          Create account
        </Button>
      </form>

      <p className="mt-6 text-sm text-haze">
        Already have an account?{" "}
        <Link to="/login" className="text-violet-soft hover:underline">
          Sign in
        </Link>
      </p>
    </AuthLayout>
  );
}