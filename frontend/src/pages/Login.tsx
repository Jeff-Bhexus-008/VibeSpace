import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import AuthLayout from "@/components/AuthLayout";
import Button from "@/components/ui/Button";
import { ErrorNote } from "@/components/ui/Feedback";
import { FieldLabel, Input } from "@/components/ui/Input";
import { useAuth } from "@/context/AuthContext";
import { errorMessage } from "@/lib/utils";

export default function Login() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const returnTo = (location.state as { from?: string } | null)?.from ?? "/feed";

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await signIn(email.trim(), password);
      navigate(returnTo, { replace: true });
    } catch (loginError) {
      setError(errorMessage(loginError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout title="Welcome back" subtitle="Sign in to publish, battle and message.">
      <form className="space-y-4" onSubmit={submit}>
        <div>
          <FieldLabel htmlFor="email">Email</FieldLabel>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>
        <div>
          <FieldLabel htmlFor="password">Password</FieldLabel>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>
        {error ? <ErrorNote message={error} /> : null}
        <Button type="submit" className="w-full" loading={busy}>
          Sign in
        </Button>
      </form>

      <div className="mt-6 space-y-2 text-sm text-haze">
        <p>
          <Link to="/forgot-password" className="text-violet-soft hover:underline">
            Forgot your password?
          </Link>
        </p>
        <p>
          New to VibeSpace?{" "}
          <Link to="/register" className="text-violet-soft hover:underline">
            Create an account
          </Link>
        </p>
      </div>
    </AuthLayout>
  );
}