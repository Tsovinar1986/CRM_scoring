import { useState } from "react";
import { startCheckout, startPayPalCheckout } from "../api";
import { useI18n } from "../i18n";
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

// Payment happens on Stripe's own checkout page: this sends the buyer there, and they come back to
// /?checkout=<session id> once they've paid (see CheckoutReturn). Card
// details never touch our servers.
export function Subscribe({ config, tier, interval, onClose }: Props) {
  const { t } = useI18n();
  const [redirecting, setRedirecting] = useState<"card" | "paypal" | null>(null);
  const [error, setError] = useState<string | null>(
    config.checkout_available || config.paypal_available ? null : t("sub.notConfigured"),
  );

  async function payWithPayPal() {
    setRedirecting("paypal");
    setError(null);
    try {
      const { url } = await startPayPalCheckout(tier, interval);
      window.location.assign(url);
    } catch (err) {
      setRedirecting(null);
      setError(err instanceof Error ? err.message : t("sub.errStart"));
    }
  }

  async function checkout() {
    setRedirecting("card");
    setError(null);
    try {
      const { url } = await startCheckout(tier, interval);
      window.location.assign(url);
    } catch (err) {
      setRedirecting(null);
      setError(err instanceof Error ? err.message : t("sub.errStart"));
    }
  }

  const price = priceFor(config, tier, interval);
  const annual = interval === "annual";

  return (
    <div className="w-full rounded-lg border border-border bg-panel p-4 text-sm text-text shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-medium text-heading">
            {TIER_LABEL[tier]} —{" "}
            {price ? t(annual ? "sub.perYear" : "sub.perMonth", { price: Number(price) }) : t(annual ? "sub.annual" : "sub.monthly")}
          </p>
          <p className="text-xs text-text/75">{t(annual ? "sub.billedYearly" : "sub.billedMonthly")}</p>
        </div>
        {redirecting === null && (
          <button className="text-xs text-text/70 underline hover:text-heading" onClick={onClose}>
            {t("common.cancel")}
          </button>
        )}
      </div>

      {error && <p className="mt-3 text-hot">{error}</p>}
      {config.checkout_available && (
        <button
          type="button"
          onClick={checkout}
          disabled={redirecting !== null}
          className="mt-3 w-full max-w-sm rounded-md bg-accent px-4 py-2 text-sm font-medium text-white shadow-sm disabled:cursor-not-allowed disabled:opacity-50"
        >
          {redirecting === "card" ? t("sub.opening") : t("sub.continue")}
        </button>
      )}
      {config.paypal_available && (
        <button
          type="button"
          onClick={payWithPayPal}
          disabled={redirecting !== null}
          className="mt-2 block w-full max-w-sm rounded-md bg-[#ffc439] px-4 py-2 text-sm font-semibold text-[#003087] shadow-sm disabled:cursor-not-allowed disabled:opacity-50"
        >
          {redirecting === "paypal" ? t("sub.openingPayPal") : t("sub.payPal")}
        </button>
      )}
      {config.checkout_available && config.environment === "test" && (
        <p className="mt-2 text-xs text-text/60">{t("sub.testMode")}</p>
      )}
    </div>
  );
}
