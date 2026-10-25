import { useCallback, useMemo, useState, type ReactNode } from "react";
import { I18nContext, STORAGE_KEY, initialLang, translator, type Lang } from "../i18n";

// Holds the chosen language for the whole app, sets <html lang> and
// remembers the choice in this browser.
export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => {
    const start = initialLang();
    document.documentElement.lang = start;
    return start;
  });
  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    document.documentElement.lang = next;
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // not remembered, but still switched
    }
  }, []);
  const value = useMemo(() => ({ lang, t: translator(lang), setLang }), [lang, setLang]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

