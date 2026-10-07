import { useEffect, useState } from "react";

// Chrome/Edge (Android phones & tablets, Windows, Mac, ChromeOS) fire this
// when the app can be installed; Safari (iPhone, iPad, Mac) never does, so
// those visitors get the Share -> Add to Home Screen / Add to Dock steps on
// the marketing site instead.
interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

function isInstalled(): boolean {
  return (
    window.matchMedia?.("(display-mode: standalone)").matches === true ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true
  );
}

export function InstallAppButton() {
  const [prompt, setPrompt] = useState<BeforeInstallPromptEvent | null>(null);

  useEffect(() => {
    if (isInstalled()) return;
    const onPrompt = (e: Event) => {
      e.preventDefault(); // keep the browser's own mini-infobar quiet; we offer a button
      setPrompt(e as BeforeInstallPromptEvent);
    };
    const onInstalled = () => setPrompt(null);
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  if (!prompt) return null;

  async function install() {
    if (!prompt) return;
    await prompt.prompt();
    await prompt.userChoice;
    setPrompt(null); // the event can only be used once
  }

  return (
    <button
      type="button"
      onClick={install}
      className="rounded-md border border-border bg-panel px-3 py-1.5 text-sm font-medium text-heading transition-all hover:-translate-y-px hover:border-accent/40"
    >
      Install app
    </button>
  );
}
