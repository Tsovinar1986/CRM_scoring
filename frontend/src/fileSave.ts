// Saves a file the web app made (the CSV export, the PowerPoint deck).
//
// The native iOS/macOS and Android apps show this web app in a web view, where
// blob downloads go nowhere; each app exposes a bridge that saves the file.
// Text goes over as-is; binary files go over as base64.
interface NativeBridges {
  webkit?: {
    messageHandlers?: {
      saveFile?: { postMessage: (msg: { filename: string; text?: string; base64?: string }) => void };
    };
  };
  CRMScoringAndroid?: {
    saveFile: (filename: string, text: string) => void;
    saveBase64File?: (filename: string, base64: string, mimeType: string) => void;
  };
}

async function toBase64(blob: Blob): Promise<string> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary);
}

export async function saveFile(filename: string, data: string | Blob, mimeType: string): Promise<void> {
  const native = window as unknown as NativeBridges;
  const apple = native.webkit?.messageHandlers?.saveFile;
  const android = native.CRMScoringAndroid;
  if (typeof data === "string") {
    if (apple) return apple.postMessage({ filename, text: data });
    if (android) return android.saveFile(filename, data);
  } else {
    if (apple) return apple.postMessage({ filename, base64: await toBase64(data) });
    if (android?.saveBase64File) return android.saveBase64File(filename, await toBase64(data), mimeType);
  }
  const blob = typeof data === "string" ? new Blob([data], { type: `${mimeType};charset=utf-8;` }) : data;
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
