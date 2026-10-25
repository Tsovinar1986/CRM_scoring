/* English / Russian / Armenian for the site's secondary pages (terms,
 * privacy, refunds, guardrails, login, thank-you). index.html has the same
 * logic inline. Same storage key as index.html and the app, so a choice made
 * on one page holds on every page.
 *
 * A page can define window.PAGE_I18N = { en: {...}, ru: {...}, hy: {...} }
 * before loading this script. Then:
 *   data-i18n="key"             -> textContent
 *   data-i18n-html="key"        -> innerHTML (our own trusted strings only)
 *   data-i18n-placeholder="key" -> placeholder
 *   data-lang-block="ru"        -> shown only in that language (long texts)
 *   [data-lang-switch]          -> gets the EN · RU · ՀՅ pill
 * Scripts use window.crmLang.t(key, vars), .lang, .withLang(url), .onChange(fn).
 */
(function () {
  var COMMON = {
    en: {
      "nav.language": "Language",
      "footer.home": "Home",
      "footer.terms": "Terms",
      "footer.privacy": "Privacy",
      "footer.refunds": "Refunds",
      "footer.guardrails": "AI Guardrails"
    },
    ru: {
      "nav.language": "Язык",
      "footer.home": "Главная",
      "footer.terms": "Условия",
      "footer.privacy": "Конфиденциальность",
      "footer.refunds": "Возвраты",
      "footer.guardrails": "Принципы ИИ"
    },
    hy: {
      "nav.language": "Լեզու",
      "footer.home": "Գլխավոր",
      "footer.terms": "Պայմաններ",
      "footer.privacy": "Գաղտնիություն",
      "footer.refunds": "Փոխհատուցում",
      "footer.guardrails": "AI սկզբունքներ"
    }
  };
  var LANGS = [["en", "EN", "English"], ["ru", "RU", "Русский"], ["hy", "ՀՅ", "Հայերեն"]];
  var KEY = "crmscoring_lang";
  var page = window.PAGE_I18N || {};
  var listeners = [];

  function valid(l) { return l === "en" || l === "ru" || l === "hy"; }
  var lang = (function () {
    var asked = new URLSearchParams(location.search).get("lang");
    var saved = null;
    try { saved = localStorage.getItem(KEY); } catch (e) {}
    var browser = (navigator.language || "en").slice(0, 2).toLowerCase();
    return [asked, saved, browser].filter(valid)[0] || "en";
  })();

  function t(key, vars) {
    var text = (page[lang] || {})[key] || COMMON[lang][key] || (page.en || {})[key] || COMMON.en[key];
    if (text == null) return null;
    if (vars) Object.keys(vars).forEach(function (n) { text = text.split("{" + n + "}").join(vars[n]); });
    return text;
  }

  function each(selector, fn) { Array.prototype.forEach.call(document.querySelectorAll(selector), fn); }

  function apply() {
    document.documentElement.lang = lang;
    each("[data-i18n]", function (el) { var v = t(el.getAttribute("data-i18n")); if (v != null) el.textContent = v; });
    each("[data-i18n-html]", function (el) { var v = t(el.getAttribute("data-i18n-html")); if (v != null) el.innerHTML = v; });
    each("[data-i18n-placeholder]", function (el) { var v = t(el.getAttribute("data-i18n-placeholder")); if (v != null) el.placeholder = v; });
    each("[data-lang-block]", function (el) { el.hidden = el.getAttribute("data-lang-block") !== lang; });
    each("[data-lang-switch] button", function (b) { b.setAttribute("aria-pressed", String(b.getAttribute("data-lang") === lang)); });
    each("[data-lang-switch]", function (el) { el.setAttribute("aria-label", t("nav.language")); });
    listeners.forEach(function (fn) { fn(lang); });
  }

  function set(next) {
    if (!valid(next)) return;
    lang = next;
    try { localStorage.setItem(KEY, next); } catch (e) {}
    apply();
  }

  // The pill, styled with the page's own tokens (same look as index.html).
  var style = document.createElement("style");
  style.textContent =
    ".lang-switch{display:inline-flex;padding:3px;border:1px solid var(--border);border-radius:999px;background:var(--bg-alt,var(--bg))}" +
    ".lang-switch button{font:inherit;font-size:.82rem;font-weight:500;line-height:1;min-width:40px;padding:7px 11px;border:0;border-radius:999px;background:transparent;color:var(--text-muted);cursor:pointer;transition:background .15s,color .15s}" +
    ".lang-switch button:hover{color:var(--text-h)}" +
    ".lang-switch button[aria-pressed=true]{background:var(--text-h);color:var(--bg)}" +
    ".lang-switch button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}";
  document.head.appendChild(style);
  each("[data-lang-switch]", function (el) {
    el.classList.add("lang-switch");
    el.setAttribute("role", "group");
    LANGS.forEach(function (l) {
      var b = document.createElement("button");
      b.type = "button";
      b.setAttribute("data-lang", l[0]);
      b.lang = l[0];
      b.title = l[2];
      b.textContent = l[1];
      b.addEventListener("click", function () { set(l[0]); });
      el.appendChild(b);
    });
  });

  window.crmLang = {
    get lang() { return lang; },
    t: t,
    set: set,
    onChange: function (fn) { listeners.push(fn); },
    // The app is on another origin: pass the language along.
    withLang: function (url) {
      var hash = url.indexOf("#") >= 0 ? url.slice(url.indexOf("#")) : "";
      var base = hash ? url.slice(0, url.indexOf("#")) : url;
      return base + (base.indexOf("?") < 0 ? "?" : "&") + "lang=" + lang + hash;
    }
  };
  apply();
})();
