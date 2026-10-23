import { useEffect, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";

import AuthLayout from "@/components/AuthLayout";
import Button from "@/components/ui/Button";
import { ErrorNote } from "@/components/ui/Feedback";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/utils";

/**
 * Two jobs in one screen:
 * - ?token=…  confirms the address (the link from the email)
 * - no token  explains what to do next and can resend the email
 */
export default function VerifyEmail() {
  const [params] = useSearchParams();
  const location = useLocation();
  const { user, refresh } = useAuth();
  const token = params.get("token");
  const state = (location.state as { sent?: boolean; devLink?: string | null } | null) ?? {};

  const [status, setStatus] = useState<"idle" | "confirming" | "done" | "failed">(token ? "confirming" : "idle");
  const [message, setMessage] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(
    state.sent === false ? "Mail delivery is not configured on this server yet." : null,
  );

  useEffect(() => {
    if (!token) return;
    api
      .post<{ message: string }>("/auth/email/verify-confirm", { token })
      .then(async (result) => {
        setStatus("done");
        setMessage(result.message);
        await refresh();
      })
      .catch((error) => {
        setStatus("failed");
        setMessage(errorMessage(error));
      });
  }, [token, refresh]);

  async function resend() {
    try {
      const result = await api.post<{ message: string; dev_verify_link?: string | null }>(
        "/auth/email/verify-request",
      );
      setNotice(result.message);
      if (result.dev_verify_link) setMessage(result.dev_verify_link);
    } catch (error) {
      setNotice(errorMessage(error));
    }
  }

  return (
    <AuthLayout title="Confirm your email" subtitle="Confirmation unlocks uploading, battles and voting.">
      {status === "confirming" ? <p className="text-sm text-haze">Checking your link…</p> : null}

      {status === "done" ? (
        <div className="space-y-4">
          <p className="text-sm text-lime">{message ?? "Email confirmed."}</p>
          <Link to="/feed">
            <Button className="w-full">Go to the feed</Button>
          </Link>
        </div>
      ) : null}

      {status === "failed" ? (
        <div className="space-y-4">
          <ErrorNote message={message ?? "That link is invalid or has expired."} />
          {user ? (
            <Button variant="secondary" className="w-full" onClick={resend}>
              Send a new link
            </Button>
          ) : (
            <Link to="/login">
              <Button className="w-full">Sign in to resend</Button>
            </Link>
          )}
        </div>
      ) : null}

      {status === "idle" ? (
        <div className="space-y-4 text-sm text-haze">
          <p>
            {user
              ? `We sent a confirmation link to ${user.email}. Open it on this device to finish setting up your account.`
              : "Open the confirmation link from your email to finish setting up your account."}
          </p>
          {notice ? <p className="text-xs text-coral">{notice}</p> : null}
          {message ? (
            <p className="break-all rounded-2xl border border-ink-800/80 bg-ink-950/60 p-3 text-xs text-haze">
              Development mode — no mail server configured, use this link:{" "}
              <a className="text-violet-soft underline" href={message}>
                {message}
              </a>
            </p>
          ) : null}
          {user ? (
            <div className="flex flex-col gap-2">
              <Button variant="secondary" onClick={resend}>
                Resend confirmation email
              </Button>
              <Link to="/feed">
                <Button variant="ghost" className="w-full">
                  Skip for now
                </Button>
              </Link>
            </div>
          ) : (
            <Link to="/login">
              <Button className="w-full">Sign in</Button>
            </Link>
          )}
        </div>
      ) : null}
    </AuthLayout>
  );
}