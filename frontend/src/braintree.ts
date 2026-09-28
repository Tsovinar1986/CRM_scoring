// Just the slice of Braintree's Drop-in UI
// (https://developer.braintreepayments.com/guides/drop-in/overview/javascript/v3)
// this app uses: the hosted card form, tokenized into a one-time nonce.
export interface DropinPaymentMethod {
  nonce: string;
  deviceData?: string;
}

export interface DropinInstance {
  requestPaymentMethod(): Promise<DropinPaymentMethod>;
  teardown(): Promise<void>;
}

export interface DropinCreateOptions {
  authorization: string;
  container: HTMLElement;
  card?: { cardholderName?: { required: boolean } };
  dataCollector?: boolean;
}

export interface DropinNamespace {
  create(options: DropinCreateOptions): Promise<DropinInstance>;
}

declare global {
  interface Window {
    braintree?: { dropin?: DropinNamespace };
  }
}

export const DROPIN_VERSION = "1.48.0";

let sdkPromise: Promise<DropinNamespace> | null = null;

// Loads Drop-in once per page.
export function loadDropin(): Promise<DropinNamespace> {
  if (sdkPromise) return sdkPromise;
  sdkPromise = new Promise<DropinNamespace>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = `https://js.braintreegateway.com/web/dropin/${DROPIN_VERSION}/js/dropin.min.js`;
    script.async = true;
    script.onload = () => {
      const dropin = window.braintree?.dropin;
      if (dropin) resolve(dropin);
      else reject(new Error("The payment form failed to load."));
    };
    script.onerror = () => reject(new Error("Couldn't load the payment form. Check your connection or ad blocker."));
    document.head.appendChild(script);
  }).catch((err) => {
    sdkPromise = null; // allow a retry
    throw err;
  });
  return sdkPromise;
}
