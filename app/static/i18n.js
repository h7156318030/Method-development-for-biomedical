/* MethodFlow i18n runtime (Chinese source UI -> English).
 * The interface text is written in Chinese in the JS files.  In English mode this layer translates the DOM:
 * text nodes and the attributes placeholder / title / aria-label / alt, both for what is already on the page and for
 * everything added later (MutationObserver).  The table MF_I18N_EN comes from i18n_en.js (generated during
 * development) and has three parts:
 *   exact  whole-string translations
 *   pat    [regex source, replacement] for backend messages with %s / %d placeholders
 *   frag   fragments of strings that are concatenated with variables
 * Language: localStorage "mf_lang" ("zh" | "en"); default = browser language (zh* -> zh, otherwise en).
 * Content written by users (and template content that is not translated yet) stays as it is. */
(function () {
  'use strict';
  var CJK = /[一-鿿]/;
  var lang = 'zh';
  try {
    var saved = window.localStorage.getItem('mf_lang');
    if (saved === 'zh' || saved === 'en') lang = saved;
    else lang = /^zh/i.test(navigator.language || '') ? 'zh' : 'en';
  } catch (e) { lang = /^zh/i.test(navigator.language || '') ? 'zh' : 'en'; }

  var MF = window.MF = window.MF || {};
  MF.lang = lang;

  function setLang(l) {
    try { window.localStorage.setItem('mf_lang', l); } catch (e) { /* ignore */ }
    window.location.reload();
  }
  MF.setLang = setLang;

  var T = window.MF_I18N_EN || { exact: {}, pat: [], frag: [] };
  var EXACT = T.exact || {};
  var PATS = (T.pat || []).map(function (p) { return [new RegExp(p[0]), p[1]]; });
  // generated English of template labels / options / help texts
  var TPL = window.MF_I18N_TPL || {};
  Object.keys(TPL.exact || {}).forEach(function (k) { EXACT[k] = TPL.exact[k]; });
  // hand-maintained additions (i18n_extra_en.js): same shape, merged on top of the generated table
  var X = window.MF_I18N_EXTRA || {};
  Object.keys(X.exact || {}).forEach(function (k) { EXACT[k] = X.exact[k]; });
  (X.pat || []).forEach(function (p) { PATS.unshift([new RegExp(p[0]), p[1]]); });
  // status words that are also button labels: inside a badge they are statuses
  var BADGE = { '取消': 'Cancelled', '归档': 'Archived', '暂停': 'Paused', '停用': 'Retired', '逾期': 'overdue', '复核': 'Review', '关闭': 'Closed' };
  var FRAG_RE = null, FRAG_MAP = null;

  function esc(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
  function buildFrag() {
    FRAG_MAP = {};
    var keys = [];
    (T.frag || []).forEach(function (f) {
      var k = f[0];
      if (!FRAG_MAP.hasOwnProperty(k)) { FRAG_MAP[k] = f[1]; keys.push(k); }
    });
    Object.keys(EXACT).forEach(function (k) {
      if (k.length >= 2 && CJK.test(k) && !FRAG_MAP.hasOwnProperty(k)) { FRAG_MAP[k] = EXACT[k]; keys.push(k); }
    });
    keys.sort(function (a, b) { return b.length - a.length; });
    FRAG_RE = new RegExp(keys.map(esc).join('|'), 'g');
  }

  function split(s) {
    var m = /^(\s*)([\s\S]*?)(\s*)$/.exec(s);
    return [m[1], m[2], m[3]];
  }

  function translate(s, inBadge) {
    if (!s || !CJK.test(s)) return s;
    var parts = split(s), core = parts[1];
    if (!core) return s;
    if (inBadge && BADGE.hasOwnProperty(core)) return parts[0] + BADGE[core] + parts[2];
    if (EXACT.hasOwnProperty(core)) return parts[0] + EXACT[core] + parts[2];
    for (var i = 0; i < PATS.length; i++) {
      var m = PATS[i][0].exec(core);
      if (m) {
        var out = PATS[i][1].replace(/\$(\d)/g, function (_, n) { return translate(m[+n] || '', false); });
        return parts[0] + out + parts[2];
      }
    }
    // composed strings: translate the known fragments, but only when that leaves no Chinese behind.
    // Half-translated text ("items目") is worse than none, and user-written names (project, method, template body)
    // that happen to contain dictionary words must stay as written.
    if (!FRAG_RE) buildFrag();
    var res = s.replace(FRAG_RE, function (k) { return FRAG_MAP[k]; });
    return CJK.test(res) ? s : res;
  }
  MF.t = function (zh) { return lang === 'en' ? translate(String(zh), false) : zh; };

  if (lang !== 'en') {
    // Chinese: only the language switch is added
    document.documentElement.lang = 'zh-CN';
  } else {
    document.documentElement.lang = 'en';
    var SKIP = { SCRIPT: 1, STYLE: 1, TEXTAREA: 1, NOSCRIPT: 1, CODE: 0 };
    var ATTRS = ['placeholder', 'title', 'aria-label', 'alt'];

    var inBadge = function (node) {
      var p = node.parentElement;
      return !!(p && p.closest && p.closest('.badge'));
    };
    var fixText = function (n) {
      var v = n.nodeValue;
      if (!v || !CJK.test(v)) return;
      var p = n.parentElement;
      if (p && (SKIP[p.tagName] || (p.closest && p.closest('[data-notranslate]')))) return;
      var t = translate(v, inBadge(n));
      if (t !== v) n.nodeValue = t;
    };
    var fixAttrs = function (el) {
      for (var i = 0; i < ATTRS.length; i++) {
        var a = ATTRS[i], v = el.getAttribute && el.getAttribute(a);
        if (v && CJK.test(v)) {
          var t = translate(v, false);
          if (t !== v) el.setAttribute(a, t);
        }
      }
    };
    var walk = function (node) {
      if (node.nodeType === 3) { fixText(node); return; }
      if (node.nodeType !== 1) return;
      if (SKIP[node.tagName]) { if (node.tagName === 'TEXTAREA') fixAttrs(node); return; }   // placeholders of textareas are UI text
      if (node.hasAttribute && node.hasAttribute('data-notranslate')) return;
      fixAttrs(node);
      for (var c = node.firstChild; c; c = c.nextSibling) walk(c);
    };
    var obs = new MutationObserver(function (muts) {
      obs.disconnect();
      try {
        muts.forEach(function (m) {
          if (m.type === 'childList') m.addedNodes.forEach(walk);
          else if (m.type === 'characterData') fixText(m.target);
          else if (m.type === 'attributes') fixAttrs(m.target);
        });
      } finally { start(); }
    });
    var start = function () {
      obs.observe(document.documentElement, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRS });
    };
    walk(document.documentElement);
    start();
    window.addEventListener('DOMContentLoaded', function () { walk(document.documentElement); });
  }

  // language switch (fixed, bottom-right; present on every page including the login page)
  function addSwitch() {
    if (document.getElementById('mf-lang-switch')) return;
    var box = document.createElement('div');
    box.id = 'mf-lang-switch';
    box.setAttribute('data-notranslate', '');
    box.style.cssText = 'position:fixed;right:10px;bottom:10px;z-index:50;display:flex;gap:2px;background:var(--c-card,#fff);border:1px solid var(--c-border,#d0d7de);border-radius:14px;padding:2px;font-size:12px;opacity:.85';
    [['zh', '中文'], ['en', 'EN']].forEach(function (x) {
      var b = document.createElement('button');
      b.type = 'button';
      b.textContent = x[1];
      b.setAttribute('aria-label', x[0] === 'zh' ? '中文' : 'English');
      b.style.cssText = 'border:0;border-radius:12px;padding:2px 9px;cursor:pointer;background:' + (lang === x[0] ? 'var(--c-primary,#1d5fb8)' : 'transparent') + ';color:' + (lang === x[0] ? '#fff' : 'inherit');
      b.addEventListener('click', function () { if (lang !== x[0]) setLang(x[0]); });
      box.appendChild(b);
    });
    document.body.appendChild(box);
  }
  if (document.body) addSwitch(); else window.addEventListener('DOMContentLoaded', addSwitch);
})();
