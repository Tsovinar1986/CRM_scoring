import { useEffect, useState } from "react";
import { confirmStripeCheckout } from "../api";
import { TIER_LABEL } from "../plans";
import type { SubscriptionActivation } from "../types";

type Phase =
  | { kind: "confirming" }
  | { kind: "done"; result: SubscriptionActivation }
  | { kind: "failed"; message: string };

function checkoutSessionFromUrl(): string | null {
  return new URLSearchParams(window.location.search).get("checkout");
}

// Stripe sends the buyer back to /?checkout=<session id> after paying. This
// confirms the payment, shows the outcome (workspace upgraded, or the license
// key for a self-hosted install) and then drops the id from the URL.
export function CheckoutReturn({ onDone }: { onDone: () => void }) {
  const [sessionId] = useState(checkoutSessionFromUrl);
  const [phase, setPhase] = useState<Phase>({ kind: "confirming" });
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    confirmStripeCheckout(sessionId).then(
      (result) => !cancelled && setPhase({ kind: "done", result }),
      (err) =>
        !cancelled &&
        setPhase({ kind: "failed", message: err instanceof Error ? err.message : "Couldn't confirm the payment." }),
    );
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  if (!sessionId) return null;

  function close() {
    const params = new URLSearchParams(window.location.search);
    params.delete("checkout");
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
      {phase.kind === "confirming" && <p className="text-text/75">Confirming your payment…</p>}

      {phase.kind === "failed" && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-hot">
            {phase.message} If you were charged, email hello@crmscoring.com and we'll sort it out.
          </p>
          <button className="text-xs text-text/70 underline hover:text-heading" onClick={close}>
            Close
          </button>
        </div>
      )}

      {phase.kind === "done" && phase.result.workspace_upgraded && phase.result.status === "ok" && (
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-heading">
            You're subscribed — this workspace is now on {TIER_LABEL[phase.result.tier]} with unlimited uploads.
          </p>
          <button className="rounded-md bg-accent px-3 py-1 text-xs font-medium text-white" onClick={close}>
            Continue
          </button>
        </div>
      )}

      {phase.kind === "done" && !phase.result.workspace_upgraded && phase.result.status === "ok" && (
        <div className="space-y-2">
          <p className="text-heading">
            You're subscribed. Your license key
            {phase.result.email.includes("@") && (
              <>
                {" "}
                (also emailed to <strong>{phase.result.email}</strong>)
              </>
            )}
            :
          </p>
          <div className="flex items-center gap-2">
            <code className="block flex-1 truncate rounded bg-accent-soft px-2 py-1 font-mono text-xs text-heading">
              {phase.result.license_key}
            </code>
            <button
              className="rounded-md border border-accent/40 px-3 py-1 text-xs font-medium text-accent hover:bg-accent-soft"
              onClick={() => copyKey((phase.result as { license_key: string }).license_key)}
            >
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <p className="text-xs text-text/75">
            Set it as <code className="font-mono">LICENSE_KEY</code> in your <code className="font-mono">.env</code> and
            restart. A fresh key is emailed each billing period.
          </p>
          <button className="text-xs text-text/70 underline hover:text-heading" onClick={close}>
            Close
          </button>
        </div>
      )}

      {phase.kind === "done" && phase.result.status === "duplicate" && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-heading">You're subscribed. Email hello@crmscoring.com for your license key.</p>
          <button className="text-xs text-text/70 underline hover:text-heading" onClick={close}>
            Close
          </button>
        </div>
      )}
    </div>
  );
}
