import { afterEach, describe, expect, it, vi } from "vitest";
import { saveFile } from "./fileSave";

const win = window as unknown as Record<string, unknown>;
const deck = () => new Blob([new Uint8Array([80, 75, 3, 4])]);

describe("saveFile for binary files in the native apps", () => {
  afterEach(() => {
    delete win.webkit;
    delete win.CRMScoringAndroid;
  });

  it("hands the iOS/macOS app the file as base64", async () => {
    const postMessage = vi.fn();
    win.webkit = { messageHandlers: { saveFile: { postMessage } } };
    await saveFile("overview.pptx", deck(), "application/x-test");
    expect(postMessage).toHaveBeenCalledWith({ filename: "overview.pptx", base64: "UEsDBA==" });
  });

  it("hands the Android app the file as base64 with its type", async () => {
    const saveBase64File = vi.fn();
    win.CRMScoringAndroid = { saveFile: vi.fn(), saveBase64File };
    await saveFile("overview.pptx", deck(), "application/x-test");
    expect(saveBase64File).toHaveBeenCalledWith("overview.pptx", "UEsDBA==", "application/x-test");
  });
});
