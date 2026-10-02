import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AccountSettings } from "./AccountSettings";
import * as api from "../api";
import type { Account } from "../types";

vi.mock("../api", async (importActual) => {
  const actual = await importActual<typeof api>();
  return {
    ...actual,
    fetchAccount: vi.fn(),
    renameAccount: vi.fn(),
    changePassword: vi.fn(),
    deleteAccount: vi.fn(),
    cancelWorkspaceSubscription: vi.fn(),
  };
});

const starter: Account = {
  name: "Tina", email: "tina@example.com", plan: "starter", created_at: 1_790_000_000, uploads_used: 3,
  uploads_limit: 10, has_subscription: false, plan_expires_at: null, has_password: true,
};
const pro: Account = { ...starter, plan: "pro", uploads_limit: null, has_subscription: true };
const trial: Account = { ...starter, name: "Free trial", email: null, has_password: false };

describe("AccountSettings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    localStorage.setItem("tenant_api_key", "old-key");
  });

  it("shows the account's profile and plan", async () => {
    vi.mocked(api.fetchAccount).mockResolvedValue(starter);
    render(<AccountSettings onWorkspaceChange={vi.fn()} />);

    expect(await screen.findByDisplayValue("Tina")).toBeInTheDocument();
    expect(screen.getByText("tina@example.com")).toBeInTheDocument();
    expect(screen.getByText("Starter (free)")).toBeInTheDocument();
    expect(screen.getByText("3 of 10")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Upgrade plan" })).toHaveAttribute("href", "#plans");
    expect(screen.queryByRole("button", { name: "Cancel subscription" })).not.toBeInTheDocument();
  });

  it("renames the workspace", async () => {
    vi.mocked(api.fetchAccount).mockResolvedValue(starter);
    vi.mocked(api.renameAccount).mockResolvedValue({ name: "Tina Co" });
    render(<AccountSettings onWorkspaceChange={vi.fn()} />);

    const input = await screen.findByDisplayValue("Tina");
    await userEvent.clear(input);
    await userEvent.type(input, "Tina Co");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(api.renameAccount).toHaveBeenCalledWith("Tina Co");
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
  });

  it("checks the new passwords match before changing", async () => {
    vi.mocked(api.fetchAccount).mockResolvedValue(starter);
    render(<AccountSettings onWorkspaceChange={vi.fn()} />);

    await userEvent.type(await screen.findByLabelText("Current password"), "Old-pass1!");
    await userEvent.type(screen.getByLabelText(/^New password/), "New-pass1!");
    await userEvent.type(screen.getByLabelText("Confirm new password"), "Different1!");
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("don't match");
    expect(api.changePassword).not.toHaveBeenCalled();
  });

  it("changes the password and keeps the new key", async () => {
    vi.mocked(api.fetchAccount).mockResolvedValue(starter);
    vi.mocked(api.changePassword).mockResolvedValue({ tenant_id: "t", name: "Tina", api_key: "new-key" });
    render(<AccountSettings onWorkspaceChange={vi.fn()} />);

    await userEvent.type(await screen.findByLabelText("Current password"), "Old-pass1!");
    await userEvent.type(screen.getByLabelText(/^New password/), "New-pass1!");
    await userEvent.type(screen.getByLabelText("Confirm new password"), "New-pass1!");
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));

    expect(api.changePassword).toHaveBeenCalledWith("Old-pass1!", "New-pass1!");
    expect(api.getTenantApiKey()).toBe("new-key");
    expect(await screen.findByText(/Password changed/)).toBeInTheDocument();
  });

  it("only deletes after the password and typing DELETE, then signs out", async () => {
    vi.mocked(api.fetchAccount).mockResolvedValue(pro);
    vi.mocked(api.deleteAccount).mockResolvedValue({ status: "deleted" });
    const onWorkspaceChange = vi.fn();
    render(<AccountSettings onWorkspaceChange={onWorkspaceChange} />);

    const button = await screen.findByRole("button", { name: "Delete my account" });
    expect(screen.getByText(/subscription will be cancelled straight away/)).toBeInTheDocument();
    expect(button).toBeDisabled();

    await userEvent.type(screen.getByLabelText("Your password"), "Old-pass1!");
    await userEvent.type(screen.getByLabelText(/to confirm/), "delete");
    expect(button).toBeDisabled();

    await userEvent.clear(screen.getByLabelText(/to confirm/));
    await userEvent.type(screen.getByLabelText(/to confirm/), "DELETE");
    await userEvent.click(button);

    expect(api.deleteAccount).toHaveBeenCalledWith("Old-pass1!");
    expect(api.getTenantApiKey()).toBeNull();
    expect(onWorkspaceChange).toHaveBeenCalled();
  });

  it("shows why deletion failed and keeps the workspace", async () => {
    vi.mocked(api.fetchAccount).mockResolvedValue(starter);
    vi.mocked(api.deleteAccount).mockRejectedValue(new Error("That password isn't correct."));
    const onWorkspaceChange = vi.fn();
    render(<AccountSettings onWorkspaceChange={onWorkspaceChange} />);

    await userEvent.type(await screen.findByLabelText("Your password"), "wrong");
    await userEvent.type(screen.getByLabelText(/to confirm/), "DELETE");
    await userEvent.click(screen.getByRole("button", { name: "Delete my account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("That password isn't correct.");
    expect(api.getTenantApiKey()).toBe("old-key");
    expect(onWorkspaceChange).not.toHaveBeenCalled();
  });

  it("lets a free-trial workspace delete without a password", async () => {
    vi.mocked(api.fetchAccount).mockResolvedValue(trial);
    vi.mocked(api.deleteAccount).mockResolvedValue({ status: "deleted" });
    render(<AccountSettings onWorkspaceChange={vi.fn()} />);

    expect(await screen.findByText(/has no login/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Your password")).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/to confirm/), "DELETE");
    await userEvent.click(screen.getByRole("button", { name: "Delete my account" }));

    expect(api.deleteAccount).toHaveBeenCalledWith(null);
  });
});
