/* MethodFlow stage editor: MF.renderStage(container, mid, key, method)   [API v2: stages belong to a METHOD]
   Sections (text/fields/table/matrix/fmea), checklist, gate panel (submit/withdraw/review/reopen/recertify),
   experiments, attachments, knowledge tips, revision history.  All data is written with textContent (no innerHTML). */
(function () {
  'use strict';
  var MF = window.MF = window.MF || {};

  /* ================================================================== helpers */
  function H(tag, attrs) {
    var a = Array.prototype.slice.call(arguments);
    if (a[1] === undefined) a[1] = null;
    return MF.h.apply(MF, a);
  }
  function S(v) { return (v === null || v === undefined || (typeof v === 'number' && !isFinite(v))) ? '' : String(v); }
  function clone(v) { return v === undefined ? undefined : JSON.parse(JSON.stringify(v)); }
  function jstr(v) { return JSON.stringify(v === undefined ? null : v); }
  function isBlank(v) {
    if (v === null || v === undefined) return true;
    if (typeof v === 'string') return !v.trim();
    if (Array.isArray(v)) return v.every(isBlank);
    if (typeof v === 'object') return Object.keys(v).every(function (k) { return isBlank(v[k]); });
    return false;
  }
  function toast(msg, type) { if (MF.toast) MF.toast(msg, type || 'ok'); }
  function errText(e) { return (e && e.message) ? e.message : '操作失败'; }
  function two(n) { return (n < 10 ? '0' : '') + n; }
  function nowClock() { var d = new Date(); return two(d.getHours()) + ':' + two(d.getMinutes()) + ':' + two(d.getSeconds()); }
  function fdate(s) { return s ? (MF.fmt && MF.fmt.date ? MF.fmt.date(s) : String(s).slice(0, 10)) : '—'; }
  function fdt(s) { return s ? (MF.fmt && MF.fmt.datetime ? MF.fmt.datetime(s) : String(s)) : '—'; }
  function fsize(n) {
    if (MF.fmt && MF.fmt.size) return MF.fmt.size(n);
    n = Number(n); if (!isFinite(n)) return '—';
    return n < 1024 ? n + ' B' : n < 1048576 ? (n / 1024).toFixed(1) + ' KB' : (n / 1048576).toFixed(1) + ' MB';
  }
  var ROLE_FALLBACK = { owner: '方法负责人', author: '开发人员', reviewer: '复核人', approver: '批准人(QA)', viewer: '只读' };
  function roleLabel(r) { return ROLE_FALLBACK[r] || (MF.roleLabel && MF.roleLabel(r)) || S(r); }   // in a method context 'owner' = 方法负责人
  var EXP_STATUS = { planned: '计划中', running: '进行中', done: '已完成', cancelled: '已取消' };
  var EXP_KIND = { planned: 'muted', running: 'warn', done: 'ok', cancelled: 'muted' };
  var KB_KIND = { rule: '规则', pitfall: '易错点', howto: '做法', reference: '参考', lesson: '经验教训' };
  var KB_KIND_CLS = { rule: 'info', pitfall: 'err', howto: 'ok', reference: 'muted', lesson: 'warn' };
  var EDITABLE_STATUS = ['not_started', 'in_progress', 'returned'];
  var SAMPLE_MARK = '示例值，须按ATP确认';
  function sampleCount(v) {
    if (v === null || v === undefined) return 0;
    var t = typeof v === 'string' ? v : JSON.stringify(v);
    return t.split('示例值').length - 1 + (t.match(/(^|[^A-Za-z])XX+(?![A-Za-z])/g) || []).length;
  }
  function hasSample(v) { return S(v).indexOf('示例值') >= 0 || /(^|[^A-Za-z])XX+(?![A-Za-z])/.test(S(v)); }
  function badge(t, k) { return MF.badge ? MF.badge(t, k) : H('span', { class: 'badge badge-' + (k || 'muted') }, t); }

  function thresholds() {
    var a = (MF.state && MF.state.app) || {};
    return { rpn: Number(a.rpn_threshold) || 120, sev: Number(a.severity_threshold) || 8 };
  }
  function num(v) { if (v === '' || v === null || v === undefined) return NaN; return Number(v); }
  function autosize(ta) {
    if (!ta || !ta.isConnected || ta.offsetParent === null) return;
    ta.style.height = 'auto';
    ta.style.height = (ta.scrollHeight + 2) + 'px';
  }

  var CSS = [
    '.st-root{max-width:1500px}',
    '.st-layout{display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap}',
    '.st-main{flex:1 1 640px;min-width:0}',
    '.st-side{flex:1 1 330px;max-width:420px;min-width:290px;position:sticky;top:8px;max-height:calc(100vh - 16px);overflow-y:auto}',
    '@media (max-width:1100px){.st-side{position:static;max-width:none;max-height:none;overflow:visible;flex-basis:100%}}',
    '.st-side .card{margin-bottom:12px}',
    '.st-head h2{margin:0 0 4px}',
    '.st-head .st-meta{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;margin:6px 0 10px}',
    '.st-bar{position:sticky;top:0;z-index:6;background:var(--c-card);border:1px solid var(--c-border);border-radius:var(--radius);box-shadow:var(--shadow);padding:8px 12px;margin-bottom:16px}',
    '.st-bar .row{gap:10px}',
    '.st-dirty{color:var(--c-warn);font-weight:600}',
    '.st-saved{color:var(--c-ok)}',
    '.st-sec-h{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:4px}',
    '.st-sec-h h3{margin:0;font-size:16px}',
    '.st-req{color:var(--c-err);font-size:12px;border:1px solid var(--c-err);border-radius:8px;padding:0 6px;margin-left:6px;font-weight:400}',
    '.st-help{color:var(--c-muted);font-size:13px;margin:0 0 10px}',
    '.st-ro{white-space:pre-wrap;word-break:break-word;line-height:1.6}',
    '.st-ta1{min-height:32px;padding:5px 8px;resize:none;overflow:hidden;line-height:1.45}',
    '.st-invalid{border-color:var(--c-err)!important;background:var(--c-err-soft)!important}',
    '.st-tbl{width:100%;border-collapse:collapse}',
    '.st-tbl th,.st-tbl td{padding:5px 6px;border-bottom:1px solid var(--c-border);vertical-align:top;text-align:left}',
    '.st-tbl th{font-size:12.5px;color:var(--c-muted);background:var(--c-hover);font-weight:600;white-space:nowrap}',
    '.st-tbl td.st-ix{color:var(--c-muted);width:28px;text-align:center;font-size:12px;padding-top:11px}',
    '.st-tbl td.st-ops{white-space:nowrap;width:1%}',
    '.st-tbl .input,.st-tbl .select,.st-tbl .textarea{width:100%;box-sizing:border-box;margin:0}',
    '.st-tbl .st-n{text-align:center;padding-left:4px;padding-right:4px}',
    '.st-tbl input[type=number]::-webkit-inner-spin-button,.st-tbl input[type=number]::-webkit-outer-spin-button{-webkit-appearance:none;margin:0}',
    '.st-tbl input[type=number]{-moz-appearance:textfield}',
    '.st-tbl tr.st-high td{background:var(--c-err-soft)}',
    '.st-tbl td.st-rpn{text-align:center;font-weight:700;white-space:nowrap}',
    '.st-best{background:var(--c-ok-soft)!important;color:var(--c-ok)!important;font-weight:700}',
    '.st-total td{font-weight:700;border-top:2px solid var(--c-border)}',
    '.st-legend{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:12px;color:var(--c-muted);margin:6px 0}',
    '.st-sw{display:inline-block;width:12px;height:12px;border-radius:3px;vertical-align:-1px;margin-right:4px;border:1px solid var(--c-border)}',
    '.st-fgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:0 16px}',
    '.st-fgrid .st-wide{grid-column:1/-1}',
    '.st-ck{padding:10px 0;border-bottom:1px solid var(--c-border)}',
    '.st-ck:last-child{border-bottom:0}',
    '.st-ck-top{display:flex;flex-wrap:wrap;gap:8px 12px;align-items:flex-start}',
    '.st-seg{display:inline-flex;flex:0 0 auto}',
    '.st-seg .btn{border-radius:0;margin-left:-1px}',
    '.st-seg .btn:first-child{border-radius:6px 0 0 6px;margin-left:0}',
    '.st-seg .btn:last-child{border-radius:0 6px 6px 0}',
    '.st-seg .btn.on-todo{background:var(--c-hover);border-color:var(--c-muted);font-weight:600}',
    '.st-seg .btn.on-done{background:var(--c-ok);border-color:var(--c-ok);color:#fff}',
    '.st-seg .btn.on-na{background:var(--c-warn);border-color:var(--c-warn);color:#fff}',
    '.st-ck-text{flex:1 1 260px;min-width:0}',
    '.st-ck-warn{color:var(--c-err);font-size:12.5px;margin-top:4px}',
    '.st-gate ul{margin:4px 0 0;padding-left:20px}',
    '.st-gate .st-act{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}',
    '.st-rev{border-top:1px solid var(--c-border);padding:8px 0;font-size:13px}',
    '.st-rev:first-child{border-top:0}',
    '.st-li{display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center;padding:7px 0;border-top:1px solid var(--c-border)}',
    '.st-li:first-child{border-top:0}',
    '.st-mono{font-family:var(--mono);font-size:12px}',
    '.st-card-h{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:8px}',
    '.st-card-h h3{margin:0;font-size:16px}',
    '.st-details>summary{cursor:pointer;font-weight:600;font-size:16px}',
    '.st-details[open]>summary{margin-bottom:8px}',
    '.st-kb{border-top:1px solid var(--c-border);padding:6px 0}',
    '.st-kb>summary{cursor:pointer;font-size:14px}',
    '.st-kb .st-ro{padding:6px 0 4px 4px;font-size:13px}',
    '.st-wrapx{overflow-x:auto}',
    '.st-ch{font-size:12px;color:var(--c-muted);border:1px solid var(--c-border);border-radius:8px;padding:0 7px;white-space:nowrap}',
    '.st-sample-tag{display:inline-block;font-size:12px;font-weight:600;border:1px solid var(--c-warn);color:var(--c-warn);background:rgba(217,119,6,.12);border-radius:8px;padding:0 7px;white-space:nowrap}',
    '.st-sample{background:rgba(217,119,6,.16)!important;border-color:var(--c-warn)!important}',
    '.st-ro.st-sample{border-radius:4px;padding:1px 4px}'
  ].join('\n');
  function injectCss() {
    if (document.getElementById('mf-stage-css')) return;
    var s = document.createElement('style');
    s.id = 'mf-stage-css';
    s.textContent = CSS;
    document.head.appendChild(s);
  }

  /* ================================================================== modal form helper */
  /* opt: {title, intro(Node), fields:[{key,label,type:'text'|'textarea',required,placeholder,hint}], okLabel, danger, initial, width}
     returns Promise<values|null> */
  function formModal(opt) {
    var inputs = {};
    var body = H('div', null, opt.intro || null);
    opt.fields.forEach(function (f) {
      var el = f.type === 'textarea'
        ? H('textarea', { class: 'textarea', rows: f.rows || 3, placeholder: f.placeholder || '' })
        : H('input', { class: 'input', type: 'text', placeholder: f.placeholder || '' });
      el.value = S((opt.initial || {})[f.key]);
      inputs[f.key] = el;
      body.appendChild(H('div', { class: 'field' },
        H('label', null, f.label, f.required ? H('span', { class: 'req' }, '*') : null), el,
        f.hint ? H('div', { class: 'hint' }, f.hint) : null));
    });
    return MF.modal({
      title: opt.title, body: body, width: opt.width || 520,
      buttons: [{ label: '取消', value: null }, {
        label: opt.okLabel || '确定', kind: opt.danger ? 'danger' : 'primary',
        onClick: function (ctl) {
          var vals = {};
          for (var i = 0; i < opt.fields.length; i++) {
            var f = opt.fields[i];
            vals[f.key] = inputs[f.key].value.trim();
            if (f.required && !vals[f.key]) { ctl.error('请填写：' + f.label); inputs[f.key].focus(); return false; }
          }
          ctl.close(vals);
          return false;
        }
      }]
    });
  }

  /* ================================================================== data model */
  function defaultValue(sec) {
    switch (sec.type) {
      case 'text': return '';
      case 'fields': return {};
      case 'matrix': return { options: [], selected: '', criteria: [] };
      default: return [];
    }
  }
  function normValue(sec, v) {
    if (v === null || v === undefined) return defaultValue(sec);
    v = clone(v);
    switch (sec.type) {
      case 'text': return typeof v === 'string' ? v : S(v);
      case 'fields': return (v && typeof v === 'object' && !Array.isArray(v)) ? v : {};
      case 'table': case 'fmea':
        return Array.isArray(v) ? v.filter(function (r) { return r && typeof r === 'object'; }) : [];
      case 'matrix': {
        if (!v || typeof v !== 'object' || Array.isArray(v)) return defaultValue(sec);
        if (!Array.isArray(v.options)) v.options = [];
        if (!Array.isArray(v.criteria)) v.criteria = [];
        v.options = v.options.map(S);
        v.selected = S(v.selected);
        v.criteria = v.criteria.filter(function (c) { return c && typeof c === 'object'; }).map(function (c) {
          if (!c.scores || typeof c.scores !== 'object') c.scores = {};
          c.name = S(c.name);
          return c;
        });
        return v;
      }
      default: return v;
    }
  }
  function sectionFilled(sec, val) {
    var t = sec.type;
    if (t === 'text') return !isBlank(val);
    if (t === 'fields') {
      var req = (sec.fields || []).filter(function (f) { return f.required; });
      if (req.length) return req.every(function (f) { return !isBlank((val || {})[f.key]); });
      return !isBlank(val);
    }
    if (t === 'table' || t === 'fmea') {
      var rows = (val || []).filter(function (r) { return !isBlank(r); });
      return rows.length >= (t === 'table' ? Math.max(1, sec.min_rows || 1) : 1);
    }
    if (t === 'matrix') {
      var m = val || {};
      return !!m.selected && (m.criteria || []).some(function (c) {
        return Object.keys(c.scores || {}).some(function (k) { return !!c.scores[k]; });
      });
    }
    return false;
  }

  function initWork(ctx) {
    var d = ctx.detail, data = d.data || {};
    var secs = data.sections || {}, cl = data.checklist || {};
    ctx.work = { sections: {}, checklist: {}, planned_start: d.planned_start || '', planned_end: d.planned_end || '' };
    ctx.base = { sections: {}, checklist: {}, planned_start: d.planned_start || '', planned_end: d.planned_end || '' };
    ((d.def && d.def.sections) || []).forEach(function (sec) {
      var v = normValue(sec, secs[sec.key]);
      ctx.work.sections[sec.key] = v;
      ctx.base.sections[sec.key] = jstr(v);
    });
    ((d.def && d.def.checklist) || []).forEach(function (c) {
      var it = cl[c.key] || {};
      var v = { status: it.status || 'todo', note: S(it.note) };
      ctx.work.checklist[c.key] = v;
      ctx.base.checklist[c.key] = jstr(v);
    });
  }
  function changes(ctx) {
    var out = { sections: {}, checklist: {}, planned: {}, any: false };
    Object.keys(ctx.work.sections).forEach(function (k) {
      if (jstr(ctx.work.sections[k]) !== ctx.base.sections[k]) { out.sections[k] = ctx.work.sections[k]; out.any = true; }
    });
    Object.keys(ctx.work.checklist).forEach(function (k) {
      if (jstr(ctx.work.checklist[k]) !== ctx.base.checklist[k]) { out.checklist[k] = ctx.work.checklist[k]; out.any = true; }
    });
    ['planned_start', 'planned_end'].forEach(function (k) {
      if (ctx.work[k] !== ctx.base[k]) { out.planned[k] = ctx.work[k]; out.any = true; }
    });
    return out;
  }
  function isDirty(ctx) { return changes(ctx).any; }

  function api(ctx, suffix) { return '/api/methods/' + ctx.mid + '/stages/' + encodeURIComponent(ctx.key) + (suffix || ''); }

  /* ================================================================== entry point */
  MF.renderStage = function (container, mid, key, method) {
    injectCss();
    var ctx = {
      container: container, mid: mid, key: key, method: method || {}, detail: null, work: null, base: null,
      el: {}, autos: [], syncers: [], ui: { fmeaSort: {} }, checks: null, savedAt: null, saving: false, conflict: '',
      verified: {}, kb: null, root: null
    };
    MF.clear(container);
    container.appendChild(MF.loading ? MF.loading('正在加载阶段……') : H('div', { class: 'empty' }, '加载中……'));
    return MF.api('GET', api(ctx)).then(function (d) {
      ctx.detail = d;
      ctx.checks = d.checks || { blocks: [], warns: [] };
      initWork(ctx);
      build(ctx);
      loadKb(ctx);
    }, function (e) {
      if (e && e.status === 401) return;
      MF.clear(container);
      container.appendChild(MF.errorBox ? MF.errorBox(e, function () { MF.renderStage(container, mid, key, method); })
        : H('div', { class: 'callout callout-err' }, errText(e)));
    });
  };

  function changedProject(ctx) {
    if (typeof MF.reload === 'function') return MF.reload();
    return MF.renderStage(ctx.container, ctx.mid, ctx.key, ctx.method);
  }

  /* ================================================================== 上一步 / 下一步（标准流程导航） */
  function stepNav(ctx) {
    var list = (ctx.method && ctx.method.stages) || [];
    var i = -1;
    list.forEach(function (s, k) { if (s.key === ctx.key) i = k; });
    var wrap = H('div', { class: 'card', style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', flexWrap: 'wrap', marginTop: '14px' } });
    if (i < 0) return wrap;
    var prev = list[i - 1], next = list[i + 1];
    var cur = list[i];
    var mid = ctx.mid;
    wrap.appendChild(prev ? H('a', { class: 'btn', href: '#/m/' + mid + '/stage/' + prev.key }, '← 上一步：' + S(prev.title)) : H('span'));
    var locked = ctx.detail && (ctx.detail.status === 'approved' || ctx.detail.status === 'completed') && !ctx.detail.stale;
    var msg = H('span', { class: 'small muted' }, '第 ' + S(cur.ord) + ' / ' + list.length + ' 步');
    wrap.appendChild(msg);
    if (!next) wrap.appendChild(H('a', { class: 'btn btn-primary', href: '#/m/' + mid + '/docs' }, locked ? '全部完成 → 生成文档' : '最后一步：完成后可生成文档'));
    else if (locked) wrap.appendChild(H('a', { class: 'btn btn-primary', href: '#/m/' + mid + '/stage/' + next.key }, '下一步：' + S(next.title) + ' →'));
    else wrap.appendChild(H('span', { class: 'small muted', title: '本步骤通过（或已完成）后才能进入下一步' }, '🔒 本步骤通过后开放下一步：' + S(next.title)));
    return wrap;
  }

  /* ================================================================== page skeleton */
  function build(ctx) {
    MF.clear(ctx.container);
    ctx.autos = []; ctx.syncers = [];
    var root = H('div', { class: 'st-root' });
    ctx.root = root;
    ctx.el = {
      header: H('div'), banner: H('div'), bar: H('div', { class: 'st-bar' }), sections: H('div'), checklist: H('div'), exps: H('div'),
      atts: H('div'), kb: H('div'), revs: H('div'), gate: H('div')
    };
    var main = H('div', { class: 'st-main' }, ctx.el.bar, ctx.el.sections, ctx.el.checklist, ctx.el.exps, ctx.el.atts, ctx.el.kb, ctx.el.revs);
    var side = H('div', { class: 'st-side' }, ctx.el.gate);
    root.appendChild(ctx.el.header);
    root.appendChild(ctx.el.banner);
    if (MF.guide && MF.guide.stagePanel) root.appendChild(MF.guide.stagePanel(ctx.key));
    root.appendChild(H('div', { class: 'st-layout' }, main, side));
    root.appendChild(stepNav(ctx));
    ctx.container.appendChild(root);
    renderHeader(ctx);
    renderBanner(ctx);
    renderBar(ctx);
    renderSections(ctx);
    renderChecklist(ctx);
    renderGate(ctx);
    renderExps(ctx);
    renderAtts(ctx);
    renderKb(ctx);
    renderRevs(ctx);
    afterMount(ctx);
    bindGlobal(ctx);
    touch(ctx);
  }
  function afterMount(ctx) {
    requestAnimationFrame(function () { ctx.autos.forEach(autosize); });
  }
  function mkTA(ctx, cls, ph) {
    var ta = H('textarea', { class: (cls || 'textarea') + ' st-auto', rows: 1, placeholder: ph || '' });
    ctx.autos.push(ta);
    requestAnimationFrame(function () { autosize(ta); });
    return ta;
  }
  function bindGlobal(ctx) {
    if (ctx.bound) return;
    ctx.bound = true;
    function onKey(ev) {
      if (!ctx.root || !document.body.contains(ctx.root)) { document.removeEventListener('keydown', onKey, true); return; }
      if ((ev.ctrlKey || ev.metaKey) && (ev.key === 's' || ev.key === 'S')) {
        ev.preventDefault();
        if (!ctx.detail.editable) return;
        if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
        save(ctx);
      }
    }
    document.addEventListener('keydown', onKey, true);
  }

  /* touch: called on every local edit */
  function touch(ctx) {
    ctx.syncers.forEach(function (f) { try { f(); } catch (e) { /* ignore */ } });
    var dirty = isDirty(ctx);
    if (MF.dirtyGuard) MF.dirtyGuard.set(dirty);
    renderBarStatus(ctx, dirty);
    renderInvalid(ctx);
    if (ctx.el.gate && ctx.gateNote) ctx.gateNote.hidden = !dirty;
  }
  function renderInvalid(ctx) {
    var box = ctx.invalidBox;
    if (!box) return;
    var pr = ctx.detail.editable ? sodProblems(ctx) : [];
    MF.clear(box);
    box.hidden = !pr.length;
    if (!pr.length) return;
    box.appendChild(H('div', null, H('strong', null, '无法保存：'), 'FMEA 的 S（严重度）/ O（发生度）/ D（可检测度）必须是 1–10 的整数（可留空）。请先修正标红的输入框：' + pr.join('；') + '。'));
  }

  /* ================================================================== header */
  function renderHeader(ctx) {
    var d = ctx.detail, el = ctx.el.header;
    MF.clear(el);
    var def = d.def || {}, gate = def.gate;
    var meta = H('div', { class: 'st-meta' },
      MF.statusBadge ? MF.statusBadge(d.status, d.status_label, d.stale) : badge(d.status_label || d.status, 'info'),
      H('span', { class: 'muted small' }, '修订 R' + S(d.revision)),
      H('span', { class: 'muted small' }, '进度 ' + S(d.progress) + '%'),
      gate ? H('span', { class: 'small' }, badge(gate.name || gate.key, 'info'), ' 需签署：',
        (gate.roles || []).map(roleLabel).join(' → ')) : H('span', { class: 'muted small' }, '无复核门（提交后直接完成）'));
    var dates;
    if (d.editable) {
      var ps = H('input', { class: 'input input-sm', type: 'date', style: { width: '150px' } });
      var pe = H('input', { class: 'input input-sm', type: 'date', style: { width: '150px' } });
      ps.value = ctx.work.planned_start; pe.value = ctx.work.planned_end;
      ps.addEventListener('input', function () { ctx.work.planned_start = ps.value; touch(ctx); });
      pe.addEventListener('input', function () { ctx.work.planned_end = pe.value; touch(ctx); });
      dates = H('span', { class: 'row small', style: { gap: '6px' } }, '计划：', ps, '至', pe);
    } else {
      dates = H('span', { class: 'small' }, '计划：' + fdate(d.planned_start) + ' 至 ' + fdate(d.planned_end));
    }
    var extras = H('div', { class: 'st-meta' }, dates,
      d.actual_start ? H('span', { class: 'muted small' }, '实际开始 ' + fdate(d.actual_start)) : null,
      d.actual_end ? H('span', { class: 'muted small' }, '实际完成 ' + fdate(d.actual_end)) : null,
      H('span', { class: 'muted small' }, '编辑者：' + ((d.editor_names && d.editor_names.length) ? d.editor_names.join('、') : '暂无')),
      (d.contributors_names && d.contributors_names.length) ? H('span', { class: 'muted small', title: '保存、提交、编辑实验或上传附件的人，永不得复核/批准本阶段' }, '贡献者：' + d.contributors_names.join('、')) : null);
    var notes = [];
    var meth = ctx.method || {}, proj = meth.project || {};
    var M_ST = { completed: '已完成', archived: '已归档', cancelled: '已取消' };
    var P_ST = { paused: '暂停', completed: '已完成', archived: '已归档' };
    if (meth.status && meth.status !== 'active') {
      notes.push(H('div', { class: 'callout callout-warn' }, '方法状态为“' + (M_ST[meth.status] || meth.status) + '”，阶段不可编辑。'));
    } else if (proj.status && proj.status !== 'active') {
      notes.push(H('div', { class: 'callout callout-warn' }, '所属项目状态为“' + (P_ST[proj.status] || proj.status) + '”，在项目恢复为“进行中”之前阶段不可编辑。'));
    } else if (d.blocked_by && d.blocked_by.length) {
      notes.push(H('div', { class: 'callout callout-warn' }, H('strong', null, '本步骤尚未开放：'),
        '标准流程要求按顺序进行，请先完成并通过 ' + d.blocked_by.map(function (b) { return '第 ' + b.step + ' 步“' + b.title + '”'; }).join('、') + ' 后再填写。当前为只读预览，可先阅读本步骤的指引。'));
    } else if (!d.editable) {
      var why;
      if (d.status === 'in_review') why = '本阶段正在等待复核，内容已锁定。如需修改，请由方法负责人/开发人员先“撤回”。';
      else if (d.status === 'approved' || d.status === 'completed') why = '本阶段已' + (d.status === 'approved' ? '通过' : '完成') + '并锁定，内容只读。如需修改，请由方法负责人或批准人“重新打开”。';
      else why = '您在本方法中没有编辑权限（仅方法负责人/开发人员可编辑），当前为只读视图。';
      notes.push(H('div', { class: 'callout' }, why));
    }
    if (d.signatures_ok === false) {
      notes.push(H('div', { class: 'callout callout-err' }, H('strong', null, '签名完整性校验失败：'),
        '已批准内容与签署时的哈希不一致，数据可能被绕过系统改动。请立即通知管理员/QA，并勿将生成的文档用作批准文件。',
        (d.signature_problems && d.signature_problems.length) ? H('ul', { style: { margin: '4px 0 0 18px', padding: 0 } }, d.signature_problems.map(function (x) { return H('li', null, S(x)); })) : null));
    }
    if (d.stale) {
      notes.push(H('div', { class: 'callout callout-warn' }, H('strong', null, '本阶段已失效：'),
        '前置阶段被重新打开，已有的复核/批准不再有效。请核对内容后“重新确认”并重新复核。'));
    }
    if (d.status === 'returned') {
      var rej = lastReject(d);
      notes.push(H('div', { class: 'callout callout-err' }, H('strong', null, '已被退回：'),
        rej ? (S(rej.display_name) + '（' + S(rej.role_label) + '）：' + S(rej.comment || '（未写意见）')) : '请按退回意见修改后重新提交。'));
    }
    el.appendChild(H('div', { class: 'card st-head' },
      H('h2', null, S(d.title || (d.def && d.def.title) || ctx.key)),
      def.desc ? H('div', { class: 'muted' }, S(def.desc)) : null,
      meta, extras, notes));
  }
  function lastReject(d) {
    var r = (d.reviews || []).filter(function (x) { return x.decision === 'reject'; });
    return r.length ? r[r.length - 1] : null;
  }

  /* stage-level gate warns that mention example values: shown prominently (not blocking) */
  function renderBanner(ctx) {
    var el = ctx.el.banner;
    if (!el) return;
    MF.clear(el);
    var ws = ((ctx.checks && ctx.checks.warns) || []).filter(function (w) { return S(w).indexOf('示例值') >= 0; });
    if (!ws.length) return;
    el.appendChild(H('div', { class: 'callout callout-warn', style: { margin: '0 0 12px' } },
      H('strong', null, '仍含示例值（不阻断提交）：'),
      H('ul', null, ws.map(function (w) { return H('li', null, S(w)); })),
      H('div', { class: 'small' }, '带“' + SAMPLE_MARK + '”标记的判据/数值只是预置示例（章节旁有琥珀色标记），请按 ATP 确认或修改后删去标记，再生成方案/报告。')));
  }

  /* ================================================================== save bar */
  function renderBar(ctx) {
    var d = ctx.detail, el = ctx.el.bar;
    MF.clear(el);
    ctx.barStatus = H('span', { class: 'small' });
    ctx.saveBtn = H('button', { type: 'button', class: 'btn btn-primary', hidden: !d.editable, title: 'Ctrl+S', onclick: function () { save(ctx); } }, '保存');
    ctx.discardBtn = H('button', { type: 'button', class: 'btn btn-sm', hidden: true, onclick: function () { discard(ctx); } }, '放弃修改');
    ctx.conflictBox = H('div', { class: 'callout callout-err', hidden: true, style: { margin: '8px 0 0' } });
    ctx.invalidBox = H('div', { class: 'callout callout-err', hidden: true, role: 'alert', style: { margin: '8px 0 0' } });
    el.appendChild(H('div', { class: 'row' }, ctx.saveBtn, ctx.discardBtn, ctx.barStatus,
      H('span', { class: 'spacer' }),
      ctx.verLabel = H('span', { class: 'muted small' }, '版本 v' + S(d.version))));
    el.appendChild(ctx.conflictBox);
    el.appendChild(ctx.invalidBox);
    renderConflict(ctx);
    renderBarStatus(ctx, false);
  }
  function renderConflict(ctx) {
    var box = ctx.conflictBox;
    if (!box) return;
    MF.clear(box);
    box.hidden = !ctx.conflict;
    if (!ctx.conflict) return;
    box.appendChild(H('div', null, H('strong', null, '保存失败：'), ctx.conflict));
    box.appendChild(H('div', { style: { marginTop: '6px' } },
      H('button', { type: 'button', class: 'btn btn-sm btn-primary', onclick: function () { reloadServer(ctx); } }, '重新加载（放弃我的未保存修改）'),
      ' ', H('span', { class: 'muted small' }, '提示：可先复制需要保留的内容，再重新加载。')));
  }
  function renderBarStatus(ctx, dirty) {
    if (!ctx.barStatus) return;
    var d = ctx.detail;
    MF.clear(ctx.barStatus);
    if (!d.editable) {
      ctx.barStatus.appendChild(H('span', { class: 'muted' }, '只读'));
    } else if (ctx.saving) {
      ctx.barStatus.appendChild(H('span', { class: 'muted' }, '正在保存……'));
    } else if (dirty) {
      ctx.barStatus.appendChild(H('span', { class: 'st-dirty' }, '● 有未保存的修改'));
    } else if (ctx.savedAt) {
      ctx.barStatus.appendChild(H('span', { class: 'st-saved' }, '✓ 已保存 ' + ctx.savedAt));
    } else {
      ctx.barStatus.appendChild(H('span', { class: 'muted' }, '最后更新 ' + fdt(d.updated_at)));
    }
    if (ctx.verLabel) ctx.verLabel.textContent = '版本 v' + S(d.version);
    if (ctx.saveBtn) ctx.saveBtn.disabled = !d.editable || ctx.saving;
    if (ctx.discardBtn) ctx.discardBtn.hidden = !(d.editable && dirty);
  }

  function reloadServer(ctx) {
    return MF.api('GET', api(ctx)).then(function (d) {
      ctx.detail = d; ctx.checks = d.checks || { blocks: [], warns: [] }; ctx.conflict = ''; ctx.savedAt = null;
      initWork(ctx);
      build(ctx);
      if (MF.dirtyGuard) MF.dirtyGuard.set(false);
    }, function (e) { toast(errText(e), 'err'); });
  }
  async function discard(ctx) {
    var ok = await MF.confirm('放弃所有未保存的修改，恢复到上次保存的内容？', { danger: true, okLabel: '放弃修改' });
    if (ok) reloadServer(ctx);
  }

  function countInvalid(ctx) { return ctx.root ? ctx.root.querySelectorAll('.st-invalid').length : 0; }

  async function save(ctx) {
    if (ctx.saving) return false;
    var ch = changes(ctx);
    if (!ch.any) { toast('没有需要保存的修改', 'warn'); return true; }
    var sodBad = sodProblems(ctx);
    if (sodBad.length) {
      renderInvalid(ctx);
      toast('未保存：FMEA 的 S/O/D 须为 1–10 的整数（' + sodBad.slice(0, 3).join('；') + (sodBad.length > 3 ? ' 等 ' + sodBad.length + ' 处' : '') + '）', 'err');
      var bad = ctx.root && ctx.root.querySelector('.st-invalid');
      if (bad) { try { bad.scrollIntoView({ block: 'center' }); bad.focus(); } catch (e) { /* ignore */ } }
      return false;
    }
    var payload = { version: ctx.detail.version };
    if (Object.keys(ch.sections).length) payload.sections = ch.sections;
    if (Object.keys(ch.checklist).length) payload.checklist = ch.checklist;
    Object.keys(ch.planned).forEach(function (k) { payload[k] = ch.planned[k]; });
    if (MF.state.app && MF.state.app.require_change_reason && (ctx.detail.revision > 1 || ctx.detail.status === 'returned') && (payload.sections || payload.checklist)) {
      var rsn = await askChangeReason();
      if (!rsn) return false;
      payload.reason = rsn;
    }
    var sent = { sections: {}, checklist: {}, planned: ch.planned };
    Object.keys(ch.sections).forEach(function (k) { sent.sections[k] = jstr(ch.sections[k]); });
    Object.keys(ch.checklist).forEach(function (k) { sent.checklist[k] = jstr(ch.checklist[k]); });
    ctx.saving = true; renderBarStatus(ctx, true);
    try {
      var res = await MF.api('PUT', api(ctx), payload);
      Object.keys(sent.sections).forEach(function (k) { ctx.base.sections[k] = sent.sections[k]; });
      Object.keys(sent.checklist).forEach(function (k) { ctx.base.checklist[k] = sent.checklist[k]; });
      Object.keys(sent.planned).forEach(function (k) { ctx.base[k] = sent.planned[k]; });
      ctx.detail = res; ctx.checks = res.checks || ctx.checks;
      ctx.conflict = ''; ctx.savedAt = nowClock();
      ctx.saving = false;
      renderConflict(ctx);
      renderHeader(ctx); renderGate(ctx); renderRevs(ctx); renderExps(ctx); renderAtts(ctx);
      touch(ctx);
      var bad = countInvalid(ctx);
      toast(bad ? ('已保存，但仍有 ' + bad + ' 处输入不在有效范围') : '已保存', bad ? 'warn' : 'ok');
      refreshChecks(ctx, true);
      return true;
    } catch (e) {
      ctx.saving = false;
      if (e && e.status === 409) {
        ctx.conflict = errText(e);
        renderConflict(ctx);
        toast(errText(e), 'err');
      } else if (!(e && e.status === 401)) {
        toast('保存失败：' + errText(e), 'err');
      }
      touch(ctx);
      return false;
    }
  }

  /* ---------------------------------------------------------------- revision comparison (what changed since the last submission) */
  function diffVal(v) {
    if (v === null || v === undefined || v === '') return '（空）';
    if (typeof v === 'string') return v;
    if (Array.isArray(v)) return v.map(function (x) { return typeof x === 'string' ? x : JSON.stringify(x); }).join('；');
    return JSON.stringify(v);
  }
  function rowText(r) {
    if (!r) return '（无）';
    if (typeof r !== 'object') return String(r);
    return Object.keys(r).filter(function (k) { return r[k] !== '' && r[k] !== null && r[k] !== undefined; })
      .map(function (k) { return k + ': ' + (typeof r[k] === 'object' ? JSON.stringify(r[k]) : r[k]); }).join(' | ');
  }
  async function showDiff(ctx) {
    var res;
    try { res = await MF.api('GET', api(ctx, '/diff')); } catch (e) { toast(errText(e), 'err'); return; }
    var body = H('div', { style: { maxHeight: '65vh', overflowY: 'auto' } });
    if (!res.from) {
      body.appendChild(H('div', { class: 'callout' }, S(res.note) || '没有可比较的修订'));
    } else {
      body.appendChild(H('p', { class: 'muted small' }, '修订 R' + res.from + ' → 修订 R' + res.to + '：' + (res.changes.length ? res.changes.length + ' 个章节有改动' : '章节内容无改动')));
      res.changes.forEach(function (c) {
        var card = H('div', { class: 'card', style: { marginBottom: '8px', padding: '10px' } }, H('strong', null, S(c.title)));
        if (c.rows) {
          c.rows.forEach(function (r) {
            card.appendChild(H('div', { class: 'small', style: { marginTop: '6px' } }, H('span', { class: 'muted' }, '第 ' + r.row + ' 行'),
              H('div', { style: { color: 'var(--c-err,#c0392b)', textDecoration: r.new ? 'line-through' : 'none' } }, '− ' + rowText(r.old)),
              H('div', { style: { color: 'var(--c-ok,#0b7a4b)' } }, '+ ' + rowText(r.new))));
          });
        } else if (c.fields) {
          c.fields.forEach(function (f) {
            card.appendChild(H('div', { class: 'small', style: { marginTop: '6px' } }, H('span', { class: 'muted' }, S(f.key) + '：'),
              H('div', { style: { color: 'var(--c-err,#c0392b)' } }, '− ' + diffVal(f.old)), H('div', { style: { color: 'var(--c-ok,#0b7a4b)' } }, '+ ' + diffVal(f.new))));
          });
        } else {
          card.appendChild(H('div', { class: 'small', style: { marginTop: '6px', whiteSpace: 'pre-wrap' } },
            H('div', { style: { color: 'var(--c-err,#c0392b)' } }, '− ' + diffVal(c.old)), H('div', { style: { color: 'var(--c-ok,#0b7a4b)' } }, '+ ' + diffVal(c.new))));
        }
        body.appendChild(card);
      });
      if ((res.checklist_changed || []).length) {
        body.appendChild(H('div', { class: 'callout', style: { marginTop: '6px' } }, H('strong', null, '检查清单有变化（' + res.checklist_changed.length + ' 项）：'),
          H('ul', null, res.checklist_changed.slice(0, 15).map(function (t) { return H('li', null, S(t)); }))));
      }
    }
    await MF.modal({ title: '与上一修订的对比', body: body, width: 760, buttons: [{ label: '关闭', kind: 'primary', value: true }] });
  }

  function askChangeReason() {
    var ta = H('textarea', { class: 'textarea', rows: 3, placeholder: '这次修改的原因（必填，记入审计）' });
    return MF.modal({ title: '修改原因', width: 520, body: H('div', null, H('p', { class: 'small muted' }, '该阶段已被退回或重新打开过，修改内容须写明原因。'), ta),
      buttons: [{ label: '取消', value: null }, { label: '保存', kind: 'primary', onClick: function (ctl) {
        if (!ta.value.trim()) { ctl.error('请填写修改原因'); ctl.setBusy(false); return false; }
        ctl.close(ta.value.trim());
      } }] });
  }

  async function confirmSection(ctx, sec) {
    var ok = await MF.confirm('请确认：您已逐项核对“' + S(sec.title) + '”中的预置内容，并已按本产品改为真实内容（不再含“示例值”标记）。确认后本节计为已填写，并写入审计记录。');
    if (!ok) return;
    if (isDirty(ctx)) { var saved = await save(ctx); if (!saved) return; }
    try {
      var res = await MF.api('PUT', api(ctx), { version: ctx.detail.version, confirm_sections: [sec.key] });
      ctx.detail = res; ctx.checks = res.checks || ctx.checks;
      touch(ctx); renderGate(ctx); renderBanner(ctx); renderHeader(ctx);
      toast('已确认：' + S(sec.title), 'ok');
      if (typeof MF.reload === 'function') MF.reload();
    } catch (e) {
      if (!(e && e.status === 401)) toast(errText(e), 'err');
    }
  }

  function refreshChecks(ctx, quiet) {
    return MF.api('GET', api(ctx, '/checks')).then(function (c) {
      ctx.checks = c; renderGate(ctx); renderBanner(ctx);
    }, function (e) { if (!quiet) toast(errText(e), 'err'); });
  }

  /* ================================================================== sections */
  function renderSections(ctx) {
    var el = ctx.el.sections;
    MF.clear(el);
    var ro = !ctx.detail.editable;
    ((ctx.detail.def && ctx.detail.def.sections) || []).forEach(function (sec) {
      el.appendChild(sectionCard(ctx, sec, ro));
    });
  }
  function sectionCard(ctx, sec, ro) {
    var filledBadge = H('span');
    function syncFilled() {
      MF.clear(filledBadge);
      var ok = sectionFilled(sec, ctx.work.sections[sec.key]);
      if (sec.required || ok) filledBadge.appendChild(badge(ok ? '已填写' : '未填写', ok ? 'ok' : (sec.required ? 'warn' : 'muted')));
    }
    ctx.syncers.push(syncFilled);
    var body;
    switch (sec.type) {
      case 'text': body = buildText(ctx, sec, ro); break;
      case 'fields': body = buildFields(ctx, sec, ro); break;
      case 'table': body = buildTable(ctx, sec, ro); break;
      case 'matrix': body = buildMatrix(ctx, sec, ro); break;
      case 'fmea': body = buildFmea(ctx, sec, ro); break;
      default: body = H('div', { class: 'muted' }, '（暂不支持的章节类型：' + S(sec.type) + '）');
    }
    var sampleTag = H('span');
    function syncSample() {
      MF.clear(sampleTag);
      var n = sampleCount(ctx.work.sections[sec.key]);
      if (n) sampleTag.appendChild(H('span', { class: 'st-sample-tag', title: '该章节仍含“' + SAMPLE_MARK + '”标记的示例判据/数值。请按 ATP 确认或修改，确认后删去标记。' },
        '含示例值 ×' + n + '，须按ATP确认'));
    }
    ctx.syncers.push(syncSample);
    syncSample();
    var uncEl = H('span', { style: { display: 'inline-flex', gap: '6px', alignItems: 'center' } });
    function syncUnc() {
      MF.clear(uncEl);
      var unc = ((ctx.detail && ctx.detail.data) || {}).unconfirmed || [];
      if (unc.indexOf(sec.key) < 0) return;
      uncEl.appendChild(badge('模板预置 · 待确认', 'warn'));
      if (ctx.detail.editable) {
        uncEl.appendChild(H('button', { type: 'button', class: 'btn btn-sm btn-primary', title: '逐项核对并改成本产品的真实内容后，点此确认',
          onclick: function () { confirmSection(ctx, sec); } }, '确认本节'));
      }
    }
    ctx.syncers.push(syncUnc);
    syncUnc();
    var chText = null;
    if (sec.ch && (sec.ch.plan || sec.ch.report)) {
      chText = [sec.ch.plan ? '方案 ' + sec.ch.plan : '', sec.ch.report ? '报告 ' + sec.ch.report : ''].filter(Boolean).join(' · ');
    }
    return H('div', { class: 'card', id: 'st-sec-' + sec.key },
      H('div', { class: 'st-sec-h' },
        chText ? H('span', { class: 'st-ch', title: '在受控文件（方案/报告）中的章号' }, chText) : null,
        H('h3', null, S(sec.title)), sec.required ? H('span', { class: 'st-req' }, '必填') : null, filledBadge, sampleTag, uncEl,
        (MF.records && MF.records.commentButton) ? MF.records.commentButton(ctx, sec) : null),
      sec.help ? H('div', { class: 'st-help' }, S(sec.help)) : null,
      body);
  }

  /* ---------------------------------------------------------------- text */
  function buildText(ctx, sec, ro) {
    var v = ctx.work.sections[sec.key];
    if (ro) return v ? H('div', { class: 'st-ro' + (hasSample(v) ? ' st-sample' : '') }, v) : H('div', { class: 'muted' }, '（未填写）');
    var ta = H('textarea', { class: 'textarea' + (hasSample(v) ? ' st-sample' : ''), placeholder: sec.placeholder || '', style: { overflow: 'hidden', minHeight: '84px' } });
    ta.value = v;
    ta.addEventListener('input', function () {
      ctx.work.sections[sec.key] = ta.value; ta.classList.toggle('st-sample', hasSample(ta.value)); autosize(ta); touch(ctx);
    });
    ctx.autos.push(ta);
    return ta;
  }

  /* ---------------------------------------------------------------- fields */
  function buildFields(ctx, sec, ro) {
    var val = ctx.work.sections[sec.key];
    var grid = H('div', { class: 'st-fgrid' });
    (sec.fields || []).forEach(function (f) {
      var cur = val[f.key];
      var control;
      if (ro) {
        control = S(cur) ? H('div', { class: 'st-ro' + (hasSample(cur) ? ' st-sample' : '') }, S(cur)) : H('div', { class: 'muted' }, '—');
      } else if (f.type === 'select') {
        control = H('select', { class: 'select' }, H('option', { value: '' }, '请选择'),
          (f.options || []).map(function (o) { return H('option', { value: o }, o); }));
        if (S(cur) && (f.options || []).indexOf(S(cur)) < 0) control.appendChild(H('option', { value: S(cur) }, S(cur)));
        control.value = S(cur);
        control.addEventListener('change', function () { val[f.key] = control.value; touch(ctx); });
      } else if (f.type === 'textarea') {
        control = H('textarea', { class: 'textarea', style: { minHeight: '60px', overflow: 'hidden' } });
        control.value = S(cur);
        control.addEventListener('input', function () { val[f.key] = control.value; autosize(control); touch(ctx); });
        ctx.autos.push(control);
      } else {
        var t = f.type === 'number' ? 'number' : f.type === 'date' ? 'date' : 'text';
        control = H('input', { class: 'input', type: t, step: t === 'number' ? 'any' : null });
        control.value = S(cur);
        control.addEventListener('input', function () {
          if (t === 'number') { var n = num(control.value); val[f.key] = isNaN(n) ? '' : n; }
          else val[f.key] = control.value;
          touch(ctx);
        });
      }
      grid.appendChild(H('div', { class: 'field' + (f.type === 'textarea' ? ' st-wide' : '') },
        H('label', null, S(f.label), f.required ? H('span', { class: 'req' }, '*') : null),
        control,
        (!ro && f.hint) ? H('div', { class: 'hint' }, S(f.hint)) : null));
    });
    return grid;
  }

  /* ---------------------------------------------------------------- table */
  function moveItem(arr, i, dir) {
    var j = i + dir;
    if (j < 0 || j >= arr.length) return false;
    var t = arr[i]; arr[i] = arr[j]; arr[j] = t;
    return true;
  }
  function opBtn(label, title, fn, disabled) {
    return H('button', { type: 'button', class: 'btn btn-sm btn-ghost', title: title, disabled: !!disabled, 'aria-label': title, onclick: fn }, label);
  }
  function cellControl(ctx, col, row, onChange) {
    var cur = row[col.key];
    var el;
    if (col.type === 'select') {
      el = H('select', { class: 'select' }, H('option', { value: '' }, '—'),
        (col.options || []).map(function (o) { return H('option', { value: o }, o); }));
      if (S(cur) && (col.options || []).indexOf(S(cur)) < 0) el.appendChild(H('option', { value: S(cur) }, S(cur)));
      el.value = S(cur);
      el.addEventListener('change', function () { row[col.key] = el.value; onChange(); });
    } else if (col.type === 'number') {
      el = H('input', { class: 'input', type: 'number', step: 'any' });
      el.value = S(cur);
      el.addEventListener('input', function () { var n = num(el.value); row[col.key] = isNaN(n) ? '' : n; onChange(); });
    } else if (col.type === 'date') {
      el = H('input', { class: 'input', type: 'date' });
      el.value = S(cur);
      el.addEventListener('input', function () { row[col.key] = el.value; onChange(); });
    } else {
      el = mkTA(ctx, 'textarea st-ta1');
      el.value = S(cur);
      el.classList.toggle('st-sample', hasSample(cur));
      el.addEventListener('input', function () { row[col.key] = el.value; el.classList.toggle('st-sample', hasSample(el.value)); autosize(el); onChange(); });
    }
    return el;
  }

  function buildTable(ctx, sec, ro) {
    var rows = ctx.work.sections[sec.key];
    var cols = sec.columns || [];
    var wrap = H('div');
    var hint = H('div', { class: 'hint', style: { marginTop: '6px' } });
    function validCount() { return rows.filter(function (r) { return !isBlank(r); }).length; }
    function syncHint() {
      MF.clear(hint);
      var parts = [];
      if (sec.min_rows) {
        var n = validCount();
        hint.appendChild(H('span', { style: { color: n >= sec.min_rows ? 'var(--c-ok)' : 'var(--c-warn)' } },
          '至少需要 ' + sec.min_rows + ' 行有效内容（当前 ' + n + ' 行）'));
      }
    }
    ctx.syncers.push(syncHint);

    function render() {
      MF.clear(wrap);
      if (ro && !rows.length) { wrap.appendChild(H('div', { class: 'muted' }, '（暂无内容）')); wrap.appendChild(hint); return; }
      var head = H('tr', null, H('th', null, '#'),
        cols.map(function (c) { return H('th', { style: c.width ? { minWidth: Math.round(c.width * 0.75) + 'px' } : null }, S(c.label)); }),
        ro ? null : H('th', null, ''));
      var tbody = H('tbody');
      rows.forEach(function (row, i) {
        var tr = H('tr', null, H('td', { class: 'st-ix' }, String(i + 1)));
        cols.forEach(function (c) {
          if (ro) tr.appendChild(H('td', null, H('div', { class: 'st-ro' + (hasSample(row[c.key]) ? ' st-sample' : '') }, S(row[c.key]) || '—')));
          else tr.appendChild(H('td', null, cellControl(ctx, c, row, function () { touch(ctx); })));
        });
        if (!ro) {
          tr.appendChild(H('td', { class: 'st-ops' },
            opBtn('↑', '上移', function () { if (moveItem(rows, i, -1)) { render(); touch(ctx); } }, i === 0),
            opBtn('↓', '下移', function () { if (moveItem(rows, i, 1)) { render(); touch(ctx); } }, i === rows.length - 1),
            opBtn('✕', '删除此行', async function () {
              if (!isBlank(row)) {
                var ok = await MF.confirm('删除第 ' + (i + 1) + ' 行？', { danger: true, okLabel: '删除' });
                if (!ok) return;
              }
              rows.splice(i, 1); render(); touch(ctx);
            })));
        }
        tbody.appendChild(tr);
      });
      wrap.appendChild(H('div', { class: 'st-wrapx' }, H('table', { class: 'st-tbl' }, H('thead', null, head), tbody)));
      if (!rows.length) wrap.appendChild(H('div', { class: 'muted small', style: { padding: '8px 2px' } }, '还没有行，点击下方“添加一行”。'));
      if (!ro) {
        wrap.appendChild(H('div', { style: { marginTop: '8px' } },
          H('button', { type: 'button', class: 'btn btn-sm', onclick: function () {
            var r = {}; cols.forEach(function (c) { r[c.key] = ''; });
            rows.push(r); render(); touch(ctx);
            var inp = wrap.querySelector('tbody tr:last-child textarea, tbody tr:last-child input, tbody tr:last-child select');
            if (inp) inp.focus();
          } }, '＋ 添加一行')));
      }
      wrap.appendChild(hint);
      syncHint();
    }
    render();
    return wrap;
  }

  /* ---------------------------------------------------------------- matrix */
  function buildMatrix(ctx, sec, ro) {
    var m = ctx.work.sections[sec.key];
    var wrap = H('div');
    var radioName = 'st-sel-' + sec.key;
    var totCells = [], headCells = [], noteBox = H('div', { class: 'small', style: { marginTop: '8px' } });

    function totals() {
      return m.options.map(function (o) {
        var sum = 0, any = false;
        m.criteria.forEach(function (c) {
          var sc = num(c.scores && c.scores[o]), w = num(c.weight);
          if (!isNaN(sc) && sc > 0 && !isNaN(w)) { sum += w * sc; any = true; }
        });
        return any ? Math.round(sum * 100) / 100 : null;
      });
    }
    function maxPossible() {
      var s = 0;
      m.criteria.forEach(function (c) { var w = num(c.weight); if (!isNaN(w)) s += w * 5; });
      return s;
    }
    function updateTotals() {
      var t = totals(), mx = Math.max.apply(null, t.map(function (x) { return x === null ? -1 : x; }).concat([-1]));
      var maxP = maxPossible();
      t.forEach(function (v, i) {
        var best = v !== null && v === mx && mx > 0;
        if (totCells[i]) {
          totCells[i].textContent = v === null ? '—' : (v + (maxP > 0 ? '（' + Math.round(v / maxP * 100) + '%）' : ''));
          totCells[i].classList.toggle('st-best', best);
        }
        if (headCells[i]) headCells[i].classList.toggle('st-best', best);
      });
      MF.clear(noteBox);
      var bestNames = m.options.filter(function (o, i) { return t[i] !== null && t[i] === mx && mx > 0; });
      if (bestNames.length) noteBox.appendChild(H('div', { class: 'muted' }, '加权总分最高：' + bestNames.join('、') + '（总分 = Σ 权重 × 得分，满分 ' + maxP + '）'));
      if (m.selected && bestNames.length && bestNames.indexOf(m.selected) < 0) {
        noteBox.appendChild(H('div', { style: { color: 'var(--c-warn)' } }, '提示：所选方案“' + m.selected + '”不是评分最高的方案，请在“选择结论与理由”中说明原因。'));
      }
      if (!m.selected && m.options.length) noteBox.appendChild(H('div', { style: { color: 'var(--c-warn)' } }, '尚未选定方案。'));
    }
    ctx.syncers.push(updateTotals);

    function uniqueName(base) {
      var n = m.options.length + 1, name = base + n;
      while (m.options.indexOf(name) >= 0) { n += 1; name = base + n; }
      return name;
    }

    function render() {
      MF.clear(wrap); totCells = []; headCells = [];
      if (!m.options.length) {
        wrap.appendChild(H('div', { class: 'muted' }, '还没有候选方案。'));
        if (!ro) wrap.appendChild(H('button', { type: 'button', class: 'btn btn-sm', onclick: function () { m.options.push(uniqueName('候选方案')); render(); touch(ctx); } }, '＋ 添加候选方案'));
        wrap.appendChild(noteBox);
        return;
      }
      var head = H('tr', null, H('th', { style: { minWidth: '170px' } }, '评价标准'), H('th', { style: { minWidth: '64px' } }, '权重'));
      m.options.forEach(function (o, i) {
        var th = H('th', { style: { minWidth: '110px' } });
        if (ro) th.appendChild(H('span', null, o));
        else {
          var inp = H('input', { class: 'input', type: 'text' });
          inp.value = o;
          inp.addEventListener('change', function () {
            var nv = inp.value.trim(), old = m.options[i];
            if (!nv) { inp.value = old; toast('方案名称不能为空', 'warn'); return; }
            if (nv !== old && m.options.indexOf(nv) >= 0) { inp.value = old; toast('方案名称不能重复', 'warn'); return; }
            if (nv === old) return;
            m.criteria.forEach(function (c) {
              if (c.scores && Object.prototype.hasOwnProperty.call(c.scores, old)) { c.scores[nv] = c.scores[old]; delete c.scores[old]; }
            });
            if (m.selected === old) m.selected = nv;
            m.options[i] = nv;
            touch(ctx);
          });
          th.appendChild(H('div', { class: 'row nowrap', style: { gap: '2px' } }, inp,
            opBtn('✕', '删除此候选方案', async function () {
              var has = m.criteria.some(function (c) { return c.scores && c.scores[m.options[i]]; });
              if (has) { var ok = await MF.confirm('删除候选方案“' + m.options[i] + '”及其评分？', { danger: true, okLabel: '删除' }); if (!ok) return; }
              var name = m.options[i];
              m.criteria.forEach(function (c) { if (c.scores) delete c.scores[name]; });
              if (m.selected === name) m.selected = '';
              m.options.splice(i, 1); render(); touch(ctx);
            })));
        }
        headCells[i] = th;
        head.appendChild(th);
      });
      if (!ro) head.appendChild(H('th', null, ''));
      var tbody = H('tbody');
      m.criteria.forEach(function (c, ci) {
        var tr = H('tr');
        if (ro) {
          tr.appendChild(H('td', null, H('div', { class: 'st-ro' }, c.name || '—')));
          tr.appendChild(H('td', { class: 'st-n' }, S(c.weight) || '—'));
        } else {
          var nm = H('input', { class: 'input', type: 'text', placeholder: '评价标准' });
          nm.value = c.name; nm.addEventListener('input', function () { c.name = nm.value; touch(ctx); });
          var w = H('input', { class: 'input st-n', type: 'number', min: '0', step: 'any' });
          w.value = S(c.weight);
          w.addEventListener('input', function () {
            var n = num(w.value); c.weight = isNaN(n) ? '' : n;
            w.classList.toggle('st-invalid', w.value !== '' && (isNaN(n) || n < 0));
            touch(ctx);
          });
          tr.appendChild(H('td', null, nm));
          tr.appendChild(H('td', null, w));
        }
        m.options.forEach(function (o, i) {
          if (ro) { tr.appendChild(H('td', { class: 'st-n' }, S(c.scores && c.scores[o]) || '—')); return; }
          var sel = H('select', { class: 'select st-n' }, H('option', { value: '' }, '—'),
            [1, 2, 3, 4, 5].map(function (n) { return H('option', { value: String(n) }, String(n)); }));
          sel.value = S(c.scores && c.scores[o]);
          sel.addEventListener('change', function () {
            if (!c.scores) c.scores = {};
            var key = m.options[i];
            if (sel.value === '') delete c.scores[key]; else c.scores[key] = Number(sel.value);
            touch(ctx);
          });
          tr.appendChild(H('td', null, sel));
        });
        if (!ro) {
          tr.appendChild(H('td', { class: 'st-ops' },
            opBtn('↑', '上移', function () { if (moveItem(m.criteria, ci, -1)) { render(); touch(ctx); } }, ci === 0),
            opBtn('↓', '下移', function () { if (moveItem(m.criteria, ci, 1)) { render(); touch(ctx); } }, ci === m.criteria.length - 1),
            opBtn('✕', '删除此标准', function () { m.criteria.splice(ci, 1); render(); touch(ctx); })));
        }
        tbody.appendChild(tr);
      });
      var totTr = H('tr', { class: 'st-total' }, H('td', { colspan: 2 }, '加权总分'));
      m.options.forEach(function (o, i) {
        var td = H('td', { class: 'st-n' }, '—');
        totCells[i] = td; totTr.appendChild(td);
      });
      if (!ro) totTr.appendChild(H('td'));
      var selTr = H('tr', null, H('td', { colspan: 2 }, '选定方案'));
      m.options.forEach(function (o, i) {
        var td = H('td', { class: 'st-n' });
        if (ro) td.textContent = m.selected === o ? '✔ 已选' : '';
        else {
          var r = H('input', { type: 'radio', name: radioName, checked: m.selected === o, 'aria-label': '选定 ' + o });
          r.addEventListener('change', function () { m.selected = m.options[i]; touch(ctx); });
          td.appendChild(r);
        }
        selTr.appendChild(td);
      });
      if (!ro) selTr.appendChild(H('td'));
      tbody.appendChild(totTr); tbody.appendChild(selTr);
      wrap.appendChild(H('div', { class: 'st-wrapx' }, H('table', { class: 'st-tbl' }, H('thead', null, head), tbody)));
      if (!ro) {
        wrap.appendChild(H('div', { class: 'row', style: { marginTop: '8px' } },
          H('button', { type: 'button', class: 'btn btn-sm', onclick: function () { m.criteria.push({ name: '', weight: 3, scores: {} }); render(); touch(ctx); } }, '＋ 添加评价标准'),
          H('button', { type: 'button', class: 'btn btn-sm', onclick: function () { m.options.push(uniqueName('候选方案')); render(); touch(ctx); } }, '＋ 添加候选方案')));
      }
      wrap.appendChild(noteBox);
      updateTotals();
    }
    render();
    return wrap;
  }

  /* ---------------------------------------------------------------- FMEA */
  var FMEA_COLS = [
    { key: 'mode', label: '失效模式', w: 150, t: 'text' }, { key: 'cause', label: '原因', w: 140, t: 'text' },
    { key: 'effect', label: '影响', w: 140, t: 'text' }, { key: 'S', label: 'S 严重度', w: 62, t: 'sod' },
    { key: 'O', label: 'O 发生度', w: 62, t: 'sod' }, { key: 'D', label: 'D 可检测', w: 62, t: 'sod' },
    { key: 'rpn', label: 'RPN', w: 80, t: 'rpn' }, { key: 'control', label: '控制措施', w: 200, t: 'text' },
    { key: 'owner', label: '责任人', w: 90, t: 'text' }
  ];
  function sodValid(v) { var n = num(v); return !isNaN(n) && n === Math.floor(n) && n >= 1 && n <= 10; }
  function fmeaState(r, th) {
    var okS = sodValid(r.S), okO = sodValid(r.O), okD = sodValid(r.D);
    var rpn = (okS && okO && okD) ? num(r.S) * num(r.O) * num(r.D) : null;
    var high = (rpn !== null && rpn >= th.rpn) || (okS && num(r.S) >= th.sev);
    var missing = high && !S(r.control).trim();
    return { rpn: rpn, high: high, missing: missing };
  }

  /* every S/O/D that is not an integer 1-10 (empty is allowed); the API rejects these with 400 */
  function sodProblems(ctx) {
    var out = [];
    ((ctx.detail.def && ctx.detail.def.sections) || []).forEach(function (sec) {
      if (sec.type !== 'fmea') return;
      (ctx.work.sections[sec.key] || []).forEach(function (r, i) {
        ['S', 'O', 'D'].forEach(function (k) {
          var v = r[k];
          if (v === '' || v === null || v === undefined) return;
          if (!sodValid(v)) out.push('“' + S(sec.title) + '”第 ' + (i + 1) + ' 行 ' + k + '=' + S(v));
        });
      });
    });
    return out;
  }

  function buildFmea(ctx, sec, ro) {
    var rows = ctx.work.sections[sec.key];
    var th = thresholds();
    var wrap = H('div');
    var summary = H('span', { class: 'small muted' });
    var entries = [];

    function syncSummary() {
      var hi = 0, miss = 0, filled = 0;
      rows.forEach(function (r) {
        if (isBlank(r)) return;
        filled += 1;
        var st = fmeaState(r, th);
        if (st.high) hi += 1;
        if (st.missing) miss += 1;
      });
      summary.textContent = '共 ' + filled + ' 行；高风险 ' + hi + ' 行；高风险缺控制措施 ' + miss + ' 行';
      summary.style.color = miss ? 'var(--c-err)' : '';
    }
    ctx.syncers.push(syncSummary);

    function updateRow(e) {
      var r = e.row, st = fmeaState(r, th);
      e.tr.classList.toggle('st-high', st.high);
      MF.clear(e.rpnTd);
      e.rpnTd.appendChild(H('div', null, st.rpn === null ? '—' : String(st.rpn)));
      if (st.high) e.rpnTd.appendChild(H('div', null, badge('高风险', 'err')));
      if (st.missing) e.rpnTd.appendChild(H('div', null, badge('缺控制措施', 'err')));
      if (e.ctl) e.ctl.classList.toggle('st-invalid', st.missing);
    }

    function render() {
      MF.clear(wrap); entries = [];
      var order = rows.map(function (r, i) { return i; });
      var sorted = !!ctx.ui.fmeaSort[sec.key];
      if (sorted) {
        order.sort(function (a, b) {
          var ra = fmeaState(rows[a], th).rpn, rb = fmeaState(rows[b], th).rpn;
          return ((rb === null ? -1 : rb) - (ra === null ? -1 : ra)) || (a - b);
        });
      }
      wrap.appendChild(H('div', { class: 'row', style: { marginBottom: '6px' } },
        H('button', { type: 'button', class: 'btn btn-sm' + (sorted ? ' btn-primary' : ''), onclick: function () {
          ctx.ui.fmeaSort[sec.key] = !sorted; render();
        } }, sorted ? '按 RPN 降序：开（点击关闭）' : '按 RPN 降序排序'),
        sorted ? H('button', { type: 'button', class: 'btn btn-sm', onclick: render }, '重新排序') : null,
        summary));
      wrap.appendChild(H('div', { class: 'st-legend' },
        H('span', null, H('span', { class: 'st-sw', style: { background: 'var(--c-err-soft)', borderColor: 'var(--c-err)' } }),
          '红底 = RPN ≥ ' + th.rpn + ' 或 S ≥ ' + th.sev + '（高风险，必须填写控制措施）'),
        H('span', null, 'RPN = S × O × D（均为 1–10 的整数）')));
      if (ro && !rows.length) { wrap.appendChild(H('div', { class: 'muted' }, '（暂无内容）')); syncSummary(); return; }
      var head = H('tr', null, H('th', null, '#'),
        FMEA_COLS.map(function (c) { return H('th', { style: { minWidth: Math.round(c.w * 0.7) + 'px' } }, c.label); }),
        ro ? null : H('th'));
      var tbody = H('tbody');
      order.forEach(function (idx, pos) {
        var row = rows[idx];
        var e = { row: row, tr: H('tr'), rpnTd: H('td', { class: 'st-rpn' }), ctl: null };
        e.tr.appendChild(H('td', { class: 'st-ix' }, String(idx + 1)));
        FMEA_COLS.forEach(function (c) {
          if (c.t === 'rpn') { e.tr.appendChild(e.rpnTd); return; }
          if (ro) { e.tr.appendChild(H('td', { class: c.t === 'sod' ? 'st-n' : null }, H('div', { class: 'st-ro' }, S(row[c.key]) || '—'))); return; }
          var el;
          if (c.t === 'sod') {
            el = H('input', { class: 'input st-n', type: 'number', min: '1', max: '10', step: '1' });
            el.value = S(row[c.key]);
            (function (el, c) {
              el.addEventListener('input', function () {
                var n = num(el.value); row[c.key] = isNaN(n) ? '' : n;
                var bad = el.value !== '' && !sodValid(el.value);
                el.classList.toggle('st-invalid', bad);
                el.title = bad ? c.label + ' 需为 1–10 的整数' : '';
                updateRow(e); touch(ctx);
              });
              if (el.value !== '' && !sodValid(el.value)) el.classList.add('st-invalid');
            })(el, c);
          } else {
            el = mkTA(ctx, 'textarea st-ta1');
            el.value = S(row[c.key]);
            (function (el, c) {
              el.addEventListener('input', function () { row[c.key] = el.value; autosize(el); if (c.key === 'control') updateRow(e); touch(ctx); });
            })(el, c);
            if (c.key === 'control') e.ctl = el;
          }
          e.tr.appendChild(H('td', null, el));
        });
        if (!ro) {
          e.tr.appendChild(H('td', { class: 'st-ops' },
            opBtn('↑', sorted ? '排序模式下不可移动' : '上移', function () { if (moveItem(rows, idx, -1)) { render(); touch(ctx); } }, sorted || idx === 0),
            opBtn('↓', sorted ? '排序模式下不可移动' : '下移', function () { if (moveItem(rows, idx, 1)) { render(); touch(ctx); } }, sorted || idx === rows.length - 1),
            opBtn('✕', '删除此行', async function () {
              if (!isBlank(row)) {
                var ok = await MF.confirm('删除第 ' + (idx + 1) + ' 行（' + (S(row.mode) || '未命名') + '）？', { danger: true, okLabel: '删除' });
                if (!ok) return;
              }
              rows.splice(idx, 1); render(); touch(ctx);
            })));
        }
        entries.push(e);
        updateRow(e);
        tbody.appendChild(e.tr);
      });
      wrap.appendChild(H('div', { class: 'st-wrapx' }, H('table', { class: 'st-tbl' }, H('thead', null, head), tbody)));
      if (!rows.length) wrap.appendChild(H('div', { class: 'muted small', style: { padding: '8px 2px' } }, '还没有行，点击下方“添加一行”。'));
      if (!ro) {
        wrap.appendChild(H('div', { style: { marginTop: '8px' } },
          H('button', { type: 'button', class: 'btn btn-sm', onclick: function () {
            rows.push({ mode: '', cause: '', effect: '', S: '', O: '', D: '', control: '', owner: '' });
            render(); touch(ctx);
            var inp = wrap.querySelector('tbody tr:last-child textarea');
            if (inp) inp.focus();
          } }, '＋ 添加一行')));
      }
      syncSummary();
    }
    render();
    return wrap;
  }

  /* ================================================================== checklist */
  var CK_LABEL = { todo: '待办', done: '完成', na: '不适用' };
  function ckWarn(c, it) {
    var note = (it.note || '').trim();
    if (it.status === 'na' && !note) return '标记“不适用”须填写理由。';
    if (it.status === 'done' && c.evidence && !note) return '此项需填写证据说明（如实验编号、文件名、结论）。';
    return '';
  }
  function renderChecklist(ctx) {
    var el = ctx.el.checklist, d = ctx.detail;
    MF.clear(el);
    var items = (d.def && d.def.checklist) || [];
    if (!items.length) return;
    var ro = !d.editable;
    var counter = H('span', { class: 'muted small' });
    function syncCount() {
      var done = items.filter(function (c) { var s = ctx.work.checklist[c.key].status; return s === 'done' || s === 'na'; }).length;
      counter.textContent = '已处理 ' + done + ' / ' + items.length;
    }
    ctx.syncers.push(syncCount);
    var list = H('div');
    items.forEach(function (c) {
      var it = ctx.work.checklist[c.key];
      var warn = H('div', { class: 'st-ck-warn', hidden: true });
      var segBtns = {};
      var seg = H('div', { class: 'st-seg' });
      ['todo', 'done', 'na'].forEach(function (s) {
        var b = H('button', { type: 'button', class: 'btn btn-sm', disabled: ro, onclick: function () { it.status = s; sync(); touch(ctx); } }, CK_LABEL[s]);
        segBtns[s] = b; seg.appendChild(b);
      });
      var noteEl = null;
      if (!ro) {
        noteEl = mkTA(ctx, 'textarea st-ta1', c.evidence ? '证据说明（必填）：实验编号 / 文件 / 结论' : '备注（标记“不适用”时须填写理由）');
        noteEl.value = it.note;
        noteEl.addEventListener('input', function () { it.note = noteEl.value; autosize(noteEl); sync(); touch(ctx); });
      }
      function sync() {
        ['todo', 'done', 'na'].forEach(function (s) { segBtns[s].classList.toggle('on-' + s, it.status === s); });
        var w = ckWarn(c, it);
        warn.hidden = !w; warn.textContent = w;
        if (noteEl) noteEl.classList.toggle('st-invalid', !!w);
      }
      sync();
      list.appendChild(H('div', { class: 'st-ck' },
        H('div', { class: 'st-ck-top' }, seg,
          H('div', { class: 'st-ck-text' },
            H('div', null, S(c.text), ' ',
              c.required ? badge('必需', 'err') : badge('可选', 'muted'), ' ',
              c.evidence ? badge('需证据', 'warn') : null),
            c.guidance ? H('div', { class: 'muted small', style: { marginTop: '2px' } }, '提示：' + S(c.guidance)) : null,
            c.ref ? H('div', { class: 'muted small' }, '依据：' + S(c.ref)) : null)),
        ro ? (it.note ? H('div', { class: 'small st-ro', style: { margin: '4px 0 0 4px' } }, '备注：' + it.note) : null)
          : H('div', { style: { marginTop: '6px' } }, noteEl),
        warn));
    });
    el.appendChild(H('div', { class: 'card' },
      H('div', { class: 'st-card-h' }, H('h3', null, '检查清单'), counter,
        ro ? null : H('button', { type: 'button', class: 'btn btn-sm', title: '把尚未处理且不要求证据说明的检查项标为“完成”；请确认您确实逐项核对过',
          onclick: async function () {
            var todo = items.filter(function (c) { return ctx.work.checklist[c.key].status === 'todo' && !c.evidence; });
            if (!todo.length) { toast('没有可批量标记的检查项（需证据说明的项须逐项填写）', 'warn'); return; }
            if (!(await MF.confirm('把 ' + todo.length + ' 个未处理的检查项标为“完成”？这表示您已逐项核对；需证据说明的项不会被标记。'))) return;
            todo.forEach(function (c) { ctx.work.checklist[c.key].status = 'done'; });
            renderChecklist(ctx); touch(ctx);
          } }, '全部标为完成')),
      H('div', { class: 'st-help' }, '逐项确认；“不适用”必须写明理由；标有“需证据”的完成项必须写证据说明。'),
      list));
    syncCount();
  }

  /* ================================================================== gate panel */
  function stageTitle(ctx, key) {
    var st = ((ctx.method && ctx.method.stages) || []).filter(function (s) { return s.key === key; })[0];
    return st ? st.title : key;
  }
  function memberNames(ctx, role) {
    var ed = (ctx.detail.editors || []).concat(ctx.detail.contributors || []);
    var names = ((ctx.method && ctx.method.members) || []).filter(function (m) {
      return m.role === role && ed.indexOf(m.user_id) < 0;
    }).map(function (m) { return m.display_name; });
    return names.filter(function (n, i) { return names.indexOf(n) === i; });
  }
  function nextStepText(ctx) {
    var d = ctx.detail, st = d.status;
    if (d.stale) return '下一步：核对内容后点击“重新确认”，重新提交复核。';
    if (st === 'in_review') {
      var nm = memberNames(ctx, d.next_role);
      return '下一步：待' + roleLabel(d.next_role) + (nm.length ? ' ' + nm.join('、') : '') + ' 签署。';
    }
    if (st === 'approved') return '本阶段已通过并锁定，可进入后续阶段。';
    if (st === 'completed') return '本阶段已完成并锁定。';
    if (st === 'returned') return '下一步：按退回意见修改，满足提交条件后重新提交。';
    return d.can_submit ? '下一步：补全章节与检查清单，满足全部提交条件后“提交”。' : '下一步：由方法负责人/开发人员编辑并提交。';
  }
  function renderGate(ctx) {
    var d = ctx.detail, el = ctx.el.gate;
    MF.clear(el);
    var gate = d.def && d.def.gate;
    var projActive = (!ctx.method || !ctx.method.status || ctx.method.status === 'active') && (!ctx.method || !ctx.method.project || !ctx.method.project.status || ctx.method.project.status === 'active');
    var card = H('div', { class: 'card st-gate' });
    card.appendChild(H('div', { class: 'st-card-h' }, H('h3', null, gate ? S(gate.name || gate.key) : '阶段完成'),
      MF.statusBadge ? MF.statusBadge(d.status, d.status_label, d.stale) : null));
    /* signers progress */
    if (gate) {
      var signed = {};
      (d.reviews || []).forEach(function (r) { if (r.revision === d.revision && r.decision === 'approve') signed[r.role] = true; });
      card.appendChild(H('div', { class: 'small', style: { marginBottom: '6px' } }, '需要签署：',
        (gate.roles || []).map(function (r, i) {
          return H('span', null, i ? ' → ' : '', badge(roleLabel(r) + (d.status === 'in_review' || d.status === 'approved' ? (signed[r] ? ' ✓' : '') : ''), signed[r] ? 'ok' : 'muted'));
        })));
      if ((gate.covers || []).length) {
        card.appendChild(H('div', { class: 'muted small' }, '本门同时覆盖：' + gate.covers.map(function (k) { return stageTitle(ctx, k); }).join('、')));
      }
    } else {
      card.appendChild(H('div', { class: 'muted small', style: { marginBottom: '6px' } }, '本阶段无需复核，满足条件后提交即完成。'));
    }
    card.appendChild(H('div', { class: 'callout', style: { margin: '8px 0' } }, nextStepText(ctx)));
    if (MF.records && MF.records.commentButton) {
      card.appendChild(H('div', { class: 'row', style: { gap: '6px', alignItems: 'center', margin: '4px 0 8px' } }, MF.records.commentButton(ctx, null), H('span', { class: 'small muted' }, '讨论本阶段（可 @同事）')));
    }
    if ((d.revisions || []).length >= 2 || (d.revisions || []).length >= 1 && d.revision > 1) {
      card.appendChild(H('div', { style: { margin: '4px 0 8px' } },
        H('button', { type: 'button', class: 'btn btn-sm', onclick: function () { showDiff(ctx); } }, '查看与上一修订的对比')));
    }
    /* checks */
    var showChecks = (EDITABLE_STATUS.indexOf(d.status) >= 0 || d.stale) && d.can_submit;
    if (showChecks) {
      var ck = ctx.checks || { blocks: [], warns: [] };
      card.appendChild(H('div', { class: 'st-card-h', style: { marginTop: '4px' } }, H('strong', null, '提交条件检查'),
        H('button', { type: 'button', class: 'btn btn-sm btn-ghost', onclick: function () { refreshChecks(ctx); } }, '刷新')));
      ctx.gateNote = H('div', { class: 'hint', hidden: true }, '有未保存的修改：以下检查基于已保存的内容，保存后自动刷新。');
      card.appendChild(ctx.gateNote);
      if ((ck.blocks || []).length) {
        card.appendChild(H('div', { class: 'callout callout-err' }, H('strong', null, '阻断项（' + ck.blocks.length + '）：必须解决才能提交'),
          H('ul', null, ck.blocks.map(function (b) { return H('li', null, S(b)); }))));
      }
      if ((ck.incomplete || []).length) {
        card.appendChild(H('div', { class: 'callout callout-warn' }, H('strong', null, '尚未填写（' + ck.incomplete.length + '）：不阻断提交，可逐步补充'),
          H('ul', null, ck.incomplete.map(function (b) { return H('li', null, S(b)); }))));
      }
      if ((ck.warns || []).length) {
        card.appendChild(H('div', { class: 'callout callout-warn' }, H('strong', null, '提示（' + ck.warns.length + '）：不阻断提交'),
          H('ul', null, ck.warns.map(function (b) { return H('li', null, S(b)); }))));
      }
      if (!(ck.blocks || []).length && !(ck.warns || []).length) {
        card.appendChild(H('div', { class: 'callout callout-ok' }, '所有提交条件均已满足。'));
      } else if (!(ck.blocks || []).length) {
        card.appendChild(H('div', { class: 'callout callout-ok' }, '没有阻断项，可以提交。'));
      }
    } else {
      ctx.gateNote = null;
      var ck2 = ctx.checks || { blocks: [], warns: [] };
      if ((ck2.warns || []).length) {
        card.appendChild(H('div', { class: 'callout callout-warn' }, H('strong', null, '阶段提示（' + ck2.warns.length + '）：不阻断'),
          H('ul', null, ck2.warns.map(function (b) { return H('li', null, S(b)); }))));
      }
    }
    /* actions */
    var act = H('div', { class: 'st-act' });
    if (projActive && d.can_submit && EDITABLE_STATUS.indexOf(d.status) >= 0) {
      act.appendChild(btnAct('primary', gate ? '提交复核' : '完成本阶段', function () { return doSubmit(ctx); }));
    }
    if (projActive && d.can_withdraw) act.appendChild(btnAct('', '撤回', function () { return doWithdraw(ctx); }));
    if (d.can_sign_as) {
      act.appendChild(btnAct('primary', '复核通过', function () { return doReview(ctx, 'approve'); }));
      act.appendChild(btnAct('danger', '退回', function () { return doReview(ctx, 'reject'); }));
    }
    if (projActive && d.can_recertify) act.appendChild(btnAct('primary', '重新确认', function () { return doRecertify(ctx); }));
    if (projActive && d.can_reopen) act.appendChild(btnAct('', '重新打开', function () { return doReopen(ctx); }));
    if (act.childNodes.length) card.appendChild(act);
    if (d.status === 'in_review' && !d.can_sign_as && d.cannot_sign_reason) {
      card.appendChild(H('div', { class: 'muted small' }, '您当前不能签署：' + S(d.cannot_sign_reason)));
    }
    el.appendChild(card);
    /* sign history */
    var revs = d.reviews || [];
    var hist = H('div', { class: 'card' }, H('div', { class: 'st-card-h' }, H('h3', null, '签署记录'), H('span', { class: 'muted small' }, revs.length + ' 条')));
    if (!revs.length) hist.appendChild(H('div', { class: 'muted small' }, '暂无签署记录。'));
    revs.slice().reverse().forEach(function (r) {
      hist.appendChild(H('div', { class: 'st-rev' },
        H('div', { class: 'row', style: { gap: '6px' } },
          badge(r.decision === 'approve' ? '通过' : '退回', r.decision === 'approve' ? 'ok' : 'err'),
          H('strong', null, S(r.display_name)), H('span', { class: 'muted' }, S(r.role_label || roleLabel(r.role))),
          H('span', { class: 'muted small' }, 'R' + S(r.revision)),
          badge(r.intact ? '内容未被改动' : '内容哈希不一致', r.intact ? 'ok' : 'err')),
        H('div', { class: 'muted small' }, fdt(r.signed_at) + (r.data_hash ? ' · 哈希 ' + String(r.data_hash).slice(0, 12) : '')),
        r.meaning ? H('div', { class: 'small', title: S(r.meaning) }, '含义：' + S(r.meaning)) : null,
        r.comment ? H('div', { class: 'st-ro' }, '意见：' + S(r.comment)) : null));
    });
    el.appendChild(hist);
    touch(ctx);
  }
  function btnAct(kind, label, fn) {
    var b = H('button', { type: 'button', class: 'btn' + (kind === 'primary' ? ' btn-primary' : kind === 'danger' ? ' btn-danger' : '') }, label);
    b.addEventListener('click', async function () {
      if (b.disabled) return;
      b.disabled = true;
      try { await fn(); } catch (e) { if (!(e && e.status === 401)) toast(errText(e), 'err'); } finally { b.disabled = false; }
    });
    return b;
  }

  function blocksModal(title, blocks, warns) {
    var body = H('div');
    if (blocks && blocks.length) body.appendChild(H('div', { class: 'callout callout-err' }, H('strong', null, '阻断项'),
      H('ul', null, blocks.map(function (b) { return H('li', null, S(b)); }))));
    if (warns && warns.length) body.appendChild(H('div', { class: 'callout callout-warn' }, H('strong', null, '提示'),
      H('ul', null, warns.map(function (b) { return H('li', null, S(b)); }))));
    return MF.modal({ title: title, body: body, width: 560, buttons: [{ label: '知道了', kind: 'primary', value: true }] });
  }

  async function doSubmit(ctx) {
    var d = ctx.detail, gate = d.def && d.def.gate;
    if (isDirty(ctx)) {
      var saved = await save(ctx);
      if (!saved) return;
      d = ctx.detail;
    }
    await refreshChecks(ctx, true);
    var ck = ctx.checks || { blocks: [], warns: [] };
    if ((ck.blocks || []).length) {
      await blocksModal('尚不能提交：还有 ' + ck.blocks.length + ' 项阻断条件', ck.blocks, ck.warns);
      return;
    }
    var intro = H('div');
    intro.appendChild(H('div', { class: 'callout' }, gate
      ? '提交后本阶段内容将被锁定并生成快照，进入“' + (gate.name || '复核') + '”，由 ' + (gate.roles || []).map(roleLabel).join('、') + ' 依次签署。'
      : '本阶段无需复核，提交后将直接标记为完成并锁定。'));
    if ((ck.incomplete || []).length) {
      intro.appendChild(H('div', { class: 'callout callout-warn' }, H('strong', null, '仍有 ' + ck.incomplete.length + ' 项补充内容未填写：'),
        H('ul', null, ck.incomplete.slice(0, 12).map(function (w) { return H('li', null, S(w)); }).concat(ck.incomplete.length > 12 ? [H('li', null, '……另有 ' + (ck.incomplete.length - 12) + ' 项')] : [])),
        H('div', { class: 'small' }, '这些不阻止提交；它们会显示给复核人，在文档中标为红色【待填写】，并写入审计记录。确认现在提交吗？')));
    }
    if ((ck.warns || []).length) {
      intro.appendChild(H('div', { class: 'callout callout-warn' }, H('strong', null, '提示（不阻断）'),
        H('ul', null, ck.warns.map(function (w) { return H('li', null, S(w)); }))));
    }
    var v = await formModal({
      title: gate ? '提交复核' : '完成本阶段', intro: intro, okLabel: gate ? '提交复核' : '确认完成',
      fields: [{ key: 'comment', label: '提交说明（可选）', type: 'textarea', placeholder: '本次提交的主要内容 / 需要复核人注意的地方' }]
    });
    if (!v) return;
    try {
      await MF.api('POST', api(ctx, '/submit'), { comment: v.comment });
      toast(gate ? '已提交复核' : '本阶段已完成', 'ok');
      if (MF.dirtyGuard) MF.dirtyGuard.set(false);
      changedProject(ctx);
    } catch (e) {
      if (e && e.status === 422 && e.detail && e.detail.blocks) {
        ctx.checks = { blocks: e.detail.blocks, warns: e.detail.warns || [] };
        renderGate(ctx);
        await blocksModal('未满足提交条件', e.detail.blocks, e.detail.warns);
      } else throw e;
    }
  }

  async function doWithdraw(ctx) {
    var v = await formModal({
      title: '撤回复核', okLabel: '撤回', danger: true,
      intro: H('div', { class: 'callout callout-warn' }, '撤回后已有的签署作废，阶段回到“进行中”并进入新的修订版本，可继续编辑。'),
      fields: [{ key: 'reason', label: '撤回原因', type: 'textarea', required: true }]
    });
    if (!v) return;
    await MF.api('POST', api(ctx, '/withdraw'), { reason: v.reason });
    toast('已撤回', 'ok');
    changedProject(ctx);
  }

  async function doReview(ctx, decision) {
    var d = ctx.detail, title = d.title || ctx.key;
    var role = d.can_sign_as;
    var rev = 'R' + S(d.revision);
    var meaning;
    if (decision === 'approve') {
      meaning = role === 'approver'
        ? '我作为批准人（QA）已审阅“' + title + '”阶段（修订 ' + rev + '）的内容及复核记录，批准本阶段内容及其结论。'
        : '我已复核“' + title + '”阶段（修订 ' + rev + '）的全部内容，确认其完整、准确，并同意本阶段内容。';
    } else {
      meaning = '我复核了“' + title + '”阶段（修订 ' + rev + '），认为需要修改，退回给开发人员（原因见意见）。';
    }
    var r = await MF.askSign({
      title: decision === 'approve' ? (role === 'approver' ? '批准通过：' : '复核通过：') + title : '退回：' + title,
      meaning: meaning, needComment: true, commentRequired: decision === 'reject',
      commentLabel: decision === 'reject' ? '退回原因（必填）' : '复核意见'
    });
    if (!r) return;
    try {
      await MF.api('POST', api(ctx, '/review'), { decision: decision, password: r.password, comment: r.comment || '',
        revision: d.revision, expected_hash: d.hash });
    } catch (e) {
      if (e && e.status === 409) {
        toast(e.message || '内容已更新，请刷新后重新审阅', 'err');
        changedProject(ctx);
        return;
      }
      throw e;
    }
    toast(decision === 'approve' ? '已签署通过' : '已退回', 'ok');
    changedProject(ctx);
  }

  async function doReopen(ctx) {
    var d = ctx.detail, title = d.title || ctx.key;
    var r = await MF.askSign({
      title: '重新打开：' + title,
      meaning: '我确认重新打开“' + title + '”阶段（当前修订 R' + S(d.revision) + '）。已有签署将失效，依赖本阶段的后续阶段会被标记为失效，需重新复核。',
      needComment: true, commentRequired: true, commentLabel: '重新打开原因（必填）'
    });
    if (!r) return;
    var res = await MF.api('POST', api(ctx, '/reopen'), { reason: r.comment, password: r.password });
    toast('阶段已重新打开', 'ok');
    var aff = (res && res.affected) || [];
    if (aff.length) {
      await MF.modal({
        title: '受影响的阶段', width: 520,
        body: H('div', null, H('div', { class: 'callout callout-warn' }, '下列阶段受本次重新打开影响：'),
          H('ul', null, aff.map(function (a) { return H('li', null, H('strong', null, stageTitle(ctx, a.stage)), '：' + S(a.effect)); }))),
        buttons: [{ label: '知道了', kind: 'primary', value: true }]
      });
    }
    changedProject(ctx);
  }

  async function doRecertify(ctx) {
    var v = await formModal({
      title: '重新确认并提交复核', okLabel: '重新提交复核',
      intro: H('div', { class: 'callout' }, '内容不变，生成新的修订版本并重新提交复核。请确认前置阶段的变更不影响本阶段结论。'),
      fields: [{ key: 'comment', label: '说明（可选）', type: 'textarea', placeholder: '例如：已核对前置阶段变更，对本阶段无影响' }]
    });
    if (!v) return;
    try {
      await MF.api('POST', api(ctx, '/recertify'), { comment: v.comment });
      toast('已重新提交复核', 'ok');
      changedProject(ctx);
    } catch (e) {
      if (e && e.status === 422 && e.detail && e.detail.blocks) {
        await blocksModal('未满足提交条件', e.detail.blocks, e.detail.warns);
      } else throw e;
    }
  }

  /* ================================================================== side data refresh */
  function refreshServer(ctx) {
    return MF.api('GET', api(ctx)).then(function (d) {
      ctx.detail.experiments = d.experiments; ctx.detail.attachments = d.attachments; ctx.detail.editor_names = d.editor_names;
      ctx.detail.editors = d.editors; ctx.detail.reviews = d.reviews; ctx.detail.revisions = d.revisions;
      ctx.checks = d.checks || ctx.checks;
      renderHeader(ctx); renderBanner(ctx); renderGate(ctx); renderExps(ctx); renderAtts(ctx); renderRevs(ctx);
    }, function (e) { toast(errText(e), 'err'); });
  }

  /* ================================================================== experiments */
  function renderExps(ctx) {
    var d = ctx.detail, el = ctx.el.exps;
    MF.clear(el);
    var list = d.experiments || [];
    var canAdd = d.editable;
    var card = H('div', { class: 'card' },
      H('div', { class: 'st-card-h' }, H('h3', null, '本阶段实验'), H('span', { class: 'muted small' }, list.length + ' 个'), H('span', { class: 'spacer' }),
        canAdd ? H('button', { type: 'button', class: 'btn btn-sm', onclick: function () { newExperiment(ctx); } }, '＋ 新增实验') : null));
    if (!list.length) card.appendChild(H('div', { class: 'muted small' }, '本阶段还没有登记实验。'));
    list.forEach(function (e) {
      card.appendChild(H('div', { class: 'st-li' },
        H('strong', null, S(e.code)),
        H('a', { href: '#/m/' + ctx.mid + '/exp/' + e.id }, S(e.title) || '（未命名）'),
        e.added_after_plan ? H('span', { class: 'st-sample-tag', title: '方案提交/批准后新增的实验，在文档中单列' }, '方案后新增') : null,
        badge(EXP_STATUS[e.status] || S(e.status), EXP_KIND[e.status] || 'muted'),
        e.locked ? badge('已锁定', 'muted') : null,
        e.attachments ? H('span', { class: 'muted small' }, '附件 ' + e.attachments) : null,
        H('span', { class: 'spacer' }),
        (e.planned_start || e.planned_end) ? H('span', { class: 'muted small' }, fdate(e.planned_start) + ' ~ ' + fdate(e.planned_end)) : null));
    });
    el.appendChild(card);
  }
  async function newExperiment(ctx) {
    var planSt = ((ctx.method && ctx.method.stages) || []).filter(function (x) { return x.key === 'plan'; })[0];
    var late = planSt && ['in_review', 'approved', 'completed'].indexOf(planSt.status) >= 0;
    var v = await formModal({
      title: '新增实验', okLabel: '创建', width: 560,
      intro: late ? H('div', { class: 'callout callout-warn' }, '“开发方案”阶段已提交/批准：新增的实验将标记为“方案后新增”，并在文档中单列，且必须填写“设计”和“接受标准”。') : null,
      fields: [
        { key: 'title', label: '实验名称', required: true, placeholder: '例如：抗体滴定' },
        { key: 'objective', label: '目的', type: 'textarea', rows: 2 },
        { key: 'design', label: '设计', type: 'textarea', rows: 3, required: !!late, hint: late ? '方案已提交/批准，必须填写' : '' },
        { key: 'acceptance', label: '接受标准', type: 'textarea', rows: 2, required: !!late, hint: late ? '方案已提交/批准，必须填写' : '' }
      ]
    });
    if (!v) return;
    try {
      var body = { title: v.title, stage_key: ctx.key, objective: v.objective, design: v.design, acceptance: v.acceptance };
      await MF.api('POST', '/api/methods/' + ctx.mid + '/experiments', body);
      toast('实验已创建，可点击实验名称进入详情继续填写', 'ok');
      await refreshServer(ctx);
    } catch (e) { if (!(e && e.status === 401)) toast(errText(e), 'err'); }
  }

  /* ================================================================== attachments */
  function renderAtts(ctx) {
    var d = ctx.detail, el = ctx.el.atts;
    MF.clear(el);
    var list = d.attachments || [];
    var canEdit = d.editable;
    var card = H('div', { class: 'card' });
    var head = H('div', { class: 'st-card-h' }, H('h3', null, '本阶段附件'), H('span', { class: 'muted small' }, list.length + ' 个'), H('span', { class: 'spacer' }));
    if (canEdit) {
      var desc = H('input', { class: 'input input-sm', type: 'text', placeholder: '附件说明（可选）', style: { width: '180px' } });
      var file = H('input', { type: 'file', hidden: true });
      var upBtn = H('button', { type: 'button', class: 'btn btn-sm', onclick: function () { file.click(); } }, '＋ 上传附件');
      file.addEventListener('change', async function () {
        var f = file.files && file.files[0];
        if (!f) return;
        upBtn.disabled = true; upBtn.textContent = '上传中……';
        try {
          var url = '/api/methods/' + ctx.mid + '/attachments?filename=' + encodeURIComponent(f.name) + '&stage_key=' + encodeURIComponent(ctx.key) +
            '&description=' + encodeURIComponent(desc.value.trim());
          await MF.upload(url, f);
          toast('已上传：' + f.name, 'ok');
          await refreshServer(ctx);
        } catch (e) { if (!(e && e.status === 401)) toast('上传失败：' + errText(e), 'err'); }
        finally { file.value = ''; upBtn.disabled = false; upBtn.textContent = '＋ 上传附件'; }
      });
      head.appendChild(desc); head.appendChild(upBtn); head.appendChild(file);
    }
    card.appendChild(head);
    if (!list.length) card.appendChild(H('div', { class: 'muted small' }, '本阶段还没有附件。'));
    list.forEach(function (a) {
      var ver = ctx.verified[a.id];
      var verBadge = ver === undefined ? null : badge(ver ? '完整性校验通过' : '校验不一致', ver ? 'ok' : 'err');
      card.appendChild(H('div', { class: 'st-li' },
        H('a', { href: '/api/attachments/' + a.id + '/download', download: S(a.filename) }, S(a.filename)),
        H('span', { class: 'muted small' }, fsize(a.size)),
        H('span', { class: 'muted small' }, S(a.uploader) + ' · ' + fdt(a.uploaded_at)),
        H('span', { class: 'st-mono muted', title: S(a.sha256) }, 'sha256 ' + S(a.sha256).slice(0, 12)),
        a.description ? H('span', { class: 'small' }, S(a.description)) : null,
        verBadge,
        H('span', { class: 'spacer' }),
        H('button', { type: 'button', class: 'btn btn-sm', onclick: async function () {
          try {
            var r = await MF.api('POST', '/api/attachments/' + a.id + '/verify');
            ctx.verified[a.id] = !!(r && r.intact);
            toast(r && r.intact ? '校验通过：文件未被改动' : '校验不一致：文件可能被改动或丢失', r && r.intact ? 'ok' : 'err');
            renderAtts(ctx);
          } catch (e) { if (!(e && e.status === 401)) toast(errText(e), 'err'); }
        } }, '校验'),
        canEdit ? H('button', { type: 'button', class: 'btn btn-sm btn-danger', onclick: async function () {
          var v = await formModal({ title: '删除附件', okLabel: '删除', danger: true,
            intro: H('div', { class: 'callout callout-warn' }, '将删除附件“' + S(a.filename) + '”。删除会写入审计日志。'),
            fields: [{ key: 'reason', label: '删除原因', type: 'textarea', required: true }] });
          if (!v) return;
          try {
            await MF.api('DELETE', '/api/attachments/' + a.id + '?reason=' + encodeURIComponent(v.reason));
            toast('附件已删除', 'ok');
            await refreshServer(ctx);
          } catch (e) { if (!(e && e.status === 401)) toast(errText(e), 'err'); }
        } }, '删除') : null));
    });
    el.appendChild(card);
  }

  /* ================================================================== knowledge */
  function loadKb(ctx) {
    return MF.api('GET', '/api/methods/' + ctx.mid + '/kb?stage=' + encodeURIComponent(ctx.key)).then(function (list) {
      ctx.kb = Array.isArray(list) ? list : [];
      renderKb(ctx);
    }, function () { ctx.kb = []; renderKb(ctx); });
  }
  function renderKb(ctx) {
    var el = ctx.el.kb;
    MF.clear(el);
    var list = ctx.kb;
    var det = H('details', { class: 'st-details card' });
    if (ctx.kbOpen) det.open = true;
    det.addEventListener('toggle', function () { ctx.kbOpen = det.open; });
    det.appendChild(H('summary', null, '相关知识与坑' + (list ? '（' + list.length + '）' : '')));
    if (!list) det.appendChild(H('div', { class: 'muted small' }, '加载中……'));
    else {
      if (ctx.detail.can_submit) {
        det.appendChild(H('div', { style: { marginBottom: '8px' } },
          H('button', { type: 'button', class: 'btn btn-sm', onclick: function () { newLesson(ctx); } }, '＋ 沉淀经验')));
      }
      if (!list.length) det.appendChild(H('div', { class: 'muted small' }, '暂无与本阶段相关的知识条目。'));
      list.forEach(function (k) {
        det.appendChild(H('details', { class: 'st-kb' },
          H('summary', null, badge(KB_KIND[k.kind] || S(k.kind), KB_KIND_CLS[k.kind] || 'muted'), ' ', S(k.title)),
          H('div', { class: 'st-ro' }, S(k.body)),
          (k.tags && k.tags.length || k.source) ? H('div', { class: 'muted small', style: { paddingLeft: '4px' } },
            (k.tags && k.tags.length ? '标签：' + k.tags.join('、') + '  ' : '') + (k.source ? '来源：' + S(k.source) : '')) : null));
      });
    }
    el.appendChild(det);
  }
  async function newLesson(ctx) {
    var v = await formModal({
      title: '沉淀经验', okLabel: '保存到知识库', width: 560,
      intro: H('div', { class: 'muted small', style: { marginBottom: '8px' } }, '记录做对了什么、踩过什么坑；将关联到本阶段与本技术类型，供今后的方法开发参考。'),
      fields: [{ key: 'title', label: '标题', required: true, placeholder: '一句话概括' },
        { key: 'body', label: '内容', type: 'textarea', rows: 5, required: true, placeholder: '背景、现象、原因、怎么做' }]
    });
    if (!v) return;
    try {
      await MF.api('POST', '/api/methods/' + ctx.mid + '/lessons', { title: v.title, body: v.body, stage_key: ctx.key });
      toast('经验已沉淀', 'ok');
      ctx.kbOpen = true;
      await loadKb(ctx);
    } catch (e) { if (!(e && e.status === 401)) toast(errText(e), 'err'); }
  }

  /* ================================================================== revisions */
  function renderRevs(ctx) {
    var el = ctx.el.revs;
    MF.clear(el);
    var list = ctx.detail.revisions || [];
    var det = H('details', { class: 'st-details card' });
    if (ctx.revOpen) det.open = true;
    det.addEventListener('toggle', function () { ctx.revOpen = det.open; });
    det.appendChild(H('summary', null, '修订历史（' + list.length + '）'));
    det.appendChild(H('div', { class: 'st-help' }, '每次提交复核都会生成内容快照；签署与该快照的哈希绑定。当前修订 R' + S(ctx.detail.revision) + '。'));
    if (!list.length) det.appendChild(H('div', { class: 'muted small' }, '尚无提交快照。'));
    list.slice().reverse().forEach(function (r) {
      det.appendChild(H('div', { class: 'st-li' }, badge('R' + S(r.revision), 'info'),
        H('span', { class: 'muted small' }, '提交于 ' + fdt(r.created_at)),
        H('span', { class: 'st-mono muted', title: S(r.data_hash) }, '哈希 ' + S(r.data_hash).slice(0, 16))));
    });
    if (ctx.detail.hash) {
      det.appendChild(H('div', { class: 'muted small', style: { marginTop: '6px' } }, '当前内容哈希：', H('span', { class: 'st-mono' }, String(ctx.detail.hash).slice(0, 16))));
    }
    el.appendChild(det);
  }
})();
