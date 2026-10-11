//
//  ContentView.swift
//  CRMSCORING
//
//  Created by Tsovinar Babakhanyan on 07.10.26.
//

import SwiftUI
import WebKit

struct ContentView: View {
    @State private var model = WebModel()

    var body: some View {
        WebView(webView: model.webView)
            .ignoresSafeArea(.container, edges: .bottom)
            .overlay {
                if let message = model.errorMessage {
                    ContentUnavailableView {
                        Label("Can't reach CRM Scoring", systemImage: "wifi.exclamationmark")
                    } description: {
                        Text(message)
                    } actions: {
                        Button("Try again") { model.load() }
                            .buttonStyle(.borderedProminent)
                    }
                    .background(.background)
                } else if model.isLoading && !model.hasContent {
                    // The hosted server sleeps when idle, so the first load can take a while.
                    VStack(spacing: 12) {
                        ProgressView().controlSize(.large)
                        Text("Starting CRM Scoring…")
                        Text("The first load can take up to a minute.")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                    .padding(24)
                    .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12))
                }
            }
            .alert(
                "CRM Scoring",
                isPresented: Binding(get: { model.dialog != nil }, set: { if !$0 { model.dialog = nil } }),
                presenting: model.dialog
            ) { dialog in
                if dialog.isConfirm {
                    Button("Cancel", role: .cancel) { dialog.respond(false) }
                    Button("OK") { dialog.respond(true) }
                } else {
                    Button("OK") { dialog.respond(true) }
                }
            } message: { dialog in
                Text(dialog.message)
            }
    }
}

/// Shows the model's `WKWebView`, shared across platforms so the same login /
/// subscription experience runs on Mac, iPad and iPhone.
struct WebView {
    let webView: WKWebView
}

#if os(macOS)
extension WebView: NSViewRepresentable {
    func makeNSView(context: Context) -> WKWebView { webView }
    func updateNSView(_ nsView: WKWebView, context: Context) {}
}
#else
extension WebView: UIViewRepresentable {
    func makeUIView(context: Context) -> WKWebView { webView }
    func updateUIView(_ uiView: WKWebView, context: Context) {}
}
#endif

#Preview {
    ContentView()
}
