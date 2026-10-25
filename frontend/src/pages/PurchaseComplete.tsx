import { useI18n } from "../i18n";

function CheckIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <circle cx="12" cy="12" r="10" className="fill-accent-soft" />
      <path
        d="m8 12.5 2.5 2.5L16 9.5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function PurchaseComplete() {
  const { t } = useI18n();
  return (
    <div className="min-h-screen font-sans text-text antialiased">
      <div className="animate-fade-in-up mx-auto flex max-w-[480px] flex-col items-center gap-3 px-6 pt-[15vh] text-center">
        <div className="w-full rounded-xl border border-border bg-panel p-7 shadow-sm">
          <CheckIcon className="mx-auto mb-3 h-12 w-12 text-accent" />
          <h1 className="font-display text-2xl font-semibold text-heading">{t("purchase.title")}</h1>
          <p className="mt-3 text-sm text-text/75">{t("purchase.text")}</p>
          <p className="mt-3 text-sm text-text/75">{t("purchase.noEmail")}</p>
          <a
            className="mt-5 inline-block rounded-md bg-accent px-4 py-2 text-sm font-medium text-white shadow-sm transition-all hover:-translate-y-px hover:shadow-md"
            href="/"
          >
            {t("reset.backToApp")}
          </a>
        </div>
      </div>
    </div>
  );
}
