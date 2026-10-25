import { useEffect, useRef, useState } from "react";
import { LicenseRequiredError, TenantAuthError, fetchBillingConfig, uploadLeads } from "../api";
import type { BillingConfig, BillingInterval, ScoredLead } from "../types";
import { useI18n } from "../i18n";
import { isNativeApp } from "../nativeApp";
import { Subscribe } from "./Subscribe";

interface Props {
  onUploaded: (leads: ScoredLead[]) => void;
}

const btnPrimary =
  "rounded-md bg-accent px-4 py-2 text-sm font-medium text-white shadow-sm transition-all hover:-translate-y-px hover:shadow-md active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0 disabled:hover:shadow-sm";

function UploadCloudIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <path
        d="M7 18a4.5 4.5 0 0 1-.4-8.98A5.5 5.5 0 0 1 17.4 8.5 4 4 0 0 1 17 16.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M12 12v7m0-7 2.5 2.5M12 12l-2.5 2.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function UploadPanel({ onUploaded }: Props) {
  const { t } = useI18n();
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [licenseRequired, setLicenseRequired] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);
  const [trialLimitNotice, setTrialLimitNotice] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [billing, setBilling] = useState<BillingConfig | null>(null);
  const [buyInterval, setBuyInterval] = useState<BillingInterval | null>(null);
  const dragDepth = useRef(0);

  useEffect(() => {
    fetchBillingConfig()
      .then(setBilling)
      .catch(() => setBilling({ checkout_available: false, environment: "test" }));
  }, []);

  async function handleFile(file: File) {
    setBusy(true);
    setError(null);
    setLicenseRequired(false);
    setTrialLimitNotice(null);
    setFileName(file.name);
    try {
      const { leads, trialLimitedRows, trialTotalRows } = await uploadLeads(file);
      if (trialLimitedRows != null && trialTotalRows != null) {
        setTrialLimitNotice(
          t(isNativeApp() ? "upload.trialLimited" : "upload.trialLimitedUpgrade", { limited: trialLimitedRows, total: trialTotalRows })
        );
      }
      onUploaded(leads);
    } catch (err) {
      if (err instanceof LicenseRequiredError) {
        setLicenseRequired(true);
      } else {
        setError(
          err instanceof TenantAuthError
            ? t("upload.startTrialFirst")
            : err instanceof Error
              ? err.message
              : t("upload.failed")
        );
      }
    } finally {
      setBusy(false);
    }
  }

  function handleDragEnter(e: React.DragEvent) {
    e.preventDefault();
    dragDepth.current += 1;
    if (e.dataTransfer.types.includes("Files")) setDragActive(true);
  }

  function handleDragLeave(e: React.DragEvent) {
    e.preventDefault();
    dragDepth.current -= 1;
    if (dragDepth.current <= 0) {
      dragDepth.current = 0;
      setDragActive(false);
    }
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    dragDepth.current = 0;
    setDragActive(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  }

  return (
    <div className="rounded-xl border border-border bg-panel p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="font-display text-lg font-semibold text-heading">{t("upload.title")}</h2>
          <p className="mt-0.5 text-sm text-text/75">{t("upload.subtitle")}</p>
        </div>
      </div>

      <div
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
        className={`mt-4 flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-8 text-center transition-colors ${
          dragActive
            ? "border-accent bg-accent-soft"
            : "border-border hover:border-accent/50 hover:bg-accent-soft/40"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.xlsx,.xls"
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
          }}
        />
        <UploadCloudIcon
          className={`h-8 w-8 transition-colors ${dragActive ? "text-accent" : "text-text/50"}`}
        />
        {busy ? (
          <p className="text-sm font-medium text-heading">{t("upload.scoring")}</p>
        ) : (
          <>
            <p className="text-sm font-medium text-heading">
              {t("upload.dropPrefix")} <span className="text-accent">{t("upload.chooseOne")}</span>
            </p>
            {fileName && <p className="text-xs text-text/75">{fileName}</p>}
          </>
        )}
      </div>

      {error && <p className="mt-3 text-sm text-hot">{error}</p>}
      {trialLimitNotice && <p className="mt-3 text-sm text-text/75">{trialLimitNotice}</p>}
      {licenseRequired && (
        <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-border pt-4 text-sm text-hot">
          <p>{t("upload.trialExpired")}</p>
          {!isNativeApp() && (
            <>
              <button className={btnPrimary} disabled={busy} onClick={() => setBuyInterval("monthly")}>
                {t("upload.monthly")}
              </button>
              <button className={btnPrimary} disabled={busy} onClick={() => setBuyInterval("annual")}>
                {t("upload.annual")}
              </button>
              {buyInterval && billing && (
                <Subscribe
                  key={buyInterval}
                  config={billing}
                  tier="pro"
                  interval={buyInterval}
                  onClose={() => setBuyInterval(null)}
                />
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
