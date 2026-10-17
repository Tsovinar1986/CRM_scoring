import { useState } from "react";
import { startCheckout } from "../api";
import { TIER_LABEL } from "../plans";
import type { BillingConfig, BillingInterval, PaidTier } from "../types";

interface Props {
  config: BillingConfig;
  tier: PaidTier;
  interval: BillingInterval;
  onClose: () => void;
}

function priceFor(config: BillingConfig, tier: PaidTier, interval: BillingInterval): string | null | undefined {
  if (tier === "advanced") return interval === "annual" ? config.price_advanced_annual : config.price_advanced_monthly;
  return interval === "annual" ? config.price_annual : config.price_monthly;
}

// Payment happens on the provider's checkout page -- Paying (card details go
// on the bank's) or Stripe --
// own page): this sends the buyer there, and they come back to
// /?checkout=<session id> once they've paid (see CheckoutReturn). Card
// details never touch our servers.
export function Subscribe({ config, tier, interval, onClose }: Props) {
  const [redirecting, setRedirecting] = useState(false);
  const [error, setError] = useState<string | null>(
    config.checkout_available ? null : "Checkout isn't configured on this deployment.",
  );

  async function checkout() {
    setRedirecting(true);
    setError(null);
    try {
      const { url } = await startCheckout(tier, interval);
      window.location.assign(url);
    } catch (err) {
      setRedirecting(false);
      setError(err instanceof Error ? err.message : "Couldn't start checkout. Please try again.");
    }
  }

  const price = priceFor(config, tier, interval);
  const period = interval === "annual" ? "year" : "month";

  return (
    <div className="w-full rounded-lg border border-border bg-panel p-4 text-sm text-text shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-medium text-heading">
            {TIER_LABEL[tier]} — {price ? `$${Number(price)}/${period}` : interval}
          </p>
          <p className="text-xs text-text/75">
            Billed every {period} by card. Cancel anytime from Account settings.
          </p>
        </div>
        {!redirecting && (
          <button className="text-xs text-text/70 underline hover:text-heading" onClick={onClose}>
            Cancel
          </button>
        )}
      </div>

      {error && <p className="mt-3 text-hot">{error}</p>}
      {config.checkout_available && (
        <button
          type="button"
          onClick={checkout}
          disabled={redirecting}
          className="mt-3 w-full max-w-sm rounded-md bg-accent px-4 py-2 text-sm font-medium text-white shadow-sm disabled:cursor-not-allowed disabled:opacity-50"
        >
          {redirecting ? "Opening secure checkout…" : "Continue to secure checkout"}
        </button>
      )}
      {config.environment === "test" && (
        <p className="mt-2 text-xs text-text/60">Test mode: no real money is charged.</p>
      )}
    </div>
  );
}
