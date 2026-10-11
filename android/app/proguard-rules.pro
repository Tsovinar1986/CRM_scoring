# The web app calls these through the CRMScoringAndroid JavaScript bridge.
-keepclassmembers class com.crmscoring.app.MainActivity$NativeBridge {
    @android.webkit.JavascriptInterface <methods>;
}
