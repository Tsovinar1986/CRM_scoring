//
//  WebModel.swift
//  CRMSCORING
//

import SwiftUI
import UniformTypeIdentifiers
import WebKit
#if os(macOS)
import AppKit
#else
import UIKit
#endif

/// The hosted CRM Scoring service. Opening this URL directly takes the user
/// straight to the login / sign-up screen (with the subscription + free-trial
/// options), skipping the marketing landing page that the website shows.
let appURL = URL(string: "https://ai-lead-generation-scoring.onrender.com/")!

/// Same-host pages that are the public marketing / landing page rather than
/// the logged-in app. When the user logs out or swipes back onto one of these,
/// the app reloads the login screen (`appURL`) instead of stranding them on the
/// website's landing page.
///
/// If logout / back lands somewhere not listed here, run a debug build and read
/// the path shown at the bottom of the screen, then add it to this set.
let landingPaths: Set<String> = ["/home", "/landing", "/index.html", "/welcome", "/start"]

/// The marketing website (SITE_URL in frontend/src/api.ts). Logging out sends
/// the page to its home page ("https://crmscoring.com/#signed-out"), and the
/// logo links there too; in the app those show the login screen instead of
/// opening the browser. Other pages on it (terms, privacy) still open outside.
let siteHosts: Set<String> = ["crmscoring.com", "www.crmscoring.com"]

private func isWebsiteHome(_ url: URL) -> Bool {
    guard let host = url.host?.lowercased(), siteHosts.contains(host) else { return false }
    return url.path.isEmpty || url.path == "/" || url.path == "/index.html"
}

/// A JavaScript alert/confirm from the page, shown as a native alert.
struct PageDialog: Identifiable {
    let id = UUID()
    let message: String
    let isConfirm: Bool
    let respond: (Bool) -> Void
}

/// Owns the one `WKWebView` the app shows and everything a browser would
/// otherwise do for the page: opening outside links in the system browser,
/// alert/confirm dialogs, picking files to upload (Mac) and saving the CSV and
/// PowerPoint exports, which the web app hands over through the `saveFile` bridge.
@Observable
final class WebModel: NSObject {
    @ObservationIgnored let webView: WKWebView
    var isLoading = true
    var hasContent = false
    var errorMessage: String?
    var dialog: PageDialog?
    /// The web view's current URL, mirrored here so SwiftUI can show it in debug
    /// builds and so we can react when the user reaches the landing page.
    var currentURL: URL?
    @ObservationIgnored private var redirectingToLogin = false
    @ObservationIgnored private var urlObservation: NSKeyValueObservation?

    override init() {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        configuration.applicationNameForUserAgent = "CRMScoringApp/1.0"
        webView = WKWebView(frame: .zero, configuration: configuration)
        super.init()
        webView.configuration.userContentController.add(WeakScriptHandler(self), name: "saveFile")
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.allowsBackForwardNavigationGestures = true
        // Watch the URL so that logging out or swiping back onto the public
        // landing page bounces the user to the login screen.
        urlObservation = webView.observe(\.url, options: [.new]) { [weak self] webView, _ in
            guard let self else { return }
            self.currentURL = webView.url
            self.redirectToLoginIfOnLanding()
        }
        #if os(iOS)
        let refresh = UIRefreshControl()
        refresh.addAction(UIAction { [weak self] _ in self?.webView.reload() }, for: .valueChanged)
        webView.scrollView.refreshControl = refresh
        #endif
        load()
    }

    func load() {
        errorMessage = nil
        if hasContent {
            webView.reload()
        } else {
            webView.load(URLRequest(url: appURL))
        }
    }

    /// Bounces the user back to the login screen when they log out or swipe back
    /// onto the public landing page. A fresh load of `appURL` reliably shows the
    /// login screen, so we never loop on the pages we send them to.
    private func redirectToLoginIfOnLanding() {
        guard !redirectingToLogin,
              let url = webView.url,
              url.host?.lowercased() == appURL.host?.lowercased(),
              landingPaths.contains(url.path) else { return }
        redirectingToLogin = true
        webView.load(URLRequest(url: appURL))
    }

    /// Pages of the hosted app stay in the app; everything else (help links,
    /// email addresses, payment providers' own pages) opens outside it.
    private static func opensOutside(_ url: URL) -> Bool {
        switch url.scheme?.lowercased() {
        case "http", "https": return url.host?.lowercased() != appURL.host?.lowercased()
        case "mailto", "tel", "sms": return true
        default: return false // about:, blob:, data:, javascript:
        }
    }

    private func openExternally(_ url: URL) {
        #if os(macOS)
        NSWorkspace.shared.open(url)
        #else
        UIApplication.shared.open(url)
        #endif
    }

    private func finishLoading() {
        redirectingToLogin = false
        isLoading = false
        #if os(iOS)
        webView.scrollView.refreshControl?.endRefreshing()
        #endif
    }

    private func ask(_ message: String, isConfirm: Bool) async -> Bool {
        await withCheckedContinuation { continuation in
            dialog = PageDialog(message: message, isConfirm: isConfirm) { continuation.resume(returning: $0) }
        }
    }

    private func saveFile(named name: String, data: Data) {
        #if os(macOS)
        let panel = NSSavePanel()
        panel.nameFieldStringValue = name
        panel.allowedContentTypes = [UTType(filenameExtension: (name as NSString).pathExtension) ?? .data]
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            try data.write(to: url, options: .atomic)
        } catch {
            dialog = PageDialog(message: "Couldn't save \(name): \(error.localizedDescription)", isConfirm: false) { _ in }
        }
        #else
        // Write a temporary copy and offer the share sheet ("Save to Files", Mail, AirDrop…).
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(name)
        do {
            try data.write(to: url, options: .atomic)
        } catch {
            dialog = PageDialog(message: "Couldn't save \(name): \(error.localizedDescription)", isConfirm: false) { _ in }
            return
        }
        let sheet = UIActivityViewController(activityItems: [url], applicationActivities: nil)
        sheet.popoverPresentationController?.sourceView = webView
        sheet.popoverPresentationController?.sourceRect = CGRect(x: webView.bounds.midX, y: webView.bounds.midY, width: 0, height: 0)
        var presenter = webView.window?.rootViewController
        while let next = presenter?.presentedViewController { presenter = next }
        presenter?.present(sheet, animated: true)
        #endif
    }
}

extension WebModel: WKNavigationDelegate {
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction) async -> WKNavigationActionPolicy {
        // Only top-level navigations leave the app; embedded frames (e.g. the
        // card fields on the subscription form) load where they are.
        if let url = navigationAction.request.url,
           navigationAction.targetFrame?.isMainFrame != false,
           isWebsiteHome(url) {
            webView.load(URLRequest(url: appURL)) // logged out: back to the login screen
            return .cancel
        }
        if let url = navigationAction.request.url,
           navigationAction.targetFrame?.isMainFrame != false,
           Self.opensOutside(url) {
            openExternally(url)
            return .cancel
        }
        return .allow
    }

    func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
        isLoading = true
        errorMessage = nil
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        hasContent = true
        finishLoading()
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        finishLoading()
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        finishLoading()
        let error = error as NSError
        // Cancelled loads (a link we sent to the browser, a quick second tap) aren't failures.
        if error.domain == NSURLErrorDomain && error.code == NSURLErrorCancelled { return }
        if error.domain == WKError.errorDomain && error.code == 102 { return } // frame load interrupted
        errorMessage = error.localizedDescription
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        webView.reload()
    }
}

extension WebModel: WKUIDelegate {
    // Links with target="_blank" and window.open().
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = navigationAction.request.url {
            if Self.opensOutside(url) {
                openExternally(url)
            } else {
                webView.load(navigationAction.request)
            }
        }
        return nil
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo) async {
        _ = await ask(message, isConfirm: false)
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo) async -> Bool {
        await ask(message, isConfirm: true)
    }

    #if os(macOS)
    // The lead upload's file input. iOS and iPadOS show their own picker.
    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo) async -> [URL]? {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = parameters.allowsDirectories
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        return panel.runModal() == .OK ? panel.urls : nil
    }
    #endif
}

extension WebModel: WKScriptMessageHandler {
    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.frameInfo.securityOrigin.host == appURL.host,
              let body = message.body as? [String: Any] else { return }
        // Text files (the CSV) come as text, binary ones (the PowerPoint deck) as base64.
        let data: Data
        if let text = body["text"] as? String {
            data = Data(text.utf8)
        } else if let base64 = body["base64"] as? String, let decoded = Data(base64Encoded: base64) {
            data = decoded
        } else {
            return
        }
        // Keep only the file name, so the page can't pick where it's written.
        let requested = URL(fileURLWithPath: body["filename"] as? String ?? "").lastPathComponent
        saveFile(named: requested.isEmpty || requested == "/" ? "scored-leads.csv" : requested, data: data)
    }
}

/// `WKUserContentController` keeps its handlers alive; this breaks the cycle
/// between it and the model.
private final class WeakScriptHandler: NSObject, WKScriptMessageHandler {
    weak var target: WKScriptMessageHandler?

    init(_ target: WKScriptMessageHandler) {
        self.target = target
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        target?.userContentController(userContentController, didReceive: message)
    }
}
