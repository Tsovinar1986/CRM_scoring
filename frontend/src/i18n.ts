import { createContext, useContext } from "react";
import { en, type MessageKey } from "./locales/en";
import { hy } from "./locales/hy";
import { ru } from "./locales/ru";

// English, Armenian and Russian. English (locales/en.ts) is the source: the
// other two must translate every key, which TypeScript checks.
export type Lang = "en" | "hy" | "ru";

export const LANGUAGES: { code: Lang; label: string; short: string }[] = [
  { code: "en", label: "English", short: "EN" },
  { code: "hy", label: "Հայերեն", short: "ՀՅ" },
  { code: "ru", label: "Русский", short: "РУ" },
];

const MESSAGES: Record<Lang, Record<MessageKey, string>> = { en, hy, ru };
function isLang(value: unknown): value is Lang {
  return value === "en" || value === "hy" || value === "ru";
}

// The visitor's saved choice, else their browser's language, else English.
export const STORAGE_KEY = "crmscoring_lang";

export function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (isLang(saved)) return saved;
  } catch {
    // storage blocked (private mode etc.) -- fall through
  }
  const browser = (typeof navigator !== "undefined" ? navigator.language : "en").slice(0, 2).toLowerCase();
  return isLang(browser) ? browser : "en";
}

export type Translate = (key: MessageKey, vars?: Record<string, string | number>) => string;

export function translator(lang: Lang): Translate {
  return (key, vars) => {
    let text = MESSAGES[lang][key] ?? en[key];
    if (vars) for (const [name, value] of Object.entries(vars)) text = text.split(`{${name}}`).join(String(value));
    return text;
  };
}

export interface I18n {
  lang: Lang;
  t: Translate;
  setLang: (lang: Lang) => void;
}

// Without a provider (e.g. a component rendered on its own in a test) the
// app is in English.
export const I18nContext = createContext<I18n>({ lang: "en", t: translator("en"), setLang: () => {} });

// The provider (components/LanguageProvider.tsx) holds the chosen language
// and remembers it.
export function useI18n(): I18n {
  return useContext(I18nContext);
}
