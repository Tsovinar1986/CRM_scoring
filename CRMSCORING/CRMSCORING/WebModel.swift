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

/// A JavaScript alert/confirm from the page, shown as a native alert.
struct PageDialog: Identifiable {
    let id = UUID()
    let message: String
    let isConfirm: Bool
    let respond: (Bool) -> Void
}

/// Owns the one `WKWebView` the app shows and everything a browser would
/// otherwise do for the page: opening outside links in the system browser,
/// alert/confirm dialogs, picking files to upload (Mac) and saving the CSV
/// export, which the web app hands over through the `saveFile` bridge.
@Observable
final class WebModel: NSObject {
    @ObservationIgnored let webView: WKWebView
    var isLoading = true
    var hasContent = false
    var errorMessage: String?
    var dialog: PageDialog?

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

    private func saveFile(named name: String, text: String) {
        #if os(macOS)
        let panel = NSSavePanel()
        panel.nameFieldStringValue = name
        panel.allowedContentTypes = [.commaSeparatedText]
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            try text.write(to: url, atomically: true, encoding: .utf8)
        } catch {
            dialog = PageDialog(message: "Couldn't save \(name): \(error.localizedDescription)", isConfirm: false) { _ in }
        }
        #else
        // Write a temporary copy and offer the share sheet ("Save to Files", Mail, AirDrop…).
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(name)
        do {
            try text.write(to: url, atomically: true, encoding: .utf8)
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
              let body = message.body as? [String: Any],
              let text = body["text"] as? String else { return }
        // Keep only the file name, so the page can't pick where it's written.
        let requested = URL(fileURLWithPath: body["filename"] as? String ?? "").lastPathComponent
        saveFile(named: requested.isEmpty || requested == "/" ? "scored-leads.csv" : requested, text: text)
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
