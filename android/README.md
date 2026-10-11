# CRM Scoring for Android

A small Kotlin app that shows the hosted CRM Scoring web app
(https://ai-lead-generation-scoring.onrender.com/), like the Swift app in
`../CRMSCORING` does on iPhone, iPad and Mac. Outside links open in the
browser, the lead upload uses the system file picker, and the CSV export is
saved wherever the user picks (via the `CRMScoringAndroid` bridge that
`frontend/src/csvExport.ts` calls).

## Build

Open this folder in Android Studio, or from a terminal:

```sh
./gradlew assembleDebug        # app/build/outputs/apk/debug/app-debug.apk
./gradlew bundleRelease        # app/build/outputs/bundle/release/app-release.aab, for Google Play
```

## Publishing to Google Play

1. Create an upload key once (keep it safe and out of git):
   `keytool -genkey -v -keystore upload.jks -alias upload -keyalg RSA -keysize 2048 -validity 10000`
2. In Android Studio: **Build → Generate Signed App Bundle**, pick `upload.jks`.
3. Upload the `.aab` in the Play Console. `applicationId` (`com.crmscoring.app`
   in `app/build.gradle.kts`) can't change after the first upload.
