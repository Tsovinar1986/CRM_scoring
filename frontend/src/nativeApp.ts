// The iOS/macOS and Android apps add "CRMScoringApp" to their user agent.
// App Store and Google Play require their own billing for subscriptions sold
// inside an app, so the apps don't sell plans: buy buttons and upgrade prompts
// are left out there, and people subscribe on the website.
export function isNativeApp(): boolean {
  return typeof navigator !== "undefined" && navigator.userAgent.includes("CRMScoringApp");
}
