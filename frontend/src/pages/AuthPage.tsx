import { useState, type FormEvent } from "react";
import { siteLink, forgotPassword, login, setTenantApiKey, signup, startFreeTrial } from "../api";
import { Logo } from "../components/Logo";
import { LanguageSwitcher } from "../components/LanguageSwitcher";
import { useI18n } from "../i18n";
import type { MessageKey } from "../locales/en";
import { isNativeApp } from "../nativeApp";

type Mode = "login" | "signup" | "forgot" | "forgot-sent";

const inputClasses =
  "w-full rounded-lg border border-border bg-bg px-3 py-2.5 text-sm text-heading outline-none transition-colors placeholder:text-text/50 focus:border-accent";
const btnPrimary =
  "w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:-translate-y-px hover:shadow-md disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0";
const btnSecondary =
  "w-full rounded-lg border border-border bg-panel px-4 py-2.5 text-sm font-medium text-heading transition-all hover:-translate-y-px hover:border-accent/40 disabled:cursor-not-allowed disabled:opacity-50";
const linkBtn = "bg-transparent text-sm text-accent underline-offset-2 hover:underline";

const TITLES: Record<Mode, { title: MessageKey; subtitle: MessageKey }> = {
  login: { title: "auth.login.title", subtitle: "auth.login.subtitle" },
  signup: { title: "auth.signup.title", subtitle: isNativeApp() ? "auth.signup.subtitleNative" : "auth.signup.subtitle" },
  forgot: { title: "auth.forgot.title", subtitle: "auth.forgot.subtitle" },
  "forgot-sent": { title: "auth.forgotSent.title", subtitle: "auth.forgotSent.subtitle" },
};

interface Props {
  onSignedIn: () => void;
}

// The hosted deployment's front door (App.tsx shows it when there's no
// workspace yet): log in / create an account on the left, or skip the
// account entirely with a one-click free trial on the right.
export function AuthPage({ onSignedIn }: Props) {
  const { t, lang } = useI18n();
  const [mode, setMode] = useState<Mode>("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function switchTo(next: Mode) {
    setError(null);
    setMode(next);
  }

  async function run(action: () => Promise<void>, fallback: string) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : fallback);
    } finally {
      setBusy(false);
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (mode === "login") {
      run(async () => {
        setTenantApiKey((await login(email.trim(), password)).api_key);
        onSignedIn();
      }, t("auth.errLogin"));
    } else if (mode === "signup") {
      run(async () => {
        setTenantApiKey((await signup(name.trim(), email.trim(), password)).api_key);
        onSignedIn();
      }, t("auth.errSignup"));
    } else if (mode === "forgot") {
      run(async () => {
        await forgotPassword(email.trim());
        setMode("forgot-sent");
      }, t("common.somethingWrong"));
    }
  }

  function handleTrial() {
    run(async () => {
      setTenantApiKey((await startFreeTrial()).api_key);
      onSignedIn();
    }, t("auth.errTrial"));
  }

  const canSubmit =
    !busy &&
    Boolean(email) &&
    (mode === "forgot" || Boolean(password)) &&
    (mode !== "signup" || Boolean(name.trim()));

  return (
    <div className="min-h-screen font-sans text-text antialiased">
      <div className="mx-auto flex min-h-screen max-w-[960px] flex-col justify-center px-4 py-10 sm:px-6">
        <header className="animate-fade-in-up mb-8 flex flex-col items-center gap-1 text-center">
          <a href={siteLink("/", lang)}>
            <Logo />
          </a>
          <p className="text-sm text-text/75">{t("common.taglineShort")}</p>
          <LanguageSwitcher className="mt-3" />
        </header>

        <div className="grid items-stretch gap-5 md:grid-cols-[1.15fr_1fr]">
          {/* Account card */}
          <section
            className="animate-fade-in-up flex flex-col rounded-xl border border-border bg-panel p-6 shadow-sm sm:p-8"
            style={{ animationDelay: "60ms" }}
            aria-labelledby="auth-title"
          >
            <h1 id="auth-title" className="font-display text-2xl font-semibold tracking-tight text-heading">
              {t(TITLES[mode].title)}
            </h1>
            <p className="mt-1 text-sm text-text/75">{t(TITLES[mode].subtitle)}</p>

            {mode === "forgot-sent" ? (
              <div className="mt-6">
                <button className={btnSecondary} onClick={() => switchTo("login")}>
                  {t("auth.backToLogin")}
                </button>
              </div>
            ) : (
              <form className="mt-6 flex flex-col gap-3" onSubmit={handleSubmit}>
                {mode === "signup" && (
                  <label className="flex flex-col gap-1.5">
                    <span className="text-xs font-medium text-text/80">{t("auth.workspaceName")}</span>
                    <input
                      className={inputClasses}
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="Acme Inc."
                      autoComplete="organization"
                    />
                  </label>
                )}
                <label className="flex flex-col gap-1.5">
                  <span className="text-xs font-medium text-text/80">{t("common.email")}</span>
                  <input
                    className={inputClasses}
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@company.com"
                    autoComplete="email"
                  />
                </label>
                {mode !== "forgot" && (
                  <div className="flex flex-col gap-1.5">
                    <div className="flex items-baseline justify-between">
                      <label htmlFor="auth-password" className="text-xs font-medium text-text/80">
                        {t("common.password")}
                      </label>
                      {mode === "login" && (
                        <button type="button" className="text-xs text-accent hover:underline" onClick={() => switchTo("forgot")}>
                          {t("auth.forgotPassword")}
                        </button>
                      )}
                    </div>
                    <input
                      id="auth-password"
                      className={inputClasses}
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      autoComplete={mode === "signup" ? "new-password" : "current-password"}
                    />
                    {mode === "signup" && (
                      <span className="text-xs text-text/60">{t("common.passwordRules")}</span>
                    )}
                  </div>
                )}

                {error && (
                  <p role="alert" className="text-sm text-hot">
                    {error}
                  </p>
                )}

                <button type="submit" className={`${btnPrimary} mt-1`} disabled={!canSubmit}>
                  {busy
                    ? t("auth.pleaseWait")
                    : mode === "login"
                      ? t("auth.logIn")
                      : mode === "signup"
                        ? t("auth.createAccount")
                        : t("auth.sendResetLink")}
                </button>

                <p className="text-center text-sm text-text/75">
                  {mode === "login" && (
                    <>
                      {t("auth.newHere")}{" "}
                      <button type="button" className={linkBtn} onClick={() => switchTo("signup")}>
                        {t("auth.createAnAccount")}
                      </button>
                    </>
                  )}
                  {mode === "signup" && (
                    <>
                      {t("auth.haveAccount")}{" "}
                      <button type="button" className={linkBtn} onClick={() => switchTo("login")}>
                        {t("auth.logIn")}
                      </button>
                    </>
                  )}
                  {mode === "forgot" && (
                    <button type="button" className={linkBtn} onClick={() => switchTo("login")}>
                      {t("auth.backToLogin")}
                    </button>
                  )}
                </p>
              </form>
            )}
          </section>

          {/* No-account card */}
          <section
            className="animate-fade-in-up flex flex-col rounded-xl border border-accent/30 bg-accent-soft p-6 sm:p-8"
            style={{ animationDelay: "110ms" }}
            aria-labelledby="trial-title"
          >
            <h2 id="trial-title" className="font-display text-2xl font-semibold tracking-tight text-heading">
              {t("auth.justLooking")}
            </h2>
            <p className="mt-1 text-sm text-text/80">{t("auth.justLookingText")}</p>

            <ul className="mt-6 flex flex-col gap-3 text-sm text-text">
              {[
                t("auth.perkNoCard"),
                t("auth.perkUploads"),
                // The native apps don't sell plans (store billing rules).
                ...(isNativeApp() ? [] : [t("auth.perkUpgrade")]),
              ].map((item) => (
                <li key={item} className="flex items-start gap-2.5">
                  <span
                    aria-hidden="true"
                    className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent text-xs font-semibold text-white"
                  >
                    ✓
                  </span>
                  {item}
                </li>
              ))}
            </ul>

            <div className="mt-auto pt-8">
              <button className={btnPrimary} disabled={busy} onClick={handleTrial}>
                {t("auth.startTrial")}
              </button>
            </div>
          </section>
        </div>

        <p className="mt-6 text-center text-xs text-text/60">
          {t("auth.agreePrefix")}{" "}
          <a className="underline underline-offset-2 hover:text-heading" href={siteLink("/terms.html", lang)}>
            {t("auth.terms")}
          </a>{" "}
          {t("auth.and")}{" "}
          <a className="underline underline-offset-2 hover:text-heading" href={siteLink("/privacy.html", lang)}>
            {t("auth.privacy")}
          </a>
          .
        </p>
      </div>
    </div>
  );
}
