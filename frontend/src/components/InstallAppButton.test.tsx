import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { InstallAppButton } from "./InstallAppButton";

function fireInstallPrompt() {
  const event = Object.assign(new Event("beforeinstallprompt"), {
    prompt: vi.fn().mockResolvedValue(undefined),
    userChoice: Promise.resolve({ outcome: "accepted" as const }),
  });
  act(() => {
    window.dispatchEvent(event);
  });
  return event;
}

describe("InstallAppButton", () => {
  it("stays hidden until the browser says the app can be installed", () => {
    const { container } = render(<InstallAppButton />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the browser's install prompt, then hides", async () => {
    render(<InstallAppButton />);
    const event = fireInstallPrompt();

    await userEvent.click(screen.getByRole("button", { name: "Install app" }));

    expect(event.prompt).toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Install app" })).not.toBeInTheDocument();
  });

  it("hides once the app is installed", () => {
    render(<InstallAppButton />);
    fireInstallPrompt();
    act(() => {
      window.dispatchEvent(new Event("appinstalled"));
    });
    expect(screen.queryByRole("button", { name: "Install app" })).not.toBeInTheDocument();
  });
});
