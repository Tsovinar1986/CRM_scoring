//
//  CRMSCORINGApp.swift
//  CRMSCORING
//
//  Created by Tsovinar Babakhanyan on 07.10.26.
//

import SwiftUI

@main
struct CRMSCORINGApp: App {
    var body: some Scene {
        WindowGroup {
            #if os(macOS)
            ContentView()
                .frame(minWidth: 900, minHeight: 640)
            #else
            ContentView()
            #endif
        }
        #if os(macOS)
        .defaultSize(width: 1200, height: 800)
        .windowResizability(.contentMinSize)
        #endif
    }
}
