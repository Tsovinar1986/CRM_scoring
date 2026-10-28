import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CheckoutReturn } from "./CheckoutReturn";
import * as api from "../api";

vi.mock("../api", async (importActual) => {
  const actual = await importActual<typeof api>();
  return { ...actual, confirmCheckout: vi.fn(), confirmPayPal: vi.fn() };
});

describe("CheckoutReturn", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.history.replaceState(null, "", "/?checkout=cs_test_1");
  });

  afterEach(() => {
    window.history.replaceState(null, "", "/");
  });

  it("renders nothing when not returning from checkout", () => {
    window.history.replaceState(null, "", "/");
    const { container } = render(<CheckoutReturn onDone={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
    expect(api.confirmCheckout).not.toHaveBeenCalled();
  });

  it("confirms the payment and says the workspace was upgraded", async () => {
    vi.mocked(api.confirmCheckout).mockResolvedValue({
      status: "ok", email: "jane@example.com", tier: "advanced", plan: "monthly", license_key: "LK", workspace_upgraded: true,
    });
    const onDone = vi.fn();

    render(<CheckoutReturn onDone={onDone} />);

    expect(await screen.findByText(/this workspace is now on advanced/i)).toBeInTheDocument();
    expect(api.confirmCheckout).toHaveBeenCalledWith("cs_test_1");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(onDone).toHaveBeenCalled();
    expect(window.location.search).toBe("");
  });

  it("shows the license key for a self-hosted buyer", async () => {
    vi.mocked(api.confirmCheckout).mockResolvedValue({
      status: "ok", email: "buyer@example.com", tier: "pro", plan: "annual", license_key: "LK-123", workspace_upgraded: false,
    });

    render(<CheckoutReturn onDone={vi.fn()} />);

    expect(await screen.findByText("LK-123")).toBeInTheDocument();
    expect(screen.getByText(/also emailed to buyer@example\.com/)).toBeInTheDocument();
  });

  it("explains when the payment can't be confirmed", async () => {
    vi.mocked(api.confirmCheckout).mockRejectedValue(new Error("This payment isn't complete yet."));

    render(<CheckoutReturn onDone={vi.fn()} />);

    expect(await screen.findByText(/this payment isn't complete yet/i)).toBeInTheDocument();
  });
});

describe("CheckoutReturn after PayPal", () => {
  afterEach(() => window.history.replaceState(null, "", "/"));

  it("confirms the PayPal subscription it came back with and tidies the URL", async () => {
    window.history.replaceState(null, "", "/?paypal=1&subscription_id=I-ABC123&ba_token=BA-1&token=T-1");
    vi.mocked(api.confirmPayPal).mockResolvedValue({
      status: "ok", email: "jo@example.com", tier: "pro", plan: "monthly", license_key: "LK", workspace_upgraded: true,
    });
    const onDone = vi.fn();

    render(<CheckoutReturn onDone={onDone} />);

    expect(await screen.findByText(/this workspace is now on Pro/i)).toBeInTheDocument();
    expect(api.confirmPayPal).toHaveBeenCalledWith("I-ABC123");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(window.location.search).toBe("");
  });
});
