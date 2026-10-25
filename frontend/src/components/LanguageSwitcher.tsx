import { LANGUAGES, useI18n } from "../i18n";

// EN · ՀՅ · РУ -- switches the whole app; the choice is remembered.
export function LanguageSwitcher({ className = "" }: { className?: string }) {
  const { lang, setLang, t } = useI18n();
  return (
    <div role="group" aria-label={t("common.language")} className={`inline-flex rounded-md border border-border bg-panel p-0.5 ${className}`}>
      {LANGUAGES.map((option) => (
        <button
          key={option.code}
          type="button"
          lang={option.code}
          title={option.label}
          aria-label={option.label}
          aria-pressed={lang === option.code}
          onClick={() => setLang(option.code)}
          className={`rounded px-2 py-1 text-xs font-medium transition-colors ${
            lang === option.code ? "bg-accent text-white" : "text-text/75 hover:text-heading"
          }`}
        >
          {option.short}
        </button>
      ))}
    </div>
  );
}
