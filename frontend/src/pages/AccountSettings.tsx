import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import {
  cancelWorkspaceSubscription,
  changePassword,
  clearTenantApiKey,
  deleteAccount,
  fetchAccount,
  renameAccount,
  setTenantApiKey,
  siteLink,
} from "../api";
import { LanguageSwitcher } from "../components/LanguageSwitcher";
import { Logo } from "../components/Logo";
import { useI18n } from "../i18n";
import { isNativeApp } from "../nativeApp";
import type { Account } from "../types";

const inputClasses =
  "w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-heading outline-none transition-colors placeholder:text-text/50 focus:border-accent disabled:opacity-60";
const btnPrimary =
  "rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white shadow-sm transition-all hover:-translate-y-px hover:shadow-md disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0";
const btnSecondary =
  "rounded-lg border border-border bg-panel px-4 py-2 text-sm font-medium text-heading transition-all hover:-translate-y-px hover:border-accent/40 disabled:cursor-not-allowed disabled:opacity-50";
const btnDanger =
  "rounded-lg bg-hot px-4 py-2 text-sm font-medium text-white shadow-sm transition-all hover:-translate-y-px hover:shadow-md disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0";

function formatDate(epochSeconds: number, lang?: string): string {
  return new Date(epochSeconds * 1000).toLocaleDateString(lang, { year: "numeric", month: "long", day: "numeric" });
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
  const { t, lang } = useI18n();
  const PLAN_LABELS: Record<string, string> = { starter: t("acct.planStarter"), pro: "Pro", advanced: "Advanced" };
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
      .catch((err) => setLoadError(err instanceof Error ? err.message : ""));
  }

  useEffect(load, []);

  async function handleRename(e: FormEvent) {
    e.preventDefault();
    setNameStatus({ busy: true, message: null, error: false });
    try {
      const { name: saved } = await renameAccount(name.trim());
      setAccount((a) => (a ? { ...a, name: saved } : a));
      setNameStatus({ busy: false, message: t("acct.saved"), error: false });
    } catch (err) {
      setNameStatus({ busy: false, message: errorText(err, t("acct.errSave")), error: true });
    }
  }

  async function handleChangePassword(e: FormEvent) {
    e.preventDefault();
    if (newPassword !== confirmPassword) {
      setPasswordStatus({ busy: false, message: t("acct.mismatch"), error: true });
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
        message: t("acct.passwordChanged"),
        error: false,
      });
    } catch (err) {
      setPasswordStatus({ busy: false, message: errorText(err, t("acct.errPassword")), error: true });
    }
  }

  async function handleCancelSubscription() {
    if (!window.confirm(t("banner.confirmCancel"))) {
      return;
    }
    setCancelling(true);
    setBillingMessage(null);
    try {
      const { access_until } = await cancelWorkspaceSubscription();
      setBillingMessage({
        text: access_until
          ? t("acct.cancelledUntil", { date: formatDate(access_until, lang) })
          : t("acct.cancelled"),
        error: false,
      });
      load();
    } catch (err) {
      setBillingMessage({ text: errorText(err, t("banner.errCancel")), error: true });
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
      setDeleteError(errorText(err, t("acct.errDelete")));
      setDeleting(false);
    }
  }

  const header = (
    <div className="mb-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <a href={siteLink("/", lang)} className="inline-block">
          <Logo />
        </a>
        <LanguageSwitcher />
      </div>
      <a href="#" className="text-sm text-accent hover:underline">
        {t("acct.backToDashboard")}
      </a>
      <h1 className="mt-2 font-display text-[1.7rem] font-semibold tracking-tight text-heading">{t("app.accountSettings")}</h1>
    </div>
  );

  if (loadError !== null) {
    return (
      <div className="mx-auto max-w-[760px] px-4 py-8 sm:px-6">
        {header}
        <p className="text-sm text-hot">{loadError || t("acct.errLoad")}</p>
      </div>
    );
  }
  if (!account) return null;

  const planLabel = account.plan ? (PLAN_LABELS[account.plan] ?? account.plan) : t("acct.unlimited");
  const canDelete = deleteConfirm === "DELETE" && (!account.has_password || Boolean(deletePassword)) && !deleting;

  return (
    <div className="mx-auto max-w-[760px] px-4 py-8 sm:px-6">
      {header}

      <div className="flex flex-col gap-5">
        <Section title={t("acct.profile")}>
          <form onSubmit={handleRename} className="flex flex-col gap-3">
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-text/80">{t("acct.workspaceName")}</span>
              <div className="flex flex-col gap-2 sm:flex-row">
                <input className={inputClasses} value={name} onChange={(e) => setName(e.target.value)} maxLength={200} />
                <button
                  type="submit"
                  className={`${btnPrimary} shrink-0`}
                  disabled={nameStatus.busy || !name.trim() || name.trim() === account.name}
                >
                  {nameStatus.busy ? t("acct.saving") : t("acct.save")}
                </button>
              </div>
            </label>
            {nameStatus.message && (
              <p className={`text-sm ${nameStatus.error ? "text-hot" : "text-text/75"}`}>{nameStatus.message}</p>
            )}
          </form>
          <dl className="mt-3 divide-y divide-border border-t border-border">
            <Row label={t("common.email")}>{account.email ?? <span className="text-text/60">{t("acct.noEmail")}</span>}</Row>
            <Row label={t("acct.memberSince")}>{formatDate(account.created_at, lang)}</Row>
          </dl>
        </Section>

        <Section title={t("acct.planBilling")}>
          <dl className="divide-y divide-border">
            <Row label={t("acct.currentPlan")}>{planLabel}</Row>
            {account.uploads_limit !== null && (
              <Row label={t("acct.uploadsUsed")}>
                {t("acct.uploadsOf", { used: account.uploads_used, limit: account.uploads_limit })}
              </Row>
            )}
            {account.plan_expires_at && (
              <Row label={t("acct.accessUntil")}>
                {formatDate(account.plan_expires_at, lang)} <span className="text-text/60">{t("acct.wontRenew")}</span>
              </Row>
            )}
            <Row label={t("acct.billing")}>
              {account.has_subscription ? t("acct.renews") : t("acct.noSubscription")}
            </Row>
          </dl>
          <div className="mt-4 flex flex-wrap gap-2">
            {!isNativeApp() && (account.plan === "starter" || (account.plan_expires_at && !account.has_subscription)) && (
              <a href="#plans" className={btnPrimary}>
                {account.plan === "starter" ? t("acct.upgrade") : t("acct.resubscribe")}
              </a>
            )}
            {account.has_subscription && (
              <button type="button" className={btnSecondary} disabled={cancelling} onClick={handleCancelSubscription}>
                {cancelling ? t("banner.cancelling") : t("banner.cancelSubscription")}
              </button>
            )}
          </div>
          {billingMessage && (
            <p className={`mt-3 text-sm ${billingMessage.error ? "text-hot" : "text-text/75"}`}>{billingMessage.text}</p>
          )}
        </Section>

        <Section
          title={t("acct.security")}
          description={account.has_password ? t("acct.securityPassword") : t("acct.securityTrial")}
        >
          {account.has_password && (
            <form onSubmit={handleChangePassword} className="flex max-w-sm flex-col gap-3">
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium text-text/80">{t("acct.currentPassword")}</span>
                <input
                  className={inputClasses}
                  type="password"
                  autoComplete="current-password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium text-text/80">{t("acct.newPassword")}</span>
                <input
                  className={inputClasses}
                  type="password"
                  autoComplete="new-password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                />
                <span className="text-xs text-text/60">{t("common.passwordRules")}</span>
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium text-text/80">{t("acct.confirmPassword")}</span>
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
                  {passwordStatus.busy ? t("acct.changing") : t("acct.changePassword")}
                </button>
              </div>
            </form>
          )}
          <div className={account.has_password ? "mt-5 border-t border-border pt-4" : ""}>
            <button type="button" className={btnSecondary} onClick={handleSignOut}>
              {t("acct.signOut")}
            </button>
          </div>
        </Section>

        <Section
          title={t("acct.deleteTitle")}
          danger
          description={t("acct.deleteDesc")}
        >
          <form onSubmit={handleDelete} className="flex max-w-sm flex-col gap-3">
            {account.has_subscription && (
              <p className="rounded-lg bg-hot-soft px-3 py-2 text-sm text-hot">
                {t("acct.deleteSubscription", { plan: planLabel })}
              </p>
            )}
            {account.has_password && (
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium text-text/80">{t("acct.yourPassword")}</span>
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
              <span className="text-xs font-medium text-text/80">{t("acct.typeDelete")}</span>
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
                {deleting ? t("acct.deleting") : t("acct.deleteMine")}
              </button>
            </div>
          </form>
        </Section>
      </div>
    </div>
  );
}
