import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { initialLang, useI18n } from "../i18n";
import { LanguageProvider } from "./LanguageProvider";
import { LanguageSwitcher } from "./LanguageSwitcher";

function Greeting() {
  const { t } = useI18n();
  return <p>{t("start.welcomeEmail", { email: "jo@example.com" })}</p>;
}

function renderApp() {
  return render(
    <LanguageProvider>
      <LanguageSwitcher />
      <Greeting />
    </LanguageProvider>,
  );
}

describe("language switching", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it("starts in English and switches to Armenian and Russian", async () => {
    renderApp();
    expect(screen.getByText("Welcome, jo@example.com")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Հայերեն" }));
    expect(screen.getByText("Բարի գալուստ, jo@example.com")).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("hy");

    await userEvent.click(screen.getByRole("button", { name: "Русский" }));
    expect(screen.getByText("Добро пожаловать, jo@example.com")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Русский" })).toHaveAttribute("aria-pressed", "true");
  });

  it("remembers the choice for the next visit", async () => {
    renderApp();
    await userEvent.click(screen.getByRole("button", { name: "Русский" }));

    expect(localStorage.getItem("crmscoring_lang")).toBe("ru");
    expect(initialLang()).toBe("ru");
  });

  it("starts in the browser's language on a first visit", () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("hy-AM");
    expect(initialLang()).toBe("hy");

    vi.spyOn(navigator, "language", "get").mockReturnValue("de-DE");
    expect(initialLang()).toBe("en");
  });
});

describe("language handed over from crmscoring.com", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => window.history.replaceState(null, "", "/"));

  it("opens in the ?lang= language and remembers it", () => {
    window.history.replaceState(null, "", "/?lang=hy");
    expect(initialLang()).toBe("hy");
    expect(localStorage.getItem("crmscoring_lang")).toBe("hy");
  });

  it("ignores an unknown ?lang=", () => {
    window.history.replaceState(null, "", "/?lang=xx");
    expect(initialLang()).toBe("en");
  });
});
