package com.crmscoring.app

import android.annotation.SuppressLint
import android.content.ActivityNotFoundException
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import android.os.Bundle
import android.util.Base64
import android.view.Gravity
import android.view.View
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat

/** The hosted CRM Scoring service; opening it lands on login / sign-up. */
private val APP_URL: Uri = Uri.parse("https://ai-lead-generation-scoring.onrender.com/")

private const val PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

/**
 * The marketing website (SITE_URL in frontend/src/api.ts). Logging out sends the
 * page to its home page, and the logo links there; in the app those show the
 * login screen instead. Other pages on it (terms, privacy) open in the browser.
 */
private val SITE_HOSTS = setOf("crmscoring.com", "www.crmscoring.com")

private fun isWebsiteHome(url: Uri): Boolean =
    url.host?.lowercase() in SITE_HOSTS && (url.path.isNullOrEmpty() || url.path == "/" || url.path == "/index.html")

/**
 * Shows the hosted CRM Scoring web app and does what a browser would for it:
 * outside links open in the browser, the lead upload gets the system file
 * picker, and the CSV and PowerPoint exports (handed over through the
 * `CRMScoringAndroid` bridge) are saved wherever the user picks.
 */
class MainActivity : ComponentActivity() {
    private lateinit var webView: WebView
    private lateinit var loading: View
    private lateinit var offline: View
    private lateinit var offlineMessage: TextView
    private var hasContent = false

    private var pendingUpload: ValueCallback<Array<Uri>>? = null
    private val pickUpload = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        pendingUpload?.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(result.resultCode, result.data))
        pendingUpload = null
    }

    private var pendingSave: ByteArray? = null
    private fun writePendingSave(uri: Uri?) {
        val bytes = pendingSave
        pendingSave = null
        if (uri == null || bytes == null) return
        try {
            contentResolver.openOutputStream(uri)?.use { it.write(bytes) }
        } catch (e: Exception) {
            Toast.makeText(this, R.string.save_failed, Toast.LENGTH_LONG).show()
        }
    }
    // The system picker needs the file type up front: one picker per type the
    // web app saves (the CSV export, the PowerPoint overview).
    private val pickCsvLocation = registerForActivityResult(ActivityResultContracts.CreateDocument("text/csv")) { writePendingSave(it) }
    private val pickPptxLocation = registerForActivityResult(ActivityResultContracts.CreateDocument(PPTX_MIME)) { writePendingSave(it) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(buildLayout())
        configureWebView()

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (webView.canGoBack()) {
                    webView.goBack()
                } else {
                    isEnabled = false
                    onBackPressedDispatcher.onBackPressed()
                }
            }
        })

        if (savedInstanceState == null || webView.restoreState(savedInstanceState) == null) {
            webView.loadUrl(APP_URL.toString())
        }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        webView.saveState(outState)
    }

    override fun onPause() {
        super.onPause()
        CookieManager.getInstance().flush() // keep the user signed in
    }

    private fun buildLayout(): View {
        val density = resources.displayMetrics.density
        val pad = (24 * density).toInt()
        webView = WebView(this)
        loading = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            addView(ProgressBar(this@MainActivity))
            addView(TextView(this@MainActivity).apply {
                setText(R.string.starting)
                gravity = Gravity.CENTER
                setPadding(pad, pad / 2, pad, 0)
            })
        }
        offlineMessage = TextView(this).apply { gravity = Gravity.CENTER; setPadding(0, pad / 2, 0, pad / 2) }
        offline = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(pad, pad, pad, pad)
            setBackgroundColor(getColor(R.color.paper))
            visibility = View.GONE
            addView(TextView(this@MainActivity).apply {
                setText(R.string.offline_title)
                textSize = 20f
                gravity = Gravity.CENTER
            })
            addView(offlineMessage)
            addView(Button(this@MainActivity).apply {
                setText(R.string.try_again)
                setOnClickListener { retry() }
            })
        }
        val root = FrameLayout(this).apply {
            addView(webView)
            addView(loading)
            addView(offline)
        }
        // Android 15+ draws apps edge to edge; keep the page clear of the status and navigation bars.
        ViewCompat.setOnApplyWindowInsetsListener(root) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            WindowInsetsCompat.CONSUMED
        }
        return root
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun configureWebView() {
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            userAgentString = "$userAgentString CRMScoringApp/1.0"
        }
        CookieManager.getInstance().setAcceptCookie(true)
        webView.addJavascriptInterface(NativeBridge(), "CRMScoringAndroid")

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                if (!request.isForMainFrame) return false
                if (isWebsiteHome(request.url)) {
                    view.loadUrl(APP_URL.toString()) // logged out: back to the login screen
                    return true
                }
                if (!opensOutside(request.url)) return false
                openExternally(request.url)
                return true
            }

            override fun onPageStarted(view: WebView, url: String?, favicon: Bitmap?) {
                offline.visibility = View.GONE
            }

            override fun onPageFinished(view: WebView, url: String?) {
                if (offline.visibility != View.VISIBLE) hasContent = true
                loading.visibility = View.GONE
            }

            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (!request.isForMainFrame) return
                offlineMessage.text = error.description
                offline.visibility = View.VISIBLE
                loading.visibility = View.GONE
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            // The lead upload's file input. (alert/confirm use WebChromeClient's own dialogs.)
            override fun onShowFileChooser(
                view: WebView,
                callback: ValueCallback<Array<Uri>>,
                params: FileChooserParams,
            ): Boolean {
                pendingUpload?.onReceiveValue(null)
                pendingUpload = callback
                return try {
                    pickUpload.launch(params.createIntent())
                    true
                } catch (e: ActivityNotFoundException) {
                    pendingUpload = null
                    false
                }
            }
        }
    }

    private fun retry() {
        offline.visibility = View.GONE
        loading.visibility = if (hasContent) View.GONE else View.VISIBLE
        if (hasContent) webView.reload() else webView.loadUrl(APP_URL.toString())
    }

    /** Pages of the hosted app stay in the app; everything else opens outside it. */
    private fun opensOutside(url: Uri): Boolean = when (url.scheme?.lowercase()) {
        "http", "https" -> !url.host.equals(APP_URL.host, ignoreCase = true)
        "mailto", "tel", "sms" -> true
        else -> false // about:, blob:, data:, javascript:
    }

    private fun openExternally(url: Uri) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, url))
        } catch (e: ActivityNotFoundException) {
            // Nothing on the device can open it; stay on the page.
        }
    }

    /** Called from the web app's file saves (frontend/src/fileSave.ts). */
    inner class NativeBridge {
        @JavascriptInterface
        fun saveFile(filename: String, text: String) {
            save(filename, text.toByteArray(), "text/csv")
        }

        @JavascriptInterface
        fun saveBase64File(filename: String, base64: String, mimeType: String) {
            val bytes = try {
                Base64.decode(base64, Base64.DEFAULT)
            } catch (e: IllegalArgumentException) {
                return
            }
            save(filename, bytes, mimeType)
        }

        private fun save(filename: String, bytes: ByteArray, mimeType: String) {
            runOnUiThread {
                // Only while the hosted app itself is showing.
                if (Uri.parse(webView.url ?: "").host != APP_URL.host) return@runOnUiThread
                pendingSave = bytes
                // Keep only the file name; the user picks where it goes.
                val name = filename.substringAfterLast('/').ifBlank { "scored-leads.csv" }
                if (mimeType == PPTX_MIME) pickPptxLocation.launch(name) else pickCsvLocation.launch(name)
            }
        }
    }
}
