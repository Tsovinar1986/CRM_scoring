import { useEffect, useState } from "react";
import { confirmCheckout, confirmPayPal } from "../api";
import { useI18n } from "../i18n";
import { TIER_LABEL } from "../plans";
import type { SubscriptionActivation } from "../types";

type Phase =
  | { kind: "confirming" }
  | { kind: "done"; result: SubscriptionActivation }
  | { kind: "failed"; message: string };

// Stripe comes back with ?checkout=<session id>; PayPal with
// ?paypal=1&subscription_id=I-... (it adds its own ba_token/token too).
function checkoutSessionFromUrl(): string | null {
  const params = new URLSearchParams(window.location.search);
  return params.get("checkout") ?? (params.get("paypal") ? params.get("subscription_id") : null);
}

// The buyer comes back to /?checkout=<session id> after paying. This
// confirms the payment, shows the outcome (workspace upgraded, or the license
// key for a self-hosted install) and then drops the id from the URL.
export function CheckoutReturn({ onDone }: { onDone: () => void }) {
  const { t } = useI18n();
  const [sessionId] = useState(checkoutSessionFromUrl);
  const [phase, setPhase] = useState<Phase>({ kind: "confirming" });
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    (sessionId.startsWith("I-") ? confirmPayPal(sessionId) : confirmCheckout(sessionId)).then(
      (result) => !cancelled && setPhase({ kind: "done", result }),
      (err) =>
        !cancelled &&
        setPhase({ kind: "failed", message: err instanceof Error ? err.message : t("ret.errConfirm") }),
    );
    return () => {
      cancelled = true;
    };
  }, [sessionId, t]);

  if (!sessionId) return null;

  function close() {
    const params = new URLSearchParams(window.location.search);
    for (const name of ["checkout", "paypal", "subscription_id", "ba_token", "token"]) params.delete(name);
    const query = params.toString();
    window.history.replaceState(null, "", window.location.pathname + (query ? `?${query}` : "") + window.location.hash);
    onDone();
  }

  async function copyKey(key: string) {
    try {
      await navigator.clipboard.writeText(key);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="mb-5 rounded-lg border border-border bg-panel p-4 text-sm text-text shadow-sm" role="status">
      {phase.kind === "confirming" && <p className="text-text/75">{t("ret.confirming")}</p>}

      {phase.kind === "failed" && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-hot">
            {phase.message} {t("ret.ifCharged")}
          </p>
          <button className="text-xs text-text/70 underline hover:text-heading" onClick={close}>
            {t("common.close")}
          </button>
        </div>
      )}

      {phase.kind === "done" && phase.result.workspace_upgraded && phase.result.status === "ok" && (
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-heading">
            {t("ret.upgraded", { tier: TIER_LABEL[phase.result.tier] })}
          </p>
          <button className="rounded-md bg-accent px-3 py-1 text-xs font-medium text-white" onClick={close}>
            {t("common.continue")}
          </button>
        </div>
      )}

      {phase.kind === "done" && !phase.result.workspace_upgraded && phase.result.status === "ok" && (
        <div className="space-y-2">
          <p className="text-heading">
            {phase.result.email.includes("@")
              ? t("ret.keyIntroEmailed", { email: phase.result.email })
              : t("ret.keyIntro")}
          </p>
          <div className="flex items-center gap-2">
            <code className="block flex-1 truncate rounded bg-accent-soft px-2 py-1 font-mono text-xs text-heading">
              {phase.result.license_key}
            </code>
            <button
              className="rounded-md border border-accent/40 px-3 py-1 text-xs font-medium text-accent hover:bg-accent-soft"
              onClick={() => copyKey((phase.result as { license_key: string }).license_key)}
            >
              {copied ? t("common.copied") : t("common.copy")}
            </button>
          </div>
          <p className="text-xs text-text/75">{t("ret.keyHowTo")}</p>
          <button className="text-xs text-text/70 underline hover:text-heading" onClick={close}>
            {t("common.close")}
          </button>
        </div>
      )}

      {phase.kind === "done" && phase.result.status === "duplicate" && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-heading">{t("ret.duplicate")}</p>
          <button className="text-xs text-text/70 underline hover:text-heading" onClick={close}>
            {t("common.close")}
          </button>
        </div>
      )}
    </div>
  );
}
