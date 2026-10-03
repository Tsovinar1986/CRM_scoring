import { useState, type FormEvent } from "react";
import { SITE_URL, forgotPassword, login, setTenantApiKey, signup, startFreeTrial } from "../api";
import { Logo } from "../components/Logo";

type Mode = "login" | "signup" | "forgot" | "forgot-sent";

const inputClasses =
  "w-full rounded-lg border border-border bg-bg px-3 py-2.5 text-sm text-heading outline-none transition-colors placeholder:text-text/50 focus:border-accent";
const btnPrimary =
  "w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:-translate-y-px hover:shadow-md disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0";
const btnSecondary =
  "w-full rounded-lg border border-border bg-panel px-4 py-2.5 text-sm font-medium text-heading transition-all hover:-translate-y-px hover:border-accent/40 disabled:cursor-not-allowed disabled:opacity-50";
const linkBtn = "bg-transparent text-sm text-accent underline-offset-2 hover:underline";

const TITLES: Record<Mode, { title: string; subtitle: string }> = {
  login: { title: "Welcome back", subtitle: "Log in to your workspace and pick up where you left off." },
  signup: { title: "Create your account", subtitle: "Your own private workspace — start free, upgrade any time." },
  forgot: { title: "Reset your password", subtitle: "We'll email you a link to choose a new one." },
  "forgot-sent": { title: "Check your inbox", subtitle: "If that email has an account, a reset link is on its way." },
};

interface Props {
  onSignedIn: () => void;
}

// The hosted deployment's front door (App.tsx shows it when there's no
// workspace yet): log in / create an account on the left, or skip the
// account entirely with a one-click free trial on the right.
export function AuthPage({ onSignedIn }: Props) {
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
      }, "Couldn't log in.");
    } else if (mode === "signup") {
      run(async () => {
        setTenantApiKey((await signup(name.trim(), email.trim(), password)).api_key);
        onSignedIn();
      }, "Couldn't create your account.");
    } else if (mode === "forgot") {
      run(async () => {
        await forgotPassword(email.trim());
        setMode("forgot-sent");
      }, "Something went wrong.");
    }
  }

  function handleTrial() {
    run(async () => {
      setTenantApiKey((await startFreeTrial()).api_key);
      onSignedIn();
    }, "Couldn't start your trial. Please try again.");
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
          <a href={SITE_URL}>
            <Logo />
          </a>
          <p className="text-sm text-text/75">Upload leads, get a ranked score, act on the hot ones.</p>
        </header>

        <div className="grid items-stretch gap-5 md:grid-cols-[1.15fr_1fr]">
          {/* Account card */}
          <section
            className="animate-fade-in-up flex flex-col rounded-xl border border-border bg-panel p-6 shadow-sm sm:p-8"
            style={{ animationDelay: "60ms" }}
            aria-labelledby="auth-title"
          >
            <h1 id="auth-title" className="font-display text-2xl font-semibold tracking-tight text-heading">
              {TITLES[mode].title}
            </h1>
            <p className="mt-1 text-sm text-text/75">{TITLES[mode].subtitle}</p>

            {mode === "forgot-sent" ? (
              <div className="mt-6">
                <button className={btnSecondary} onClick={() => switchTo("login")}>
                  Back to log in
                </button>
              </div>
            ) : (
              <form className="mt-6 flex flex-col gap-3" onSubmit={handleSubmit}>
                {mode === "signup" && (
                  <label className="flex flex-col gap-1.5">
                    <span className="text-xs font-medium text-text/80">Company or workspace name</span>
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
                  <span className="text-xs font-medium text-text/80">Email</span>
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
                        Password
                      </label>
                      {mode === "login" && (
                        <button type="button" className="text-xs text-accent hover:underline" onClick={() => switchTo("forgot")}>
                          Forgot password?
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
                      <span className="text-xs text-text/60">
                        8+ characters, with an uppercase letter, a lowercase letter, a number and a symbol.
                      </span>
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
                    ? "Please wait…"
                    : mode === "login"
                      ? "Log in"
                      : mode === "signup"
                        ? "Create account"
                        : "Send reset link"}
                </button>

                <p className="text-center text-sm text-text/75">
                  {mode === "login" && (
                    <>
                      New here?{" "}
                      <button type="button" className={linkBtn} onClick={() => switchTo("signup")}>
                        Create an account
                      </button>
                    </>
                  )}
                  {mode === "signup" && (
                    <>
                      Already have an account?{" "}
                      <button type="button" className={linkBtn} onClick={() => switchTo("login")}>
                        Log in
                      </button>
                    </>
                  )}
                  {mode === "forgot" && (
                    <button type="button" className={linkBtn} onClick={() => switchTo("login")}>
                      Back to log in
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
              Just looking?
            </h2>
            <p className="mt-1 text-sm text-text/80">Skip the account and score a sample list right now.</p>

            <ul className="mt-6 flex flex-col gap-3 text-sm text-text">
              {[
                "No email or card needed",
                "10 uploads, up to 10 leads each",
                "Upgrade to Pro or Advanced from inside the app",
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
                Start free trial
              </button>
            </div>
          </section>
        </div>

        <p className="mt-6 text-center text-xs text-text/60">
          By continuing you agree to the{" "}
          <a className="underline underline-offset-2 hover:text-heading" href={`${SITE_URL}/terms.html`}>
            Terms
          </a>{" "}
          and{" "}
          <a className="underline underline-offset-2 hover:text-heading" href={`${SITE_URL}/privacy.html`}>
            Privacy Policy
          </a>
          .
        </p>
      </div>
    </div>
  );
}
