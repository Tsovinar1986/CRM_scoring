import { afterEach, describe, expect, it, vi } from "vitest";
import {
  LicenseRequiredError,
  TenantAuthError,
  clearTenantApiKey,
  fetchBillingConfig,
  confirmStripeCheckout,
  fetchLicenseStatus,
  startFreeTrial,
  fetchLeads,
  setTenantApiKey,
  startStripeCheckout,
  uploadLeads,
} from "./api";

function mockFetchOnce(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      statusText: "error",
      json: async () => body,
    })
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  clearTenantApiKey();
});

describe("api error handling", () => {
  it("throws LicenseRequiredError on a 402 response", async () => {
    mockFetchOnce(402, { detail: "No valid license found." });

    await expect(fetchLeads()).rejects.toBeInstanceOf(LicenseRequiredError);
  });

  it("throws a plain Error with the server detail on other failures", async () => {
    mockFetchOnce(400, { detail: "File must include a domain column." });

    await expect(fetchLeads()).rejects.toThrow("File must include a domain column.");
  });

  it("returns parsed JSON on success", async () => {
    mockFetchOnce(200, [{ id: "1", company_name: "Acme" }]);

    const leads = await fetchLeads();
    expect(leads).toEqual([{ id: "1", company_name: "Acme" }]);
  });

  it("throws TenantAuthError on a 401 response", async () => {
    mockFetchOnce(401, { detail: "Invalid API key" });

    await expect(fetchLeads()).rejects.toBeInstanceOf(TenantAuthError);
  });
});

describe("tenant auth header", () => {
  it("sends no Authorization header when no workspace key is set", async () => {
    mockFetchOnce(200, []);
    await fetchLeads();

    const [, options] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(options?.headers?.Authorization).toBeUndefined();
  });

  it("sends Bearer <key> once a workspace key is set", async () => {
    setTenantApiKey("secret-key-123");
    mockFetchOnce(200, []);
    await fetchLeads();

    const [, options] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(options?.headers?.Authorization).toBe("Bearer secret-key-123");
  });
});

describe("uploadLeads", () => {
  it("posts multipart form data to /leads/upload", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [],
      headers: { get: () => null },
    });
    vi.stubGlobal("fetch", fetchMock);

    const file = new File(["a,b"], "leads.csv", { type: "text/csv" });
    const result = await uploadLeads(file);
    expect(result).toEqual({ leads: [], trialLimitedRows: null, trialTotalRows: null });

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/leads/upload");
    expect(options.method).toBe("POST");
    expect(options.body).toBeInstanceOf(FormData);
  });

  it("surfaces the trial row cap from response headers", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [],
      headers: {
        get: (name: string) => ({ "X-Trial-Limited-Rows": "10", "X-Trial-Total-Rows": "45" }[name] ?? null),
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await uploadLeads(new File(["a,b"], "leads.csv", { type: "text/csv" }));
    expect(result).toEqual({ leads: [], trialLimitedRows: 10, trialTotalRows: 45 });
  });
});

describe("fetchBillingConfig", () => {
  it("gets /billing/config and returns the parsed billing config", async () => {
    const config = {
      environment: "sandbox" as const,
      plans: { pro_monthly: "crm-scoring-pro-monthly" },
      checkout_available: false,
    };
    mockFetchOnce(200, config);

    const result = await fetchBillingConfig();
    expect(result).toEqual(config);

    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(url).toContain("/billing/config");
  });
});

describe("startStripeCheckout", () => {
  it("posts the plan to /billing/stripe/checkout and returns Stripe's URL", async () => {
    mockFetchOnce(200, { url: "https://checkout.stripe.com/c/pay/cs_test_1", session_id: "cs_test_1" });

    await expect(startStripeCheckout("pro", "annual")).resolves.toMatchObject({
      url: "https://checkout.stripe.com/c/pay/cs_test_1",
    });

    const [url, options] = vi.mocked(fetch).mock.calls[0];
    expect(url).toContain("/billing/stripe/checkout");
    expect(options?.method).toBe("POST");
    expect(JSON.parse(options?.body as string)).toEqual({ tier: "pro", interval: "annual", source: "app" });
  });
});

describe("confirmStripeCheckout", () => {
  it("gets /billing/stripe/session/<id> and returns the result", async () => {
    mockFetchOnce(200, { status: "duplicate" });

    await expect(confirmStripeCheckout("cs_test_1")).resolves.toEqual({ status: "duplicate" });

    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(url).toContain("/billing/stripe/session/cs_test_1");
  });

  it("surfaces an unpaid session's message", async () => {
    mockFetchOnce(409, { detail: "This payment isn't complete yet." });

    await expect(confirmStripeCheckout("cs_test_1")).rejects.toThrow("This payment isn't complete yet.");
  });
});

describe("free trial and workspace-aware license status", () => {
  it("starts a trial with a POST to /accounts/trial", async () => {
    mockFetchOnce(200, { tenant_id: "t1", name: "Free trial", api_key: "k" });

    await expect(startFreeTrial()).resolves.toEqual({ tenant_id: "t1", name: "Free trial", api_key: "k" });

    const [url, options] = vi.mocked(fetch).mock.calls[0];
    expect(url).toContain("/accounts/trial");
    expect(options?.method).toBe("POST");
  });

  it("sends the workspace key when fetching license status", async () => {
    setTenantApiKey("k");
    mockFetchOnce(200, { licensed: false, reason: "trial" });

    await fetchLicenseStatus();

    const [, options] = vi.mocked(fetch).mock.calls[0];
    expect(options?.headers).toEqual({ Authorization: "Bearer k" });
    clearTenantApiKey();
  });
});
