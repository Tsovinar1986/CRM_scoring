import { useState } from "react";
import { clearTenantApiKey, forgotPassword, getTenantApiKey, login, setTenantApiKey, signup } from "../api";
import { useI18n } from "../i18n";

interface Props {
  onChange: () => void;
}

type Mode = "closed" | "login" | "signup" | "forgot" | "forgot-sent" | "paste-key";

const inputClasses =
  "w-full min-w-[220px] rounded-md border border-border bg-panel px-3 py-1.5 text-sm text-heading outline-none focus:border-accent";
const btnPrimary =
  "rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white shadow-sm transition-all hover:-translate-y-px hover:shadow-md disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0";
const btnSecondary =
  "rounded-md border border-border bg-panel px-3 py-1.5 text-sm text-heading transition-all hover:-translate-y-px hover:border-accent/40";
const linkBtn = "bg-transparent text-xs text-accent underline underline-offset-2";

// Only relevant when a seller runs one shared instance for multiple
// customers -- a single self-hosted buyer never needs this, so it stays a
// small, unobtrusive control rather than a blocking login screen. No key
// set = the backend's default tenant, identical to this app's original
// zero-config behavior. Self-serve signup/login is an alternative to a
// seller manually running scripts/create_tenant.py; "paste a key" (the
// original flow) still works too, for tenants provisioned that way.
export function TenantSwitcher({ onChange }: Props) {
  const { t } = useI18n();
  const [mode, setMode] = useState<Mode>("closed");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pastedKey, setPastedKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hasKey = Boolean(getTenantApiKey());

  function reset() {
    setMode("closed");
    setName("");
    setEmail("");
    setPassword("");
    setPastedKey("");
    setError(null);
    setBusy(false);
  }

  function switchTo(next: Mode) {
    setError(null);
    setMode(next);
  }

  async function handleSignup() {
    setBusy(true);
    setError(null);
    try {
      const auth = await signup(name.trim(), email.trim(), password);
      setTenantApiKey(auth.api_key);
      reset();
      onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("ts.errCreate"));
    } finally {
      setBusy(false);
    }
  }

  async function handleLogin() {
    setBusy(true);
    setError(null);
    try {
      const auth = await login(email.trim(), password);
      setTenantApiKey(auth.api_key);
      reset();
      onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("auth.errLogin"));
    } finally {
      setBusy(false);
    }
  }

  async function handleForgotPassword() {
    setBusy(true);
    setError(null);
    try {
      await forgotPassword(email.trim());
      setMode("forgot-sent");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.somethingWrong"));
    } finally {
      setBusy(false);
    }
  }

  function handlePasteKey() {
    if (pastedKey.trim()) {
      setTenantApiKey(pastedKey.trim());
      reset();
      onChange();
    }
  }

  function handleClear() {
    clearTenantApiKey();
    onChange();
  }

  if (mode === "closed") {
    return (
      <div className="flex flex-wrap items-center gap-2">
        {hasKey ? (
          <>
            <span className="text-sm text-text/75">{t("ts.connected")}</span>
            <button className={btnSecondary} onClick={handleClear}>
              {t("ts.disconnect")}
            </button>
          </>
        ) : (
          <button className={linkBtn} onClick={() => switchTo("login")}>
            {t("ts.loginSignup")}
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="w-full max-w-[280px] rounded-lg border border-border bg-panel p-3 shadow-sm">
      {mode === "login" && (
        <div className="flex flex-col gap-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-text/70">{t("auth.logIn")}</h3>
          <input
            type="email"
            placeholder={t("common.email")}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={inputClasses}
          />
          <input
            type="password"
            placeholder={t("common.password")}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleLogin()}
            className={inputClasses}
          />
          {error && <p className="text-xs text-hot">{error}</p>}
          <div className="flex items-center gap-2">
            <button className={btnPrimary} disabled={busy || !email || !password} onClick={handleLogin}>
              {busy ? t("ts.loggingIn") : t("auth.logIn")}
            </button>
            <button className={btnSecondary} onClick={reset}>
              {t("common.cancel")}
            </button>
          </div>
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            <button className={linkBtn} onClick={() => switchTo("signup")}>
              {t("ts.newHereSignup")}
            </button>
            <button className={linkBtn} onClick={() => switchTo("forgot")}>
              {t("auth.forgotPassword")}
            </button>
            <button className={linkBtn} onClick={() => switchTo("paste-key")}>
              {t("ts.pasteInstead")}
            </button>
          </div>
        </div>
      )}

      {mode === "signup" && (
        <div className="flex flex-col gap-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-text/70">{t("ts.createWorkspace")}</h3>
          <input
            type="text"
            placeholder={t("ts.namePlaceholder")}
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={inputClasses}
          />
          <input
            type="email"
            placeholder={t("common.email")}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={inputClasses}
          />
          <input
            type="password"
            placeholder={t("common.password")}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSignup()}
            className={inputClasses}
          />
          <p className="text-[11px] text-text/60">{t("common.passwordRules")}</p>
          {error && <p className="text-xs text-hot">{error}</p>}
          <div className="flex items-center gap-2">
            <button
              className={btnPrimary}
              disabled={busy || !name || !email || !password}
              onClick={handleSignup}
            >
              {busy ? t("ts.creating") : t("ts.signUp")}
            </button>
            <button className={btnSecondary} onClick={reset}>
              {t("common.cancel")}
            </button>
          </div>
          <button className={linkBtn} onClick={() => switchTo("login")}>
            {t("ts.haveAccountLogin")}
          </button>
        </div>
      )}

      {mode === "forgot" && (
        <div className="flex flex-col gap-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-text/70">{t("auth.forgot.title")}</h3>
          <input
            type="email"
            placeholder={t("common.email")}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleForgotPassword()}
            className={inputClasses}
          />
          {error && <p className="text-xs text-hot">{error}</p>}
          <div className="flex items-center gap-2">
            <button className={btnPrimary} disabled={busy || !email} onClick={handleForgotPassword}>
              {busy ? t("ts.sending") : t("auth.sendResetLink")}
            </button>
            <button className={btnSecondary} onClick={() => switchTo("login")}>
              {t("common.back")}
            </button>
          </div>
        </div>
      )}

      {mode === "forgot-sent" && (
        <div className="flex flex-col gap-2">
          <p className="text-sm text-text">
            {t("ts.resetSent")}
          </p>
          <button className={btnSecondary} onClick={reset}>
            {t("common.done")}
          </button>
        </div>
      )}

      {mode === "paste-key" && (
        <div className="flex flex-col gap-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-text/70">{t("ts.pasteTitle")}</h3>
          <input
            type="password"
            placeholder={t("ts.pastePlaceholder")}
            value={pastedKey}
            onChange={(e) => setPastedKey(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handlePasteKey()}
            className={inputClasses}
          />
          <div className="flex items-center gap-2">
            <button className={btnPrimary} disabled={!pastedKey.trim()} onClick={handlePasteKey}>
              {t("ts.connect")}
            </button>
            <button className={btnSecondary} onClick={() => switchTo("login")}>
              {t("common.back")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
