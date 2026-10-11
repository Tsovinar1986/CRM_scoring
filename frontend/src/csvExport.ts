import type { ScoredLead } from "./types";

const COLUMNS: { header: string; get: (lead: ScoredLead) => string | number }[] = [
  { header: "Company", get: (l) => l.company_name },
  { header: "Domain", get: (l) => l.domain },
  { header: "Contact", get: (l) => l.contact_name ?? "" },
  { header: "Title", get: (l) => l.contact_title ?? "" },
  { header: "Industry", get: (l) => l.industry ?? "" },
  { header: "Employees", get: (l) => l.employee_count ?? "" },
  { header: "Revenue (USD)", get: (l) => l.revenue_usd ?? "" },
  { header: "Geography", get: (l) => l.geography ?? "" },
  { header: "Tech Stack", get: (l) => l.tech_stack.join("; ") },
  { header: "Hiring", get: (l) => (l.is_hiring ? "yes" : "no") },
  { header: "Fit Score", get: (l) => l.fit_score },
  { header: "Account Fit (LLM)", get: (l) => l.account_fit_score },
  { header: "Combined Score", get: (l) => l.combined_score },
  { header: "Bucket", get: (l) => l.bucket },
  { header: "LLM Rationale", get: (l) => l.llm_rationale },
];

function csvEscape(value: string | number): string {
  const str = String(value);
  if (/[",\n]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

export function leadsToCsv(leads: ScoredLead[]): string {
  const header = COLUMNS.map((c) => csvEscape(c.header)).join(",");
  const rows = leads.map((lead) => COLUMNS.map((c) => csvEscape(c.get(lead))).join(","));
  return [header, ...rows].join("\n");
}

// The native iOS/macOS and Android apps show this web app in a web view, where
// blob downloads go nowhere; each app exposes a bridge that saves the file.
interface NativeBridges {
  webkit?: { messageHandlers?: { saveFile?: { postMessage: (msg: { filename: string; text: string }) => void } } };
  CRMScoringAndroid?: { saveFile: (filename: string, text: string) => void };
}

export function downloadLeadsCsv(leads: ScoredLead[], filename = "scored-leads.csv"): void {
  const csv = leadsToCsv(leads);
  const native = window as unknown as NativeBridges;
  const apple = native.webkit?.messageHandlers?.saveFile;
  if (apple) {
    apple.postMessage({ filename, text: csv });
    return;
  }
  if (native.CRMScoringAndroid) {
    native.CRMScoringAndroid.saveFile(filename, csv);
    return;
  }
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
