import { afterEach, describe, expect, it, vi } from "vitest";
import { downloadLeadsCsv } from "./csvExport";
import type { ScoredLead } from "./types";

const lead = {
  company_name: "Acme",
  domain: "acme.com",
  contact_name: null,
  contact_title: null,
  industry: null,
  employee_count: null,
  revenue_usd: null,
  geography: null,
  tech_stack: [],
  is_hiring: false,
  fit_score: 80,
  account_fit_score: 70,
  combined_score: 75,
  bucket: "hot",
  llm_rationale: "Good fit",
} as unknown as ScoredLead;

const win = window as unknown as Record<string, unknown>;

describe("downloadLeadsCsv in the native apps", () => {
  afterEach(() => {
    delete win.webkit;
    delete win.CRMScoringAndroid;
  });

  it("hands the CSV to the iOS/macOS app's saveFile bridge", () => {
    const postMessage = vi.fn();
    win.webkit = { messageHandlers: { saveFile: { postMessage } } };
    downloadLeadsCsv([lead]);
    expect(postMessage).toHaveBeenCalledOnce();
    const msg = postMessage.mock.calls[0][0];
    expect(msg.filename).toBe("scored-leads.csv");
    expect(msg.text).toContain("Acme,acme.com");
  });

  it("hands the CSV to the Android app's saveFile bridge", () => {
    const saveFile = vi.fn();
    win.CRMScoringAndroid = { saveFile };
    downloadLeadsCsv([lead], "hot.csv");
    expect(saveFile).toHaveBeenCalledWith("hot.csv", expect.stringContaining("Acme,acme.com"));
  });
});
