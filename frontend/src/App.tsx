import { useEffect, useState } from "react";
import {
  TenantAuthError,
  clearTenantApiKey,
  fetchLeads,
  fetchLicenseStatus,
  getTenantApiKey,
  setTenantApiKey,
} from "./api";
import { GettingStarted } from "./components/GettingStarted";
import { LeadDetail } from "./components/LeadDetail";
import { LeadsTable } from "./components/LeadsTable";
import { LicenseBanner } from "./components/LicenseBanner";
import { ScoreDashboard } from "./components/ScoreDashboard";
import { TenantSwitcher } from "./components/TenantSwitcher";
import { UploadPanel } from "./components/UploadPanel";
import { AccountSettings } from "./pages/AccountSettings";
import { AuthPage } from "./pages/AuthPage";
import { PurchaseComplete } from "./pages/PurchaseComplete";
import { ResetPasswordPage } from "./pages/ResetPasswordPage";
import type { ScoredLead } from "./types";

// crmscoring.com's "Get started free" opens the app with #workspace=<key>
// for the trial workspace it just created -- keep the key, drop it from the
// URL so it isn't left in history or a copied link.
function adoptWorkspaceFromUrl() {
  const match = window.location.hash.match(/^#workspace=([\w-]+)$/);
  if (!match) return;
  setTenantApiKey(match[1]);
  window.history.replaceState(null, "", window.location.pathname + window.location.search);
}

adoptWorkspaceFromUrl();

function LeadScoringApp() {
  const [leads, setLeads] = useState<ScoredLead[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [bucketFilter, setBucketFilter] = useState<"all" | "hot" | "warm" | "cold">("all");
  const [workspaceGeneration, setWorkspaceGeneration] = useState(0);
  const [authError, setAuthError] = useState<string | null>(null);
  // Hosted deployment with no workspace yet -> the sign-in page instead of
  // the app. null while that's still being checked.
  const [needsAuth, setNeedsAuth] = useState<boolean | null>(getTenantApiKey() ? false : null);
  // #account opens the settings page; any other hash is the dashboard
  // (scrolled to that section, e.g. #plans). Back/forward just work.
  const [showAccount, setShowAccount] = useState(window.location.hash === "#account");

  useEffect(() => {
    const onHashChange = () => setShowAccount(window.location.hash === "#account");
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    const target = !showAccount && window.location.hash.slice(1);
    if (target) document.getElementById(target)?.scrollIntoView({ behavior: "smooth" });
  }, [showAccount]);

  useEffect(() => {
    if (getTenantApiKey()) {
      setNeedsAuth(false);
      return;
    }
    fetchLicenseStatus()
      .then((status) => setNeedsAuth(Boolean(status.hosted)))
      .catch(() => setNeedsAuth(false));
  }, [workspaceGeneration]);

  useEffect(() => {
    fetchLeads()
      .then(setLeads)
      .catch((err) => {
        // No key at all on the hosted deployment is just a new visitor --
        // the banner offers a free trial. Only a rejected key is an error.
        if (err instanceof TenantAuthError && getTenantApiKey()) {
          clearTenantApiKey();
          setAuthError("That workspace key was rejected — disconnected.");
          setWorkspaceGeneration((n) => n + 1);
        }
      });
  }, [workspaceGeneration]);

  function handleUploaded(newLeads: ScoredLead[]) {
    setLeads(newLeads);
  }

  function handleLeadUpdate(updated: ScoredLead) {
    setLeads((prev) => prev.map((l) => (l.id === updated.id ? updated : l)));
  }

  function handleWorkspaceChange() {
    if (!getTenantApiKey() && showAccount) {
      // Signed out or deleted from the settings page -- nothing left to show there.
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
      setShowAccount(false);
    }
    setAuthError(null);
    setSelectedId(null);
    setWorkspaceGeneration((n) => n + 1);
  }

  const selectedLead = leads.find((l) => l.id === selectedId) ?? null;

  if (needsAuth === null) return null;
  if (needsAuth) {
    return (
      <>
        {authError && <p className="bg-hot-soft px-4 py-2 text-center text-sm text-hot">{authError}</p>}
        <AuthPage onSignedIn={handleWorkspaceChange} />
      </>
    );
  }
  if (showAccount && getTenantApiKey()) {
    return (
      <div className="min-h-screen bg-bg font-sans text-text antialiased">
        <AccountSettings key={workspaceGeneration} onWorkspaceChange={handleWorkspaceChange} />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-bg font-sans text-text antialiased">
      <div className="mx-auto max-w-[1200px] px-6 py-8">
        <header className="animate-fade-in-up mb-7">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <span
                aria-hidden="true"
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-accent to-accent/70 font-display text-lg font-semibold text-white shadow-[0_2px_8px_-2px_var(--color-accent)]"
              >
                A
              </span>
              <div>
                <h1 className="font-display text-[1.7rem] font-semibold tracking-tight text-heading">
                  AI Lead Generation &amp; Scoring Agent
                </h1>
                <p className="mt-0.5 text-sm text-text/75">
                  Upload leads, get a ranked hybrid score, act on the hot ones.
                </p>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              {getTenantApiKey() && (
                <a href="#account" className="text-sm font-medium text-accent hover:underline">
                  Account settings
                </a>
              )}
              <TenantSwitcher onChange={handleWorkspaceChange} />
            </div>
          </div>
          {authError && <p className="mt-3 text-sm text-hot">{authError}</p>}
        </header>

        {/* Decides for itself whether to show (see LicenseBanner). Keyed on
            the workspace so it re-reads status after connect/disconnect. */}
        <div id="plans" className="animate-fade-in-up mb-5 scroll-mt-6 empty:hidden" style={{ animationDelay: "60ms" }}>
          <LicenseBanner key={workspaceGeneration} onWorkspaceChange={handleWorkspaceChange} />
        </div>

        <main className="flex flex-col gap-5">
          {/* Signed-in workspaces only: setup checklist + hot leads to act on. */}
          <div className="animate-fade-in-up empty:hidden" style={{ animationDelay: "85ms" }}>
            <GettingStarted
              key={workspaceGeneration}
              leads={leads}
              onSelectLead={(lead) => setSelectedId(lead.id)}
            />
          </div>
          <div id="upload" className="animate-fade-in-up scroll-mt-6" style={{ animationDelay: "110ms" }}>
            <UploadPanel onUploaded={handleUploaded} />
          </div>
          {leads.length > 0 && (
            <div className="animate-fade-in-up" style={{ animationDelay: "135ms" }}>
              <ScoreDashboard leads={leads} />
            </div>
          )}
          <div className="animate-fade-in-up" style={{ animationDelay: "160ms" }}>
            <LeadsTable
              leads={leads}
              selectedId={selectedId}
              bucketFilter={bucketFilter}
              onSelect={(lead) => setSelectedId(lead.id)}
              onBucketFilterChange={setBucketFilter}
            />
          </div>
        </main>
      </div>

      {selectedLead && (
        <LeadDetail
          lead={selectedLead}
          onClose={() => setSelectedId(null)}
          onUpdate={handleLeadUpdate}
        />
      )}
    </div>
  );
}

function App() {
  if (window.location.pathname === "/purchase-complete") {
    return <PurchaseComplete />;
  }
  if (window.location.pathname === "/reset-password") {
    return <ResetPasswordPage />;
  }
  return <LeadScoringApp />;
}

export default App;
