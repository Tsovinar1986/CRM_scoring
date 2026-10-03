import { useState } from "react";
import { resetPassword, setTenantApiKey } from "../api";

function LockIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <rect x="5" y="11" width="14" height="9" rx="2" className="fill-accent-soft" stroke="currentColor" strokeWidth="1.5" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

// Reached via the link emailed by POST /api/accounts/forgot-password
// (?token=...), which App.tsx routes here by pathname -- same pattern as
// PurchaseComplete for /purchase-complete.
export function ResetPasswordPage() {
  const token = new URLSearchParams(window.location.search).get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function handleSubmit() {
    if (password !== confirm) {
      setError("Passwords don't match.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const auth = await resetPassword(token, password);
      setTenantApiKey(auth.api_key);
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't reset your password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen font-sans text-text antialiased">
      <div className="animate-fade-in-up mx-auto flex max-w-[440px] flex-col items-center gap-3 px-6 pt-[15vh] text-center">
        <div className="w-full rounded-xl border border-border bg-panel p-7 shadow-sm">
          <LockIcon className="mx-auto mb-3 h-12 w-12 text-accent" />

          {!token ? (
            <>
              <h1 className="font-display text-2xl font-semibold text-heading">Invalid reset link</h1>
              <p className="mt-3 text-sm text-text/75">
                This link is missing its token — request a new one from the app.
              </p>
            </>
          ) : done ? (
            <>
              <h1 className="font-display text-2xl font-semibold text-heading">Password updated</h1>
              <p className="mt-3 text-sm text-text/75">
                You're signed in to your workspace with the new password.
              </p>
              <a
                className="mt-5 inline-block rounded-md bg-accent px-4 py-2 text-sm font-medium text-white shadow-sm transition-all hover:-translate-y-px hover:shadow-md"
                href="/"
              >
                Back to the app
              </a>
            </>
          ) : (
            <>
              <h1 className="font-display text-2xl font-semibold text-heading">Set a new password</h1>
              <div className="mt-4 flex flex-col gap-2 text-left">
                <input
                  type="password"
                  placeholder="New password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full rounded-md border border-border bg-panel px-3 py-1.5 text-sm text-heading outline-none focus:border-accent"
                />
                <input
                  type="password"
                  placeholder="Confirm new password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
                  className="w-full rounded-md border border-border bg-panel px-3 py-1.5 text-sm text-heading outline-none focus:border-accent"
                />
                <p className="text-[11px] text-text/60">
                  8+ characters, with at least one uppercase letter, one lowercase letter, one number, and one symbol.
                </p>
                {error && <p className="text-sm text-hot">{error}</p>}
                <button
                  className="mt-1 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white shadow-sm transition-all hover:-translate-y-px hover:shadow-md disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0"
                  disabled={busy || !password || !confirm}
                  onClick={handleSubmit}
                >
                  {busy ? "Updating…" : "Update password"}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
