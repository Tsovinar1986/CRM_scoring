import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import {
  cancelWorkspaceSubscription,
  changePassword,
  clearTenantApiKey,
  deleteAccount,
  fetchAccount,
  renameAccount,
  setTenantApiKey,
} from "../api";
import type { Account } from "../types";

const inputClasses =
  "w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-heading outline-none transition-colors placeholder:text-text/50 focus:border-accent disabled:opacity-60";
const btnPrimary =
  "rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white shadow-sm transition-all hover:-translate-y-px hover:shadow-md disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0";
const btnSecondary =
  "rounded-lg border border-border bg-panel px-4 py-2 text-sm font-medium text-heading transition-all hover:-translate-y-px hover:border-accent/40 disabled:cursor-not-allowed disabled:opacity-50";
const btnDanger =
  "rounded-lg bg-hot px-4 py-2 text-sm font-medium text-white shadow-sm transition-all hover:-translate-y-px hover:shadow-md disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0";

const PLAN_LABELS: Record<string, string> = {
  starter: "Starter (free)",
  pro: "Pro",
  advanced: "Advanced",
};

function formatDate(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });
}

function errorText(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

function Section({ title, description, children, danger = false }: {
  title: string;
  description?: string;
  children: ReactNode;
  danger?: boolean;
}) {
  return (
    <section className={`rounded-xl border bg-panel p-5 shadow-sm sm:p-6 ${danger ? "border-hot/40" : "border-border"}`}>
      <h2 className={`font-display text-lg font-semibold ${danger ? "text-hot" : "text-heading"}`}>{title}</h2>
      {description && <p className="mt-1 text-sm text-text/75">{description}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 py-2 sm:flex-row sm:items-baseline sm:gap-4">
      <dt className="w-40 shrink-0 text-sm text-text/70">{label}</dt>
      <dd className="text-sm text-heading">{children}</dd>
    </div>
  );
}

interface Props {
  // The workspace key changed or went away (password change, sign-out, deletion).
  onWorkspaceChange: () => void;
}

// The signed-in workspace's settings: profile, plan & billing, password,
// sign-out, and permanent deletion.
export function AccountSettings({ onWorkspaceChange }: Props) {
  const [account, setAccount] = useState<Account | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [nameStatus, setNameStatus] = useState<{ busy: boolean; message: string | null; error: boolean }>({
    busy: false, message: null, error: false,
  });

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordStatus, setPasswordStatus] = useState<{ busy: boolean; message: string | null; error: boolean }>({
    busy: false, message: null, error: false,
  });

  const [cancelling, setCancelling] = useState(false);
  const [billingMessage, setBillingMessage] = useState<{ text: string; error: boolean } | null>(null);

  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [deletePassword, setDeletePassword] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  function load() {
    fetchAccount()
      .then((a) => {
        setAccount(a);
        setName(a.name);
      })
      .catch((err) => setLoadError(errorText(err, "Couldn't load your account.")));
  }

  useEffect(load, []);

  async function handleRename(e: FormEvent) {
    e.preventDefault();
    setNameStatus({ busy: true, message: null, error: false });
    try {
      const { name: saved } = await renameAccount(name.trim());
      setAccount((a) => (a ? { ...a, name: saved } : a));
      setNameStatus({ busy: false, message: "Saved.", error: false });
    } catch (err) {
      setNameStatus({ busy: false, message: errorText(err, "Couldn't save."), error: true });
    }
  }

  async function handleChangePassword(e: FormEvent) {
    e.preventDefault();
    if (newPassword !== confirmPassword) {
      setPasswordStatus({ busy: false, message: "The new passwords don't match.", error: true });
      return;
    }
    setPasswordStatus({ busy: true, message: null, error: false });
    try {
      const auth = await changePassword(currentPassword, newPassword);
      setTenantApiKey(auth.api_key);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setPasswordStatus({
        busy: false,
        message: "Password changed. Any other devices have been signed out.",
        error: false,
      });
    } catch (err) {
      setPasswordStatus({ busy: false, message: errorText(err, "Couldn't change your password."), error: true });
    }
  }

  async function handleCancelSubscription() {
    if (!window.confirm("Cancel your subscription? You'll keep access until the end of the period you've paid for.")) {
      return;
    }
    setCancelling(true);
    setBillingMessage(null);
    try {
      const { access_until } = await cancelWorkspaceSubscription();
      setBillingMessage({
        text: access_until
          ? `Subscription cancelled. You keep your plan until ${formatDate(access_until)}.`
          : "Subscription cancelled.",
        error: false,
      });
      load();
    } catch (err) {
      setBillingMessage({ text: errorText(err, "Couldn't cancel. Email hello@crmscoring.com."), error: true });
    } finally {
      setCancelling(false);
    }
  }

  function handleSignOut() {
    clearTenantApiKey();
    onWorkspaceChange();
  }

  async function handleDelete(e: FormEvent) {
    e.preventDefault();
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteAccount(account?.has_password ? deletePassword : null);
      clearTenantApiKey();
      onWorkspaceChange();
    } catch (err) {
      setDeleteError(errorText(err, "Couldn't delete your account."));
      setDeleting(false);
    }
  }

  const header = (
    <div className="mb-6">
      <a href="#" className="text-sm text-accent hover:underline">
        ← Back to dashboard
      </a>
      <h1 className="mt-2 font-display text-[1.7rem] font-semibold tracking-tight text-heading">Account settings</h1>
    </div>
  );

  if (loadError) {
    return (
      <div className="mx-auto max-w-[760px] px-4 py-8 sm:px-6">
        {header}
        <p className="text-sm text-hot">{loadError}</p>
      </div>
    );
  }
  if (!account) return null;

  const planLabel = account.plan ? (PLAN_LABELS[account.plan] ?? account.plan) : "Unlimited";
  const canDelete = deleteConfirm === "DELETE" && (!account.has_password || Boolean(deletePassword)) && !deleting;

  return (
    <div className="mx-auto max-w-[760px] px-4 py-8 sm:px-6">
      {header}

      <div className="flex flex-col gap-5">
        <Section title="Profile">
          <form onSubmit={handleRename} className="flex flex-col gap-3">
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-text/80">Workspace name</span>
              <div className="flex flex-col gap-2 sm:flex-row">
                <input className={inputClasses} value={name} onChange={(e) => setName(e.target.value)} maxLength={200} />
                <button
                  type="submit"
                  className={`${btnPrimary} shrink-0`}
                  disabled={nameStatus.busy || !name.trim() || name.trim() === account.name}
                >
                  {nameStatus.busy ? "Saving…" : "Save"}
                </button>
              </div>
            </label>
            {nameStatus.message && (
              <p className={`text-sm ${nameStatus.error ? "text-hot" : "text-text/75"}`}>{nameStatus.message}</p>
            )}
          </form>
          <dl className="mt-3 divide-y divide-border border-t border-border">
            <Row label="Email">{account.email ?? <span className="text-text/60">None (free-trial workspace)</span>}</Row>
            <Row label="Member since">{formatDate(account.created_at)}</Row>
          </dl>
        </Section>

        <Section title="Plan & billing">
          <dl className="divide-y divide-border">
            <Row label="Current plan">{planLabel}</Row>
            {account.uploads_limit !== null && (
              <Row label="Uploads used">
                {account.uploads_used} of {account.uploads_limit}
              </Row>
            )}
            {account.plan_expires_at && (
              <Row label="Access until">
                {formatDate(account.plan_expires_at)} <span className="text-text/60">(cancelled, won't renew)</span>
              </Row>
            )}
            <Row label="Billing">
              {account.has_subscription ? "Renews automatically, card checkout by Braintree" : "No active subscription"}
            </Row>
          </dl>
          <div className="mt-4 flex flex-wrap gap-2">
            {(account.plan === "starter" || (account.plan_expires_at && !account.has_subscription)) && (
              <a href="#plans" className={btnPrimary}>
                {account.plan === "starter" ? "Upgrade plan" : "Resubscribe"}
              </a>
            )}
            {account.has_subscription && (
              <button type="button" className={btnSecondary} disabled={cancelling} onClick={handleCancelSubscription}>
                {cancelling ? "Cancelling…" : "Cancel subscription"}
              </button>
            )}
          </div>
          {billingMessage && (
            <p className={`mt-3 text-sm ${billingMessage.error ? "text-hot" : "text-text/75"}`}>{billingMessage.text}</p>
          )}
        </Section>

        <Section
          title="Security"
          description={
            account.has_password
              ? "Changing your password signs out every other device."
              : "This free-trial workspace has no login. Anyone with this browser can use it until you sign out or delete it."
          }
        >
          {account.has_password && (
            <form onSubmit={handleChangePassword} className="flex max-w-sm flex-col gap-3">
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium text-text/80">Current password</span>
                <input
                  className={inputClasses}
                  type="password"
                  autoComplete="current-password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium text-text/80">New password</span>
                <input
                  className={inputClasses}
                  type="password"
                  autoComplete="new-password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                />
                <span className="text-xs text-text/60">
                  8+ characters, with an uppercase letter, a lowercase letter, a number and a symbol.
                </span>
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium text-text/80">Confirm new password</span>
                <input
                  className={inputClasses}
                  type="password"
                  autoComplete="new-password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                />
              </label>
              {passwordStatus.message && (
                <p role={passwordStatus.error ? "alert" : undefined} className={`text-sm ${passwordStatus.error ? "text-hot" : "text-text/75"}`}>
                  {passwordStatus.message}
                </p>
              )}
              <div>
                <button
                  type="submit"
                  className={btnPrimary}
                  disabled={passwordStatus.busy || !currentPassword || !newPassword || !confirmPassword}
                >
                  {passwordStatus.busy ? "Changing…" : "Change password"}
                </button>
              </div>
            </form>
          )}
          <div className={account.has_password ? "mt-5 border-t border-border pt-4" : ""}>
            <button type="button" className={btnSecondary} onClick={handleSignOut}>
              Sign out
            </button>
          </div>
        </Section>

        <Section
          title="Delete account"
          danger
          description="Permanently deletes this workspace, all its scored leads and alerts, and its login. This can't be undone."
        >
          <form onSubmit={handleDelete} className="flex max-w-sm flex-col gap-3">
            {account.has_subscription && (
              <p className="rounded-lg bg-hot-soft px-3 py-2 text-sm text-hot">
                Your {planLabel} subscription will be cancelled straight away, and you won't be charged again. Within 14
                days of your first payment you can still email hello@crmscoring.com for a full refund.
              </p>
            )}
            {account.has_password && (
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium text-text/80">Your password</span>
                <input
                  className={inputClasses}
                  type="password"
                  autoComplete="current-password"
                  value={deletePassword}
                  onChange={(e) => setDeletePassword(e.target.value)}
                />
              </label>
            )}
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-text/80">
                Type <strong className="font-semibold text-heading">DELETE</strong> to confirm
              </span>
              <input
                className={inputClasses}
                value={deleteConfirm}
                onChange={(e) => setDeleteConfirm(e.target.value)}
                autoComplete="off"
              />
            </label>
            {deleteError && (
              <p role="alert" className="text-sm text-hot">
                {deleteError}
              </p>
            )}
            <div>
              <button type="submit" className={btnDanger} disabled={!canDelete}>
                {deleting ? "Deleting…" : "Delete my account"}
              </button>
            </div>
          </form>
        </Section>
      </div>
    </div>
  );
}
