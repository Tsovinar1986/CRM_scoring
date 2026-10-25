import { LANGUAGES, useI18n } from "../i18n";

// EN · RU · ՀՅ -- switches the whole app; the choice is remembered. Looks
// like the switcher on crmscoring.com: a pill with the chosen language in ink.
export function LanguageSwitcher({ className = "" }: { className?: string }) {
  const { lang, setLang, t } = useI18n();
  return (
    <div role="group" aria-label={t("common.language")} className={`inline-flex rounded-full border border-border bg-panel p-0.5 ${className}`}>
      {LANGUAGES.map((option) => (
        <button
          key={option.code}
          type="button"
          lang={option.code}
          title={option.label}
          aria-label={option.label}
          aria-pressed={lang === option.code}
          onClick={() => setLang(option.code)}
          className={`min-w-9 rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${
            lang === option.code ? "bg-heading text-bg" : "text-text/75 hover:text-heading"
          }`}
        >
          {option.short}
        </button>
      ))}
    </div>
  );
}
