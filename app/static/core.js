/* MethodFlow core: DOM helpers, API, dialogs, router, layout shell, login.
   Provides window.MF as specified in docs/前端契约.md. */
(function () {
  'use strict';
  var MF = window.MF = window.MF || {};
  MF.state = { user: null, app: null };

  /* ------------------------------------------------------------------ DOM */
  function isAttrs(a) {
    return a !== null && typeof a === 'object' && !(a instanceof Node) && !Array.isArray(a);
  }

  function appendChild(parent, c) {
    if (c === null || c === undefined || c === false || c === true) return;
    if (Array.isArray(c)) { for (var i = 0; i < c.length; i++) appendChild(parent, c[i]); return; }
    if (c instanceof Node) { parent.appendChild(c); return; }
    if (typeof c === 'number') { if (isFinite(c)) parent.appendChild(document.createTextNode(String(c))); return; }
    parent.appendChild(document.createTextNode(String(c)));
  }

  MF.h = function (tag, attrs) {
    var el = document.createElement(tag);
    var start = 1, deferred = null;
    if (attrs === null || attrs === undefined) start = 2;
    else if (isAttrs(attrs)) {
      start = 2;
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v === null || v === undefined || v === false) return;
        if (k === 'class' || k === 'className') { el.className = String(v); return; }
        if (k === 'style') {
          if (typeof v === 'string') el.style.cssText = v;
          else Object.keys(v).forEach(function (s) { if (v[s] !== null && v[s] !== undefined) el.style[s] = v[s]; });
          return;
        }
        if (k === 'dataset') { Object.keys(v).forEach(function (d) { if (v[d] !== null && v[d] !== undefined) el.dataset[d] = String(v[d]); }); return; }
        if (k.slice(0, 2) === 'on' && typeof v === 'function') { el.addEventListener(k.slice(2).toLowerCase(), v); return; }
        if (k === 'value') { deferred = v; return; }
        if (k === 'checked' || k === 'disabled' || k === 'selected' || k === 'indeterminate' || k === 'hidden' || k === 'readOnly') { el[k] = !!v; return; }
        if (k === 'for') { el.setAttribute('for', String(v)); return; }
        if (v === true) { el.setAttribute(k, ''); return; }
        el.setAttribute(k, String(v));
      });
    }
    for (var i = start; i < arguments.length; i++) appendChild(el, arguments[i]);
    if (deferred !== null) el.value = deferred;
    return el;
  };
  var h = MF.h;

  MF.clear = function (node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
    return node;
  };

  MF.qs = function (obj) {
    var parts = [];
    Object.keys(obj || {}).forEach(function (k) {
      var v = obj[k];
      if (v === null || v === undefined || v === '') return;
      parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(v));
    });
    return parts.length ? '?' + parts.join('&') : '';
  };

  /* ------------------------------------------------------------------ formatting */
  function parseTime(s) {
    if (s === null || s === undefined || s === '') return null;
    var str = String(s);
    var d;
    if (/^\d{4}-\d{2}-\d{2}$/.test(str)) return null;
    if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(str)) return { raw: str.slice(0, 16) };
    if (/^\d{4}-\d{2}-\d{2}T/.test(str) && !/(Z|[+-]\d{2}:?\d{2})$/.test(str)) str += 'Z';
    d = new Date(str);
    if (isNaN(d.getTime())) return null;
    return { d: d };
  }
  function p2(n) { return (n < 10 ? '0' : '') + n; }
  MF.fmt = {
    date: function (s) {
      if (s === null || s === undefined || s === '') return '—';
      var str = String(s);
      if (/^\d{4}-\d{2}-\d{2}$/.test(str)) return str;
      var t = parseTime(str);
      if (!t) return /^\d{4}-\d{2}-\d{2}/.test(str) ? str.slice(0, 10) : '—';
      if (t.raw) return t.raw.slice(0, 10);
      return t.d.getFullYear() + '-' + p2(t.d.getMonth() + 1) + '-' + p2(t.d.getDate());
    },
    datetime: function (s) {
      if (s === null || s === undefined || s === '') return '—';
      var t = parseTime(s);
      if (!t) return /^\d{4}-\d{2}-\d{2}$/.test(String(s)) ? String(s) : '—';
      if (t.raw) return t.raw;
      var d = t.d;
      return d.getFullYear() + '-' + p2(d.getMonth() + 1) + '-' + p2(d.getDate()) + ' ' + p2(d.getHours()) + ':' + p2(d.getMinutes());
    },
    pct: function (n) {
      n = Number(n);
      if (!isFinite(n)) n = 0;
      return Math.round(n) + '%';
    },
    esc: function (s) {
      if (s === null || s === undefined) return '';
      return String(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; });
    },
    size: function (n) {
      n = Number(n);
      if (!isFinite(n) || n < 0) return '—';
      if (n < 1024) return n + ' B';
      if (n < 1048576) return (n / 1024).toFixed(1) + ' KB';
      return (n / 1048576).toFixed(1) + ' MB';
    }
  };

  var STATUS_LABELS = { not_started: '未开始', in_progress: '进行中', in_review: '待复核', returned: '已退回', approved: '已通过', completed: '已完成' };
  var STATUS_KIND = { approved: 'ok', completed: 'ok', in_review: 'info', returned: 'err', in_progress: 'warn', not_started: 'muted' };
  var ROLE_LABELS = { admin: '管理员', author: '开发人员', reviewer: '复核人', approver: '批准人(QA)', viewer: '只读', owner: '负责人', member: '项目成员', stale: '已失效' };
  var PROJECT_ROLE_LABELS = { owner: '项目负责人', member: '项目成员', viewer: '只读' };
  var METHOD_ROLE_LABELS = { owner: '方法负责人', author: '开发人员', reviewer: '复核人', approver: '批准人(QA)', viewer: '只读' };
  var PROJECT_STATUS = { active: ['进行中', 'info'], paused: ['暂停', 'warn'], completed: ['完成', 'ok'], archived: ['归档', 'muted'] };
  var METHOD_STATUS = { active: ['进行中', 'info'], completed: ['完成', 'ok'], archived: ['归档', 'muted'], cancelled: ['取消', 'muted'] };
  var LIFECYCLE = { development: ['开发', 'info'], validation: ['验证', 'warn'], transfer: ['转移', 'warn'], routine: ['常规使用', 'ok'], retired: ['停用', 'muted'] };

  MF.badge = function (text, kind) {
    return h('span', { class: 'badge badge-' + (kind || 'muted') }, text === null || text === undefined ? '' : String(text));
  };
  MF.statusBadge = function (status, label, stale) {
    var kids = [MF.badge(label || STATUS_LABELS[status] || '未知', STATUS_KIND[status] || 'muted')];
    if (stale) kids.push(' ', MF.badge('已失效', 'warn'));
    return h('span', { class: 'nowrap' }, kids);
  };
  MF.progressBar = function (pct) {
    var n = Number(pct);
    if (!isFinite(n)) n = 0;
    n = Math.max(0, Math.min(100, n));
    return h('div', { class: 'progress' + (n >= 100 ? ' done' : ''), role: 'progressbar', 'aria-valuenow': Math.round(n), 'aria-valuemin': 0, 'aria-valuemax': 100, title: Math.round(n) + '%' },
      h('div', { class: 'progress-bar', style: { width: n + '%' } }));
  };
  /* ctx: 'project' | 'method' | undefined (global / ambiguous: owner -> 负责人) */
  MF.roleLabel = function (role, ctx) {
    var map = ctx === 'project' ? PROJECT_ROLE_LABELS : ctx === 'method' ? METHOD_ROLE_LABELS : ROLE_LABELS;
    return map[role] || ROLE_LABELS[role] || (role ? String(role) : '');
  };
  MF.projectRoleLabel = function (r) { return MF.roleLabel(r, 'project'); };
  MF.methodRoleLabel = function (r) { return MF.roleLabel(r, 'method'); };
  MF.projectStatusBadge = function (s, label) { var p = PROJECT_STATUS[s] || [label || '未知', 'muted']; return MF.badge(label || p[0], p[1]); };
  MF.methodStatusBadge = function (s, label) { var p = METHOD_STATUS[s] || [label || '未知', 'muted']; return MF.badge(label || p[0], p[1]); };
  MF.lifecycleBadge = function (s, label) { var p = LIFECYCLE[s] || [label || '未知', 'muted']; return MF.badge(label || p[0], p[1]); };
  /* hash query parameters of the current route, e.g. #/methods/new?project=3 -> {project:'3'} */
  MF.query = function () {
    var raw = (location.hash || '').replace(/^#/, '');
    var i = raw.indexOf('?');
    var out = {};
    if (i < 0) return out;
    raw.slice(i + 1).split('&').forEach(function (kv) {
      if (!kv) return;
      var j = kv.indexOf('=');
      var k = j < 0 ? kv : kv.slice(0, j), v = j < 0 ? '' : kv.slice(j + 1);
      try { out[decodeURIComponent(k)] = decodeURIComponent(v.replace(/\+/g, ' ')); } catch (e) { out[k] = v; }
    });
    return out;
  };
  MF.hasRole = function () {
    var u = MF.state.user;
    if (!u || !u.roles) return false;
    for (var i = 0; i < arguments.length; i++) if (u.roles.indexOf(arguments[i]) >= 0) return true;
    return false;
  };

  /* extras (not in the contract, available to everyone) */
  MF.loading = function (msg) { return h('div', { class: 'loading' }, h('span', { class: 'spinner' }), h('div', { style: { marginTop: '8px' } }, msg || '加载中……')); };
  MF.errorBox = function (e, retry) {
    var msg = (e && e.message) ? e.message : '发生未知错误';
    return h('div', { class: 'callout callout-err' }, h('strong', null, '出错了：'), msg,
      retry ? h('div', { style: { marginTop: '8px' } }, h('button', { class: 'btn btn-sm', onclick: retry }, '重试')) : null);
  };
  MF.field = function (label, control, opts) {
    opts = opts || {};
    return h('div', { class: 'field' + (opts.class ? ' ' + opts.class : '') },
      label ? h('label', null, label, opts.required ? h('span', { class: 'req' }, '*') : null) : null,
      control,
      opts.hint ? h('div', { class: 'hint' }, opts.hint) : null);
  };

  /* ------------------------------------------------------------------ API */
  /* Friendly Chinese fallbacks when the server sent no (or a non-Chinese) message. */
  function friendlyStatus(status, raw) {
    var base = {
      400: '提交的内容有误，请检查后重试', 401: '未登录或会话已过期，请重新登录', 403: '权限不足，无法执行此操作', 404: '未找到所请求的内容',
      405: '不支持此操作', 409: '操作与当前数据状态冲突（内容可能已被他人更新或对象已非“进行中”），请刷新后重试',
      413: '提交的内容或文件过大', 422: '提交的内容不符合要求，请按提示补充后重试', 423: '账号或操作已被临时锁定，请稍后再试',
      429: '操作过于频繁，请稍后再试', 500: '服务器内部错误，请稍后重试或联系管理员', 502: '服务暂时不可用，请稍后重试', 503: '服务暂时不可用，请稍后重试'
    };
    return base[status] || ('请求失败（HTTP ' + status + '）');
  }
  MF.friendlyStatus = friendlyStatus;

  function request(method, url, headers, body, opts) {
    opts = opts || {};
    var init = { method: method, credentials: 'same-origin', headers: headers };
    if (body !== undefined) init.body = body;
    return fetch(url, init).then(function (res) {
      return res.text().then(function (text) {
        var data = null;
        if (text) { try { data = JSON.parse(text); } catch (e) { data = text; } }
        if (!res.ok) {
          var msg = '';
          if (data && typeof data === 'object') {
            msg = data.error || (typeof data.detail === 'string' ? data.detail : '');
          }
          if (!msg || /^[\x00-\x7f]*$/.test(msg)) msg = friendlyStatus(res.status, msg);
          var err = new Error(msg);
          err.status = res.status;
          err.detail = data && typeof data === 'object' ? data.detail : undefined;
          err.data = data;
          err.mustChange = !!(data && typeof data === 'object' && data.must_change);
          if (res.status === 401 && !opts.noAuth) MF.showLogin();
          if (res.status === 403 && err.mustChange && !opts.noAuth) MF.changePassword(true);
          throw err;
        }
        return data;
      });
    }, function () {
      var err = new Error('无法连接到服务器，请检查服务是否在运行');
      err.status = 0;
      throw err;
    });
  }

  MF.api = function (method, url, body, opts) {
    method = (method || 'GET').toUpperCase();
    var headers = { 'Accept': 'application/json' };
    var payload;
    if (method !== 'GET' && method !== 'HEAD') {
      headers['X-Requested-With'] = 'MethodFlow';
      if (body !== undefined && body !== null) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body); }
    }
    return request(method, url, headers, payload, opts);
  };

  /* PDF export capability: {known, pdf, pdf_note}; 404 (endpoint not available) -> known:false */
  var capsCache = null;
  MF.capabilities = function (force) {
    if (capsCache && !force) return capsCache;
    capsCache = MF.api('GET', '/api/system/capabilities').then(function (r) {
      r = r && typeof r === 'object' ? r : {};
      return { known: true, pdf: !!r.pdf, pdf_note: r.pdf_note === null || r.pdf_note === undefined ? '' : String(r.pdf_note) };
    }, function (e) {
      if (e && e.status === 401) throw e;
      return { known: false, pdf: false, pdf_note: '' };
    });
    return capsCache;
  };

  MF.upload = function (url, file) {
    return request('POST', url, { 'X-Requested-With': 'MethodFlow', 'Content-Type': 'application/octet-stream', 'Accept': 'application/json' }, file);
  };

  /* ------------------------------------------------------------------ toast */
  var toastBox = null;
  MF.toast = function (msg, type) {
    type = type || 'ok';
    if (!toastBox || !document.body.contains(toastBox)) {
      toastBox = h('div', { class: 'toasts', 'aria-live': 'polite' });
      document.body.appendChild(toastBox);
    }
    var t = h('div', { class: 'toast toast-' + type, role: type === 'err' ? 'alert' : 'status' }, msg === null || msg === undefined ? '' : String(msg));
    toastBox.appendChild(t);
    setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, type === 'err' ? 5000 : 3000);
  };

  /* ------------------------------------------------------------------ modal */
  var openModals = [];
  MF.modal = function (o) {
    o = o || {};
    return new Promise(function (resolve) {
      var prevFocus = document.activeElement;
      var buttons = (o.buttons && o.buttons.length) ? o.buttons : [{ label: '确定', kind: 'primary', value: true }];
      var done = false;
      var errBox = h('div', { class: 'err-text', style: { padding: '0 18px 8px' }, hidden: true, role: 'alert' });
      var btnEls = [];
      var backdrop, box, primaryBtn = null;

      function close(v) {
        if (done) return;
        done = true;
        document.removeEventListener('keydown', onKey, true);
        var i = openModals.indexOf(entry);
        if (i >= 0) openModals.splice(i, 1);
        if (backdrop.parentNode) backdrop.parentNode.removeChild(backdrop);
        try { if (prevFocus && prevFocus.focus && document.body.contains(prevFocus)) prevFocus.focus(); } catch (e) { /* ignore */ }
        resolve(v === undefined ? null : v);
      }
      var entry = { close: close };
      var ctl = {
        close: close,
        body: null,
        error: function (msg) { errBox.textContent = msg || ''; errBox.hidden = !msg; },
        setBusy: function (b) { btnEls.forEach(function (x) { x.disabled = !!b; }); }
      };

      function onKey(ev) {
        if (openModals[openModals.length - 1] !== entry) return;
        if (ev.key === 'Escape' && !o.persistent) { ev.stopPropagation(); close(null); return; }
        if (ev.key === 'Enter' && primaryBtn && ev.target && ev.target.tagName === 'INPUT' && ev.target.type !== 'checkbox' && ev.target.type !== 'radio' && ev.target.type !== 'file') {
          ev.preventDefault();
          primaryBtn.click();
        }
        if (ev.key === 'Tab') { // simple focus trap
          var f = box.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled])');
          if (!f.length) return;
          var first = f[0], last = f[f.length - 1];
          if (ev.shiftKey && document.activeElement === first) { ev.preventDefault(); last.focus(); }
          else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); }
        }
      }

      buttons.forEach(function (b) {
        var el = h('button', { type: 'button', class: 'btn' + (b.kind === 'primary' ? ' btn-primary' : b.kind === 'danger' ? ' btn-danger' : '') }, b.label || '确定');
        el.addEventListener('click', function () {
          ctl.error('');
          if (typeof b.onClick === 'function') {
            ctl.setBusy(true);
            var r;
            try { r = b.onClick(ctl); } catch (e) { r = Promise.reject(e); }
            Promise.resolve(r).then(function (ok) {
              if (done) return;
              ctl.setBusy(false);
              if (ok !== false) close(b.value === undefined ? true : b.value);
            }, function (e) {
              if (done) return;
              ctl.setBusy(false);
              ctl.error(e && e.message ? e.message : '操作失败');
            });
          } else {
            close(b.value === undefined ? true : b.value);
          }
        });
        if (b.kind === 'primary' || (b.kind === 'danger' && !primaryBtn)) { if (!primaryBtn || b.kind === 'primary') primaryBtn = el; }
        btnEls.push(el);
      });

      var bodyWrap = h('div', { class: 'modal-b' }, o.body || null);
      ctl.body = bodyWrap;
      box = h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', style: o.width ? { width: typeof o.width === 'number' ? o.width + 'px' : o.width } : null },
        h('div', { class: 'modal-h' }, o.title || '', o.persistent ? null : h('button', { class: 'x', type: 'button', 'aria-label': '关闭', onclick: function () { close(null); } }, '×')),
        bodyWrap, errBox,
        h('div', { class: 'modal-f' }, btnEls));
      backdrop = h('div', { class: 'modal-backdrop' }, box);
      document.body.appendChild(backdrop);
      openModals.push(entry);
      document.addEventListener('keydown', onKey, true);
      var focusEl = bodyWrap.querySelector('input:not([type=hidden]):not([disabled]),textarea,select') || primaryBtn || btnEls[0];
      if (focusEl) setTimeout(function () { try { focusEl.focus(); } catch (e) { /* ignore */ } }, 0);
    });
  };

  MF.confirm = function (msg, opts) {
    opts = opts || {};
    return MF.modal({
      title: opts.title || (opts.danger ? '请确认' : '确认'),
      body: h('div', { style: { whiteSpace: 'pre-wrap' } }, msg === null || msg === undefined ? '' : String(msg)),
      width: 440,
      buttons: [{ label: opts.cancelLabel || '取消', value: false }, { label: opts.okLabel || '确定', kind: opts.danger ? 'danger' : 'primary', value: true }]
    }).then(function (v) { return v === true; });
  };

  MF.askSign = function (o) {
    o = o || {};
    var showComment = !!(o.needComment || o.commentRequired);
    var comment = h('textarea', { class: 'textarea', rows: 3, placeholder: o.commentLabel || '意见' });
    var pw = h('input', { class: 'input', type: 'password', autocomplete: 'current-password' });
    var body = h('div', null,
      o.meaning ? h('div', { class: 'callout' }, h('div', { class: 'small muted' }, '签名含义'), h('div', null, o.meaning)) : null,
      showComment ? MF.field((o.commentLabel || '意见') + (o.commentRequired ? '' : '（可选）'), comment, { required: !!o.commentRequired }) : null,
      MF.field('当前账号密码（电子签名重新认证）', pw, { required: true, hint: '签名将记录您的姓名、时间与含义，并与当前内容绑定，不可撤销。' }));
    return MF.modal({
      title: o.title || '电子签名', body: body, width: 480,
      buttons: [{ label: '取消', value: null }, {
        label: '签名并确认', kind: 'primary',
        onClick: function (ctl) {
          if (showComment && o.commentRequired && !comment.value.trim()) { ctl.error('请填写' + (o.commentLabel || '意见')); return false; }
          if (!pw.value) { ctl.error('请输入密码以完成签名'); return false; }
          ctl.close({ password: pw.value, comment: comment.value.trim() });
          return false;
        }
      }]
    });
  };

  /* ------------------------------------------------------------------ dirty guard */
  var dirty = false;
  MF.dirtyGuard = { set: function (b) { dirty = !!b; }, isDirty: function () { return dirty; } };
  window.addEventListener('beforeunload', function (e) {
    if (dirty) { e.preventDefault(); e.returnValue = ''; return ''; }
    return undefined;
  });

  /* ------------------------------------------------------------------ router */
  var routes = [];
  var currentPath = '/';
  var renderId = 0;
  var lastHash = '#/';

  MF.route = function (pattern, handler) {
    var parts = pattern.split('/').filter(Boolean);
    var score = parts.filter(function (p) { return p.charAt(0) !== ':'; }).length;
    for (var i = routes.length - 1; i >= 0; i--) if (routes[i].pattern === pattern) routes.splice(i, 1);
    routes.push({ pattern: pattern, parts: parts, score: score, handler: handler });
  };

  function matchRoute(path) {
    var segs = path.split('/').filter(Boolean);
    var best = null;
    routes.forEach(function (r) {
      if (r.parts.length !== segs.length) return;
      var params = {};
      for (var i = 0; i < r.parts.length; i++) {
        var p = r.parts[i];
        if (p.charAt(0) === ':') {
          try { params[p.slice(1)] = decodeURIComponent(segs[i]); } catch (e) { params[p.slice(1)] = segs[i]; }
        } else if (p !== segs[i]) return;
      }
      if (!best || r.score > best.route.score) best = { route: r, params: params };
    });
    return best;
  }

  MF.currentPath = function () { return currentPath; };
  MF.navigate = function (hash) {
    var t = '#' + String(hash || '/').replace(/^#/, '');
    if (location.hash === t) render(false); else location.hash = t;
  };

  var crumbsEl = null;
  MF.setCrumbs = function (list) {
    list = list || [];
    var title = list.length ? list[list.length - 1].label : '';
    document.title = (title ? title + ' - ' : '') + 'MethodFlow';
    if (!crumbsEl) return;
    MF.clear(crumbsEl);
    list.forEach(function (c, i) {
      if (i > 0) crumbsEl.appendChild(h('span', { class: 'crumb-sep' }, '›'));
      var label = c.label === null || c.label === undefined ? '' : String(c.label);
      if (c.href && i < list.length - 1) crumbsEl.appendChild(h('a', { href: '#' + String(c.href).replace(/^#/, '') }, label));
      else crumbsEl.appendChild(h('span', { class: i === list.length - 1 ? 'crumb-cur' : '' }, label));
    });
  };

  function highlightNav(path) {
    var key = '/';
    if (path === '/' || path === '') key = '/';
    else if (path.indexOf('/kb') === 0) key = '/kb';
    else if (path.indexOf('/guide') === 0) key = '/guide';
    else if (path.indexOf('/registry') === 0) key = '/registry';
    else if (path.indexOf('/audit-review') === 0) key = '/admin';
    else if (path.indexOf('/admin') === 0) key = '/admin';
    else if (path.indexOf('/projects') === 0 || path.indexOf('/pr/') === 0) key = '/projects';
    else if (path.indexOf('/methods') === 0 || path.indexOf('/m/') === 0) key = '/methods';
    var links = document.querySelectorAll('.nav a[data-nav]');
    for (var i = 0; i < links.length; i++) links[i].classList.toggle('active', links[i].getAttribute('data-nav') === key);
  }

  function render(keep) {
    var main = document.getElementById('app-main');
    if (!main) return Promise.resolve();
    var raw = (location.hash || '').replace(/^#/, '') || '/';
    var path = raw.split('?')[0];
    if (path.charAt(0) !== '/') path = '/' + path;
    currentPath = path;
    lastHash = location.hash || '#/';
    highlightNav(path);
    var shell = document.querySelector('.shell');
    if (shell) shell.classList.remove('nav-open');
    var rid = ++renderId;
    if (MF._closeMenu) MF._closeMenu();
    var container = h('div', { class: 'page' });
    var m = matchRoute(path);
    var oldScroll = window.scrollY;
    dirty = false;
    var swapped = false;
    function swap() {
      if (swapped || rid !== renderId) return;
      swapped = true;
      MF.clear(main);
      main.appendChild(container);
      window.scrollTo(0, keep ? oldScroll : 0);
    }
    if (!keep) { MF.clear(main); main.appendChild(MF.loading()); }
    if (!m) {
      MF.setCrumbs([{ label: '页面不存在' }]);
      container.appendChild(h('div', { class: 'card empty' }, h('h2', null, '404 页面不存在'), h('p', null, '找不到地址：' + path),
        h('a', { class: 'btn btn-primary', href: '#/' }, '返回工作台')));
      swap();
      return Promise.resolve();
    }
    if (!keep) swap();
    var p;
    try { p = Promise.resolve(m.route.handler(m.params, container)); } catch (e) { p = Promise.reject(e); }
    return p.then(function () { if (keep) swap(); }, function (e) {
      if (rid !== renderId) return;
      if (e && e.status === 401) return;
      MF.clear(container);
      if (e && e.mustChange) {
        MF.setCrumbs([{ label: '须先修改密码' }]);
        container.appendChild(h('div', { class: 'callout callout-warn' }, '须先修改密码后才能继续使用，请在弹出的对话框中完成修改。'));
        swap();
        return;
      }
      if (typeof console !== 'undefined') console.error(e);
      var st = e && e.status;
      MF.setCrumbs([{ label: st === 403 ? '无权访问' : st === 404 ? '未找到' : '出错了' }]);
      container.appendChild(MF.errorBox(e, function () { MF.reload(); }));
      swap();
    });
  }

  MF.reload = function () { return render(true); };

  window.addEventListener('hashchange', function () {
    if (!document.getElementById('app-main')) return;
    if (dirty) {
      var target = location.hash;
      try { history.replaceState(null, '', lastHash); } catch (e) { /* ignore */ }
      MF.confirm('当前页面有未保存的修改，确定离开吗？未保存的内容将丢失。', { danger: true, okLabel: '离开' }).then(function (ok) {
        if (!ok) return;
        dirty = false;
        location.hash = target;
      });
      return;
    }
    render(false);
  });

  /* ------------------------------------------------------------------ theme */
  function getTheme() { try { return localStorage.getItem('mf_theme') || 'auto'; } catch (e) { return 'auto'; } }
  function applyTheme(t) {
    if (t === 'light' || t === 'dark') document.documentElement.setAttribute('data-theme', t);
    else document.documentElement.removeAttribute('data-theme');
  }
  applyTheme(getTheme());
  var THEME_LABEL = { auto: '跟随系统', light: '浅色', dark: '深色' };

  /* ------------------------------------------------------------------ password dialog */
  var forcedOpen = null;
  MF.changePassword = function (forced) {
    if (forced) {
      if (forcedOpen) return forcedOpen;
      var pr = doChangePassword(true);
      forcedOpen = pr;
      pr.then(function () { forcedOpen = null; if (MF.state.user && MF.state.user.must_change === false) MF.reload(); }, function () { forcedOpen = null; });
      return pr;
    }
    return doChangePassword(false);
  };
  function doChangePassword(forced) {
    var minLen = (MF.state.app && MF.state.app.min_password_length) || 10;
    var oldI = h('input', { class: 'input', type: 'password', autocomplete: 'current-password' });
    var newI = h('input', { class: 'input', type: 'password', autocomplete: 'new-password' });
    var cfmI = h('input', { class: 'input', type: 'password', autocomplete: 'new-password' });
    var body = h('div', null,
      forced ? h('div', { class: 'callout callout-warn' }, '您的密码由管理员设置或重置，首次使用前须先修改密码。') : null,
      MF.field('原密码', oldI, { required: true }),
      MF.field('新密码', newI, { required: true, hint: '至少 ' + minLen + ' 位，且同时包含字母和数字。' }),
      MF.field('确认新密码', cfmI, { required: true }));
    return MF.modal({
      title: '修改密码', body: body, width: 440, persistent: !!forced,
      buttons: (forced ? [] : [{ label: '取消', value: null }]).concat([{
        label: '确认修改', kind: 'primary', value: true,
        onClick: function (ctl) {
          if (!oldI.value || !newI.value) { ctl.error('请填写原密码和新密码'); return false; }
          if (newI.value !== cfmI.value) { ctl.error('两次输入的新密码不一致'); return false; }
          return MF.api('POST', '/api/me/password', { old: oldI.value, 'new': newI.value }).then(function () {
            if (MF.state.user) MF.state.user.must_change = false;
            MF.toast('密码已修改', 'ok');
          });
        }
      }])
    });
  }

  /* ------------------------------------------------------------------ login / setup */
  function brandMark() { return h('div', { class: 'brand-mark' }, 'M'); }

  MF.showLogin = function (mode) {
    openModals.slice().forEach(function (m) { m.close(null); });
    MF.state.user = null;
    var root = document.getElementById('root');
    if (document.getElementById('login-form') && !mode) return;
    var setup = mode === 'setup';
    var minLen = (MF.state.app && MF.state.app.min_password_length) || 10;
    var user = h('input', { class: 'input', name: 'username', autocomplete: 'username', autofocus: true });
    var disp = h('input', { class: 'input', name: 'display_name', autocomplete: 'name' });
    var pw = h('input', { class: 'input', type: 'password', name: 'password', autocomplete: setup ? 'new-password' : 'current-password' });
    var pw2 = h('input', { class: 'input', type: 'password', autocomplete: 'new-password' });
    var needToken = setup && !!(MF.state.app && MF.state.app.setup_token_required);
    var tokenI = h('input', { class: 'input', type: 'password', name: 'setup_token', autocomplete: 'off' });
    var err = h('div', { class: 'callout callout-err', hidden: true, role: 'alert' });
    var btn = h('button', { class: 'btn btn-primary', type: 'submit', style: { width: '100%', marginTop: '6px' } }, setup ? '创建管理员并进入' : '登录');

    function fail(msg) { err.textContent = msg; err.hidden = false; }
    function submit(ev) {
      ev.preventDefault();
      err.hidden = true;
      var u = user.value.trim();
      if (!u || !pw.value) { fail(setup ? '请填写用户名和密码' : '请输入用户名和密码'); return; }
      if (setup) {
        if (!disp.value.trim()) { fail('请填写姓名'); return; }
        if (pw.value !== pw2.value) { fail('两次输入的密码不一致'); return; }
        if (needToken && !tokenI.value) { fail('请填写部署配置中的初始化口令（setup_token）'); return; }
      }
      btn.disabled = true;
      var setupBody = { username: u, display_name: disp.value.trim(), password: pw.value };
      if (needToken) setupBody.setup_token = tokenI.value;
      var req = setup
        ? MF.api('POST', '/api/setup', setupBody, { noAuth: true })
        : MF.api('POST', '/api/login', { username: u, password: pw.value }, { noAuth: true });
      req.then(function (r) {
        MF.state.user = r.user;
        MF.startApp();
      }, function (e) {
        btn.disabled = false;
        fail(e.message || '登录失败');
      });
    }

    var form = h('form', { id: 'login-form', onsubmit: submit, novalidate: true },
      brandMark(),
      h('h1', null, setup ? '首次使用：创建管理员' : 'MethodFlow'),
      h('p', { class: 'muted' }, setup ? '系统尚无任何账号。请创建第一个管理员账号（同时具备开发、复核、批准角色，之后可在“管理”中新增用户并调整角色）。' : '分析方法开发管理系统 · 请登录'),
      err,
      MF.field('用户名', user),
      setup ? MF.field('姓名', disp) : null,
      MF.field('密码', pw, setup ? { hint: '至少 ' + minLen + ' 位，且同时包含字母和数字。' } : null),
      setup ? MF.field('确认密码', pw2) : null,
      needToken ? MF.field('初始化口令', tokenI, { hint: '部署人员在配置文件（config.json 的 setup_token）中设置的一次性口令。' }) : null,
      btn,
      h('p', { class: 'hint', style: { marginTop: '14px', marginBottom: 0 } }, '本程序为辅助工具；用于 GxP 场景前须按企业计算机化系统验证（CSV）流程评估。'));
    MF.clear(root);
    root.appendChild(h('div', { class: 'login-wrap' }, h('div', { class: 'login-card' }, form)));
    setTimeout(function () { user.focus(); }, 0);
  };

  /* ------------------------------------------------------------------ shell */
  var ICONS = {
    home: '<svg viewBox="0 0 24 24"><path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/></svg>',
    proj: '<svg viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>',
    method: '<svg viewBox="0 0 24 24"><path d="M9 3h6"/><path d="M10 3v6.5L4.5 19a1.6 1.6 0 0 0 1.4 2.4h12.2a1.6 1.6 0 0 0 1.4-2.4L14 9.5V3"/><path d="M7.5 15h9"/></svg>',
    kb: '<svg viewBox="0 0 24 24"><path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 21V5"/><path d="M9 8h6"/></svg>',
    admin: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1.2l2-1.5-2-3.4-2.3 1a7 7 0 0 0-2-1.2L14.2 3h-4l-.4 2.7a7 7 0 0 0-2 1.2l-2.3-1-2 3.4 2 1.5a7 7 0 0 0 0 2.4l-2 1.5 2 3.4 2.3-1a7 7 0 0 0 2 1.2l.4 2.7h4l.4-2.7a7 7 0 0 0 2-1.2l2.3 1 2-3.4-2-1.5c.1-.4.1-.8.1-1.2z"/></svg>'
  };
  function icon(name) { var s = h('span', { style: { display: 'inline-flex' } }); s.innerHTML = ICONS[name]; return s; }

  function buildShell() {
    var root = document.getElementById('root');
    var u = MF.state.user || {};
    var shell, menuPop = null;
    var navItems = [{ href: '/', key: '/', label: '工作台', icon: 'home' }, { href: '/projects', key: '/projects', label: '项目', icon: 'proj' },
      { href: '/methods', key: '/methods', label: '方法', icon: 'method' }, { href: '/guide', key: '/guide', label: '新手指引', icon: 'kb' },
      { href: '/registry', key: '/registry', label: '台账', icon: 'method' }, { href: '/kb', key: '/kb', label: '知识库', icon: 'kb' }];
    if (MF.hasRole('admin')) navItems.push({ href: '/admin', key: '/admin', label: '管理', icon: 'admin' });
    var nav = h('nav', { class: 'nav', 'aria-label': '主导航' }, navItems.map(function (n) {
      return h('a', { href: '#' + n.href, 'data-nav': n.key }, icon(n.icon), n.label);
    }));
    crumbsEl = h('div', { class: 'crumbs', 'aria-label': '面包屑' });
    var initial = (u.display_name || u.username || '?').trim().slice(0, 1).toUpperCase();

    function closeMenu() { if (menuPop) { menuPop.remove(); menuPop = null; } }
    MF._closeMenu = closeMenu;
    function openMenu() {
      closeMenu();
      var theme = getTheme();
      menuPop = h('div', { class: 'menu-pop', role: 'menu' },
        h('div', { class: 'menu-head' }, h('div', { class: 'strong' }, u.display_name || u.username || ''),
          h('div', { class: 'small muted' }, (u.username || '') + (u.roles && u.roles.length ? ' · ' + u.roles.map(MF.roleLabel).join('、') : ''))),
        h('button', { type: 'button', role: 'menuitem', onclick: function () { closeMenu(); MF.changePassword(false); } }, '修改密码'),
        h('button', { type: 'button', role: 'menuitem', onclick: function () { closeMenu(); if (MF.setMyEmail) MF.setMyEmail(); } }, '设置我的邮箱（邮件通知）'),
        h('button', { type: 'button', role: 'menuitem', onclick: function () {
          var order = ['auto', 'light', 'dark'];
          var next = order[(order.indexOf(theme) + 1) % 3];
          try { localStorage.setItem('mf_theme', next); } catch (e) { /* ignore */ }
          applyTheme(next); closeMenu(); MF.toast('主题：' + THEME_LABEL[next], 'ok');
        } }, '主题：' + THEME_LABEL[theme] + '（点击切换）'),
        h('button', { type: 'button', role: 'menuitem', onclick: function () {
          closeMenu();
          MF.api('POST', '/api/logout', {}, { noAuth: true }).then(null, function () { /* ignore */ }).then(function () {
            MF.state.user = null; dirty = false; MF.showLogin();
          });
        } }, '退出登录'));
      userMenu.appendChild(menuPop);
    }
    var userMenu = h('div', { class: 'usermenu' },
      h('button', { class: 'userbtn', type: 'button', 'aria-haspopup': 'true', onclick: function (e) { e.stopPropagation(); if (menuPop) closeMenu(); else openMenu(); } },
        h('span', { class: 'avatar' }, initial), h('span', { class: 'uname' }, u.display_name || u.username || '')));
    document.addEventListener('click', function (e) { if (menuPop && !userMenu.contains(e.target)) closeMenu(); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeMenu(); });

    shell = h('div', { class: 'shell' },
      h('aside', { class: 'side' },
        h('div', { class: 'brand' }, h('span', { class: 'brand-mark' }, 'M'), h('div', null, 'MethodFlow', h('small', null, '分析方法开发管理'))),
        nav,
        h('div', { class: 'side-foot' }, 'v' + ((MF.state.app && MF.state.app.version) || ''))),
      h('div', { class: 'side-backdrop', onclick: function () { shell.classList.remove('nav-open'); } }),
      h('div', { class: 'main-col' },
        h('header', { class: 'topbar' },
          h('button', { class: 'menu-btn', type: 'button', 'aria-label': '菜单', onclick: function () { shell.classList.toggle('nav-open'); } }, '☰'),
          crumbsEl, h('form', { class: 'topsearch', style: { margin: '0 10px 0 auto' }, onsubmit: function (ev) { ev.preventDefault(); var q = ev.target.q.value.trim(); if (q) MF.navigate('/search?q=' + encodeURIComponent(q)); } },
            h('input', { class: 'input', name: 'q', type: 'search', placeholder: '搜索…', 'aria-label': '搜索', style: { width: '170px', padding: '3px 8px' } })), bell.el, userMenu),
        h('main', { id: 'app-main' })));
    MF.clear(root);
    root.appendChild(shell);
    bell.start();
  }

  /* ------------------------------------------------------------------ notification bell (in-app notifications) */
  function makeBell() {
    var pop = null, items = [], unread = 0, timer = null;
    var count = h('span', { class: 'bell-count', hidden: true, style: { background: 'var(--c-err,#c0392b)', color: '#fff', borderRadius: '9px', fontSize: '11px', padding: '0 5px', marginLeft: '4px' } });
    var box = h('div', { class: 'usermenu', style: { position: 'relative' } });
    var btn = h('button', { class: 'userbtn', type: 'button', 'aria-haspopup': 'true', title: '通知', 'aria-label': '通知' }, '🔔', count);
    box.appendChild(btn);
    function paint() { count.textContent = unread > 99 ? '99+' : String(unread); count.hidden = !unread; }
    function load() {
      if (!MF.state.user || document.hidden) return;
      MF.api('GET', '/api/notifications?limit=20', null, { noAuth: true }).then(function (r) { items = r.items || []; unread = r.unread || 0; paint(); if (pop) draw(); }, function () { /* ignore */ });
    }
    function markRead(ids) {
      return MF.api('POST', '/api/notifications/read', ids ? { ids: ids } : { all: true }).then(function (r) { unread = r.unread || 0; paint(); });
    }
    function close() { if (pop) { pop.remove(); pop = null; } }
    function draw() {
      if (!pop) return;
      MF.clear(pop);
      pop.appendChild(h('div', { class: 'menu-head', style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '10px' } },
        h('strong', null, '通知'),
        unread ? h('button', { type: 'button', class: 'btn btn-sm', onclick: function () { markRead(null).then(function () { items.forEach(function (i) { i.read = 1; }); draw(); }); } }, '全部标为已读') : null));
      if (!items.length) { pop.appendChild(h('div', { class: 'small muted', style: { padding: '12px' } }, '暂无通知')); return; }
      items.forEach(function (n) {
        pop.appendChild(h('button', { type: 'button', role: 'menuitem', style: { display: 'block', textAlign: 'left', width: '100%', whiteSpace: 'normal', opacity: n.read ? 0.65 : 1 }, onclick: function () {
          close();
          if (!n.read) { n.read = 1; markRead([n.id]); }
          if (n.method_id) MF.navigate('/m/' + n.method_id + (n.stage_key ? '/stage/' + n.stage_key : ''));
        } },
          h('div', { class: n.read ? '' : 'strong' }, (n.read ? '' : '● ') + n.title),
          n.body ? h('div', { class: 'small muted' }, n.body) : null,
          h('div', { class: 'small muted' }, MF.fmt.datetime(n.created_at))));
      });
    }
    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      if (pop) { close(); return; }
      pop = h('div', { class: 'menu-pop', role: 'menu', style: { minWidth: '320px', maxWidth: '420px', maxHeight: '70vh', overflowY: 'auto', right: 0 } });
      box.appendChild(pop);
      draw(); load();
    });
    document.addEventListener('click', function (e) { if (pop && !box.contains(e.target)) close(); });
    return {
      el: box,
      start: function () { load(); if (timer) clearInterval(timer); timer = setInterval(load, 60000); },
      refresh: load
    };
  }
  var bell = makeBell();
  MF.refreshNotifications = function () { bell.refresh(); };

  MF.startApp = function () {
    dirty = false;
    buildShell();
    if (!location.hash || location.hash === '#') { try { history.replaceState(null, '', '#/'); } catch (e) { location.hash = '#/'; } }
    render(false);
    if (MF.state.user && MF.state.user.must_change) MF.changePassword(true);
  };
})();
