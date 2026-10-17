/* MethodFlow - method.js (API v2)
 * 方法级视图：共同头部（项目链接/模板/生命周期）、总览（步进条/甘特/团队）、阶段外壳、实验列表与详情、文档(Word+PDF)、审计、知识。
 * 路由：/m/:mid、/m/:mid/:tab(experiments|docs|audit|kb)、/m/:mid/stage/:key、/m/:mid/exp/:eid
 * 依赖 core.js 提供的 window.MF.*（见 docs/前端契约.md）；阶段内容由 stage.js 的 MF.renderStage(container, mid, key, method) 渲染。
 */
(function () {
  'use strict';
  var MF = window.MF = window.MF || {};

  // =====================================================================  通用小工具
  function h() { return MF.h.apply(MF, arguments); }
  function api() { return MF.api.apply(MF, arguments); }
  function isNum(v) { return typeof v === 'number' && isFinite(v); }
  function tx(v, dash) {
    if (v === null || v === undefined || v === '' || (typeof v === 'number' && !isFinite(v))) return dash === undefined ? '—' : dash;
    return String(v);
  }
  function s0(v) { return v === null || v === undefined ? '' : String(v); }
  function toInt(v, d) { var n = parseInt(v, 10); return isFinite(n) ? n : (d || 0); }
  function fdate(s) {
    if (!s) return '—';
    try { return tx(MF.fmt && MF.fmt.date ? MF.fmt.date(s) : s); } catch (e) { return String(s); }
  }
  function fdt(s) {
    if (!s) return '—';
    try { return tx(MF.fmt && MF.fmt.datetime ? MF.fmt.datetime(s) : s); } catch (e) { return String(s); }
  }
  function errMsg(e) { return e && e.message ? e.message : '操作失败，请稍后重试'; }
  function fail(e) { MF.toast(errMsg(e), 'err'); }
  function fsize(n) {
    n = Number(n);
    if (!isFinite(n)) return '—';
    if (n < 1024) return n + ' B';
    if (n < 1048576) return (n / 1024).toFixed(1) + ' KB';
    return (n / 1048576).toFixed(1) + ' MB';
  }
  function p2(n) { return (n < 10 ? '0' : '') + n; }
  function todayStr() { var d = new Date(); return d.getFullYear() + '-' + p2(d.getMonth() + 1) + '-' + p2(d.getDate()); }
  function ymd(s) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s || '');
    return m ? Date.UTC(+m[1], +m[2] - 1, +m[3]) : null;
  }
  var DAY = 86400000;
  var MROLE = { owner: '方法负责人', author: '开发人员', reviewer: '复核人', approver: '批准人(QA)', viewer: '只读' };
  function roleLabel(r) { return MROLE[r] || tx((MF.roleLabel && MF.roleLabel(r)) || r); }
  function badge(text, kind) { return MF.badge ? MF.badge(text, kind) : h('span', { class: 'badge badge-' + (kind || 'muted') }, text); }
  function setDirty(v) { try { if (MF.dirtyGuard && MF.dirtyGuard.set) MF.dirtyGuard.set(!!v); } catch (e) { /* ignore */ } }
  function field(label, ctrl, hint, cls) {
    return h('div', { class: 'field ' + (cls || '') }, h('label', null, label), ctrl, hint ? h('div', { class: 'hint small muted' }, hint) : null);
  }
  function mkSelect(opts, value) {
    var s = h('select', { class: 'select' }, opts.map(function (o) {
      return h('option', { value: o.value, disabled: !!o.disabled }, o.label);
    }));
    s.value = value === null || value === undefined ? '' : String(value);
    if (s.selectedIndex < 0 && opts.length) s.selectedIndex = 0;
    return s;
  }
  function mkInput(type, value, ph) {
    var i = h('input', { class: 'input', type: type || 'text', placeholder: ph || '' });
    i.value = s0(value);
    return i;
  }
  function mkArea(value, rows, ph) {
    var t = h('textarea', { class: 'textarea', rows: String(rows || 3), placeholder: ph || '' });
    t.value = s0(value);
    return t;
  }
  // 方法团队（去重）：实验负责人必须是方法团队成员
  function uniqueMembers(p) {
    var seen = {}, out = [];
    (p.members || []).forEach(function (m) {
      if (!seen[m.user_id]) { seen[m.user_id] = 1; out.push({ id: m.user_id, name: tx(m.display_name || m.username, '用户#' + m.user_id) }); }
    });
    return out;
  }
  function stageTitle(p, key) {
    if (!key) return '未关联阶段';
    var s = (p.stages || []).filter(function (x) { return x.key === key; })[0];
    return s ? tx(s.title, key) : tx(key);
  }
  function stageObj(p, key) { return (p.stages || []).filter(function (x) { return x.key === key; })[0] || null; }
  function isOwner(p) { return (p.my_roles || []).indexOf('owner') >= 0; }
  // 是否可编辑内容：以后端 permissions.can_edit_content 为准（含方法/项目进行中）
  function canEdit(p) { return !!(p.permissions && p.permissions.can_edit_content); }
  function hasEditRole(p) { var r = p.my_roles || []; return r.indexOf('owner') >= 0 || r.indexOf('author') >= 0; }
  function crumbs(list) { if (MF.setCrumbs) MF.setCrumbs(list); }
  function go(path) { MF.navigate(path); }
  var FROZEN_STATUS = ['in_review', 'approved', 'completed'];
  function planFrozen(p) { var s = stageObj(p, 'plan'); return !!(s && FROZEN_STATUS.indexOf(s.status) >= 0); }
  function anyLocked(p) { return (p.stages || []).some(function (s) { return s.status === 'approved' || s.status === 'completed'; }); }

  // 带内联错误的对话框：ok(data, ctl) 抛错 -> 错误显示在对话框内并保持打开
  function dialog(opts) {
    var f = opts.make(opts.initial);
    var result;
    return MF.modal({
      title: opts.title, body: f.node, width: opts.width,
      buttons: [{ label: '取消', value: null }, {
        label: opts.okLabel || '确定', kind: opts.kind || 'primary', value: 'ok',
        onClick: function (ctl) {
          return Promise.resolve().then(function () { return opts.ok(f.read(), ctl); }).then(function (res) { result = res; });
        }
      }]
    }).then(function (r) { return r === 'ok' ? { result: result } : null; });
  }
  // 填写原因（或其他必填说明）
  function askReason(title, label, opts) {
    opts = opts || {};
    return dialog({
      title: title, okLabel: opts.okLabel || '确定', kind: opts.kind || 'primary', initial: '',
      make: function (draft) {
        var ta = mkArea(draft, 3, opts.placeholder || '');
        var node = h('div', null, opts.intro ? h('p', { class: 'muted' }, opts.intro) : null, field(label, ta));
        return { node: node, read: function () { return ta.value; } };
      },
      ok: function (v) {
        if (opts.required !== false && !String(v).trim()) throw new Error('请填写' + label);
        return String(v).trim();
      }
    }).then(function (r) { return r ? r.result : null; });
  }
  // 需要电子签名/重新认证（原因 + 密码）的动作；口令错误(403)时重新弹出
  function signAction(opts, run) {
    return new Promise(function (resolve) {
      function ask() {
        MF.askSign(opts).then(function (r) {
          if (!r) { resolve(null); return; }
          Promise.resolve().then(function () { return run(r); }).then(function (res) { resolve({ result: res }); }, function (e) {
            fail(e);
            if (e && e.status === 403 && !(e.data && e.data.must_change)) ask(); else resolve(null);
          });
        });
      }
      ask();
    });
  }
  function infoModal(title, node) {
    return MF.modal({ title: title, body: node, buttons: [{ label: '知道了', kind: 'primary', value: 'ok' }] });
  }

  // =====================================================================  样式
  var CSS = [
    '.mt-head{margin-bottom:12px}',
    '.mt-title{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:0 0 6px}',
    '.mt-title h2{margin:0;font-size:1.3rem}',
    '.mt-code{font-family:Consolas,Menlo,monospace;background:var(--c-bg,#f3f4f6);border:1px solid var(--c-border,#d0d7de);border-radius:6px;padding:1px 8px;font-size:.9rem}',
    '.mt-meta{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:.88rem;color:var(--c-muted,#6b7280);margin-bottom:8px}',
    '.mt-meta b{color:var(--c-text,#1f2328);font-weight:600}',
    '.mt-prog{display:flex;align-items:center;gap:10px;max-width:520px;margin:6px 0}',
    '.mt-prog .progress{flex:1}',
    '.mt-actions{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}',
    '.mt-warn{margin:6px 0;font-size:.88rem}',
    '.mt-tabs{margin:8px 0 14px;overflow-x:auto;white-space:nowrap}',
    '.mt-tabs a{text-decoration:none;display:inline-block}',
    '.mt-grid4{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:14px}',
    '.mt-stat .mt-big{font-size:1.7rem;font-weight:700;line-height:1.2}',
    '.mt-stat .small{margin-top:2px}',
    '.mt-steps{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:10px}',
    '.mt-stage{display:block;text-decoration:none;color:inherit;border:1px solid var(--c-border,#d0d7de);border-left-width:4px;border-radius:8px;padding:9px 10px;background:var(--c-card,#fff);transition:box-shadow .12s}',
    '.mt-stage:hover{box-shadow:0 2px 8px rgba(0,0,0,.14);text-decoration:none}.mt-stage:hover *{text-decoration:none}',
    '.mt-tb .select,.mt-tb .input{width:auto;min-width:130px}',
    '.mt-kbg>summary{cursor:pointer;font-weight:600;margin:10px 0 4px}',
    '.mt-stage-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:3px}',
    '.mt-ord{display:inline-block;min-width:22px;height:22px;line-height:22px;text-align:center;border-radius:11px;background:var(--c-bg,#eee);font-size:.8rem;font-weight:700}',
    '.mt-gate{font-size:.78rem;font-weight:600;color:var(--c-primary,#2563eb)}',
    '.mt-nogate{color:var(--c-muted,#6b7280);font-weight:400}',
    '.mt-stage-title{font-weight:600;margin:2px 0 5px;line-height:1.3}',
    '.mt-stage .progress{margin:5px 0 3px}',
    '.mt-st-not_started{border-left-color:var(--c-border,#9ca3af)}',
    '.mt-st-in_progress{border-left-color:var(--c-warn,#d97706)}',
    '.mt-st-in_review{border-left-color:var(--c-primary,#2563eb)}',
    '.mt-st-returned{border-left-color:var(--c-err,#dc2626)}',
    '.mt-st-approved,.mt-st-completed{border-left-color:var(--c-ok,#16a34a)}',
    '.mt-stage.mt-cur{box-shadow:0 0 0 2px var(--c-primary,#2563eb) inset}',
    '.mt-chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}',
    '.mt-chip{display:inline-flex;align-items:center;gap:5px;text-decoration:none;color:inherit;border:1px solid var(--c-border,#d0d7de);border-radius:16px;padding:2px 10px;font-size:.85rem;background:var(--c-card,#fff)}',
    '.mt-chip.mt-on{border-color:var(--c-primary,#2563eb);box-shadow:0 0 0 1px var(--c-primary,#2563eb)}',
    '.mt-chip.mt-blocked{opacity:.55;border-style:dashed}',
    '.mt-dot{width:9px;height:9px;border-radius:50%;background:var(--c-border,#9ca3af);display:inline-block}',
    '.mt-dot-in_progress{background:var(--c-warn,#d97706)}.mt-dot-in_review{background:var(--c-primary,#2563eb)}.mt-dot-returned{background:var(--c-err,#dc2626)}',
    '.mt-dot-approved,.mt-dot-completed{background:var(--c-ok,#16a34a)}',
    '.mt-gwrap{overflow-x:auto}',
    '.mt-gantt{min-width:640px}',
    '.mt-grow{display:grid;grid-template-columns:170px 1fr;align-items:center;border-top:1px solid var(--c-border,#e5e7eb)}',
    '.mt-glabel{font-size:.85rem;padding:3px 8px 3px 0;line-height:1.25}',
    '.mt-track{position:relative;height:30px}',
    '.mt-axis{position:relative;height:20px;font-size:.75rem;color:var(--c-muted,#6b7280)}',
    '.mt-tick{position:absolute;top:2px;padding-left:3px;border-left:1px solid var(--c-border,#d0d7de);height:18px;white-space:nowrap}',
    '.mt-grid{position:absolute;top:0;bottom:0;width:0;border-left:1px dashed var(--c-border,#e5e7eb)}',
    '.mt-plan{position:absolute;top:5px;height:8px;border-radius:4px;background:var(--c-muted,#9ca3af);opacity:.45}',
    '.mt-plan.mt-over{background:var(--c-err,#dc2626);opacity:.75}',
    '.mt-act{position:absolute;top:16px;height:9px;border-radius:4px;background:var(--c-warn,#d97706)}',
    '.mt-act-approved,.mt-act-completed{background:var(--c-ok,#16a34a)}',
    '.mt-act-in_review{background:var(--c-primary,#2563eb)}',
    '.mt-act-returned{background:var(--c-err,#dc2626)}',
    '.mt-act.mt-open{background-image:repeating-linear-gradient(45deg,rgba(255,255,255,.35) 0 4px,transparent 4px 8px)}',
    '.mt-today{position:absolute;top:0;bottom:0;width:0;border-left:2px solid var(--c-err,#dc2626);z-index:2}',
    '.mt-legend{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:.8rem;color:var(--c-muted,#6b7280);margin-top:8px;align-items:center}',
    '.mt-legend i{display:inline-block;width:18px;height:8px;border-radius:4px;vertical-align:middle;margin-right:4px}',
    '.mt-two{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}',
    '.mt-over-txt{color:var(--c-err,#dc2626);font-weight:600}',
    '.mt-tw{overflow-x:auto}',
    '.mt-tw table{min-width:620px}',
    '.mt-ro{background:var(--c-bg,#f3f4f6)!important;cursor:default}',
    '.mt-savebar{position:sticky;top:0;z-index:5;display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding:8px 12px;margin-bottom:12px;background:var(--c-card,#fff);border:1px solid var(--c-border,#d0d7de);border-radius:8px}',
    '.mt-dirty{color:var(--c-warn,#d97706);font-weight:600;font-size:.88rem}',
    '.mt-res td{padding:3px}',
    '.mt-res input,.mt-res select{width:100%;box-sizing:border-box}',
    '.mt-v-ok{color:var(--c-ok,#16a34a)}.mt-v-no{color:var(--c-err,#dc2626)}',
    '.mt-pre{white-space:pre-wrap;word-break:break-word;font-family:Consolas,Menlo,monospace;font-size:.82rem;background:var(--c-bg,#f3f4f6);border-radius:6px;padding:8px;margin:0}',
    '.mt-kb-body{white-space:pre-wrap;word-break:break-word;margin:4px 0}',
    '.mt-kbi{border:1px solid var(--c-border,#d0d7de);border-radius:8px;padding:9px 12px;margin:8px 0;background:var(--c-card,#fff)}',
    '.mt-hash{font-family:Consolas,Menlo,monospace;font-size:.82rem}',
    '.mt-clickrow{cursor:pointer}',
    '.mt-nowrap{white-space:nowrap}',
    '.mt-tag{display:inline-block;font-size:12px;font-weight:600;border:1px solid var(--c-warn,#d97706);color:var(--c-warn,#b45309);background:rgba(217,119,6,.12);border-radius:8px;padding:0 7px;margin-left:6px;white-space:nowrap}',
    '.mt-form2{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:0 14px}',
    '@media (max-width:640px){.mt-grow{grid-template-columns:110px 1fr}.mt-title h2{font-size:1.1rem}}'
  ].join('\n');
  function injectStyle() {
    if (document.getElementById('mt-style')) return;
    var st = document.createElement('style');
    st.id = 'mt-style';
    st.textContent = CSS;
    document.head.appendChild(st);
  }
  // =====================================================================  外壳（共同头部 + 标签页）
  var seq = 0;
  var METH_STATUS = {
    active: ['进行中', 'info'], completed: ['已完成', 'ok'], archived: ['已归档', 'muted'], cancelled: ['已取消', 'err']
  };
  var PROJ_STATUS_LABEL = { active: '进行中', paused: '暂停', completed: '已完成', archived: '已归档' };
  var LIFE = [['development', '开发'], ['validation', '验证'], ['transfer', '转移'], ['routine', '常规使用'], ['retired', '停用']];
  var LIFE_KIND = { development: 'info', validation: 'warn', transfer: 'warn', routine: 'ok', retired: 'muted' };
  var STAGE_LOCKED = ['approved', 'completed'];
  function lifeLabel(p) { return tx(p.lifecycle_label, (LIFE.filter(function (x) { return x[0] === p.lifecycle; })[0] || [0, p.lifecycle])[1]); }
  function curStageKey(p) {
    var cs = p.summary && p.summary.current_stage;
    if (cs && cs.key) return cs.key;
    return p.stages && p.stages.length ? p.stages[p.stages.length - 1].key : '';
  }

  function shell(container, mid, active, builder, extra) {
    injectStyle();
    var my = ++seq;
    setDirty(false);
    MF.clear(container);
    var root = h('div', { class: 'mt-root' }, h('div', { class: 'muted' }, '加载中…'));
    container.appendChild(root);
    function alive() { return my === seq && root.parentNode === container; }
    crumbs([{ label: '项目', href: '/projects' }, { label: '方法 #' + mid }]);
    return api('GET', '/api/methods/' + mid).then(function (p) {
      if (!alive()) return;
      MF.clear(root);
      var pr = p.project || {};
      var tail = extra ? extra(p) : [];
      var cr = [{ label: '项目', href: '/projects' }, { label: tx(pr.code, '项目'), href: '/pr/' + p.project_id },
        tail.length ? { label: tx(p.code) + ' ' + tx(p.name, ''), href: '/m/' + p.id } : { label: tx(p.code) + ' ' + tx(p.name, '') }];
      crumbs(cr.concat(tail));
      root.appendChild(renderHeader(p, active));
      var body = h('div', { class: 'mt-body' });
      root.appendChild(body);
      return Promise.resolve(builder(body, p, alive)).catch(function (e) {
        if (!alive()) return;
        MF.clear(body);
        body.appendChild(h('div', { class: 'callout callout-err' }, '加载失败：' + errMsg(e)));
      });
    }, function (e) {
      if (!alive()) return;
      if (e && e.status === 401) return;
      MF.clear(root);
      root.appendChild(h('div', { class: 'card' }, h('h3', null, e && e.status === 403 ? '无权访问该方法' : (e && e.status === 404 ? '方法不存在' : '无法加载方法')),
        h('p', { class: 'muted' }, errMsg(e)), h('a', { class: 'btn', href: '#/methods' }, '返回方法列表')));
    });
  }

  function renderHeader(p, active) {
    var st = METH_STATUS[p.status] || [tx(p.status_label, p.status), 'muted'];
    var sum = p.summary || {};
    var pr = p.project || {};
    var pct = isNum(sum.progress) ? sum.progress : 0;
    var cs = sum.current_stage;
    var stageKey = curStageKey(p);
    var perm = p.permissions || {};

    var meta = h('div', { class: 'mt-meta' },
      h('span', null, '所属项目：', h('a', { href: '#/pr/' + p.project_id }, h('b', null, tx(pr.code) + ' ' + tx(pr.name, ''))),
        pr.status && pr.status !== 'active' ? badge('项目' + (PROJ_STATUS_LABEL[pr.status] || pr.status), 'warn') : null),
      h('span', null, '技术模板：', h('b', null, tx(p.technique_label || (p.meta && p.meta.template_label) || p.technique)), '　模板版本 ', h('b', null, tx(p.template_version))),
      h('span', null, '方法版本：', h('b', null, tx(p.method_version))),
      p.analyte ? h('span', null, '被测属性：', h('b', null, tx(p.analyte))) : null,
      p.matrix ? h('span', null, '样品基质：', h('b', null, tx(p.matrix))) : null,
      h('span', null, '负责人：', h('b', null, tx(p.owner_name))),
      h('span', null, '当前阶段：', cs ? h('a', { href: '#/m/' + p.id + '/stage/' + cs.key }, tx(cs.title)) : h('b', null, '全部阶段已通过')),
      h('span', null, '计划：', fdate(p.planned_start), ' ~ ', fdate(p.planned_end)));

    var warns = [];
    if (p.signatures_ok === false) {
      var bad = p.bad_signatures || [];
      warns.push(h('div', { class: 'callout callout-err mt-warn' }, h('b', null, '签名完整性校验失败：'),
        '已签署阶段的内容与签署时的哈希不一致，数据可能被绕过系统改动。请立即通知管理员/QA，并勿将本方法生成的文档用作批准文件。',
        bad.length ? h('ul', { style: 'margin:4px 0 0 18px;padding:0' }, bad.map(function (b) {
          return h('li', null, tx(b.title || b.stage) + (b.revision !== undefined ? '（R' + b.revision + '）' : '') + '：' + (b.problems || []).join('；'));
        })) : null));
    }
    if (sum.overdue && sum.overdue.length) warns.push(h('div', { class: 'callout callout-warn mt-warn' }, '⚠ 逾期阶段（超过计划结束日期且未通过）：' + sum.overdue.join('、')));
    if (sum.stale && sum.stale.length) warns.push(h('div', { class: 'callout callout-warn mt-warn' }, '⚠ 已失效阶段（上游被重新打开，需重新复核）：' + sum.stale.join('、')));
    if (p.status !== 'active') warns.push(h('div', { class: 'callout mt-warn' }, '本方法当前为“' + st[0] + '”状态，' + (p.status === 'completed' ? '内容已完成，不可再编辑阶段。' : '阶段、实验、附件均不可修改。') + (isOwner(p) ? '方法负责人可“恢复为进行中”（须填写原因并重新认证）。' : '')));
    if (pr.status && pr.status !== 'active') warns.push(h('div', { class: 'callout callout-warn mt-warn' }, '所属项目 ' + tx(pr.code) + ' 当前为“' + (PROJ_STATUS_LABEL[pr.status] || pr.status) + '”，在项目恢复为“进行中”之前，本方法的内容不可修改。'));

    var actions = h('div', { class: 'mt-actions' });
    if (MF.hasRole && MF.hasRole('author', 'admin')) actions.appendChild(h('button', { class: 'btn btn-sm', onclick: function () { cloneMethod(p); } }, '克隆方法'));
    actions.appendChild(h('a', { class: 'btn btn-sm', href: '/api/methods/' + p.id + '/export', download: '' }, '导出 JSON'));
    if (perm.can_edit_info) {
      actions.appendChild(h('button', { class: 'btn btn-sm', onclick: function () { editMethod(p); } }, '编辑基本信息'));
      if (p.status === 'active') {
        actions.appendChild(h('button', { class: 'btn btn-sm btn-primary', onclick: function () { setMethodStatus(p, 'completed'); } }, '完成方法'));
        actions.appendChild(h('button', { class: 'btn btn-sm', onclick: function () { setMethodStatus(p, 'archived'); } }, '归档'));
        actions.appendChild(h('button', { class: 'btn btn-sm btn-danger', onclick: function () { setMethodStatus(p, 'cancelled'); } }, '取消方法'));
      } else {
        actions.appendChild(h('button', { class: 'btn btn-sm', onclick: function () { setMethodStatus(p, 'active'); } }, '恢复为进行中'));
        if (p.status === 'completed') actions.appendChild(h('button', { class: 'btn btn-sm', onclick: function () { setMethodStatus(p, 'archived'); } }, '归档'));
      }
    }
    if (perm.can_change_lifecycle) actions.appendChild(h('button', { class: 'btn btn-sm', onclick: function () { changeLifecycle(p); } }, '变更生命周期'));
    if (MF.records) MF.records.headerActions(p).forEach(function (b) { actions.appendChild(b); });
    if (p.status === 'active' && hasEditRole(p)) actions.appendChild(h('button', { class: 'btn btn-sm', title: '从某一步起按计划周数重新排布后续各步的计划日期（已通过的步骤不变）', onclick: function () { rescheduleDialog(p); } }, '重排计划'));

    var tabs = [
      { k: 'overview', l: '总览', path: '/m/' + p.id },
      { k: 'stage', l: '阶段', path: '/m/' + p.id + '/stage/' + stageKey },
      { k: 'experiments', l: '实验', path: '/m/' + p.id + '/experiments' },
      { k: 'docs', l: '文档', path: '/m/' + p.id + '/docs' },
      { k: 'audit', l: '审计', path: '/m/' + p.id + '/audit' },
      { k: 'kb', l: '知识', path: '/m/' + p.id + '/kb' }
    ];
    (MF.methodTabs || []).forEach(function (t) {
      var at = tabs.map(function (x) { return x.k; }).indexOf('docs');
      tabs.splice(at < 0 ? tabs.length : at, 0, { k: t.k, l: t.l, path: '/m/' + p.id + '/' + t.k });
    });
    if (!stageKey) tabs.splice(1, 1);

    return h('div', { class: 'mt-head' },
      h('div', { class: 'mt-title' }, h('span', { class: 'mt-code' }, tx(p.code)), h('h2', null, tx(p.name, '（未命名方法）')),
        h('span', { title: '生命周期' }, badge(lifeLabel(p), LIFE_KIND[p.lifecycle] || 'muted')),
        h('span', { title: '开发工作状态' }, badge(st[0], st[1]))),
      meta,
      h('div', { class: 'mt-prog' }, h('span', { class: 'small muted mt-nowrap' }, '总进度'), MF.progressBar(pct), h('b', null, pct + '%')),
      warns, actions,
      h('div', { class: 'tabs mt-tabs' }, tabs.map(function (t) {
        return h('a', { class: 'tab' + (t.k === active ? ' tab-active' : ''), href: '#' + t.path }, t.l);
      })));
  }

  // ---------------------------------------------------------------- 头部动作
  function rescheduleDialog(p) {
    var open = (p.stages || []).filter(function (s) { return s.status !== 'approved' && s.status !== 'completed'; });
    if (!open.length) { MF.toast('所有阶段都已通过/完成，无需重排', 'warn'); return; }
    var sel = h('select', { class: 'select' }, open.map(function (s) { return h('option', { value: s.key }, s.ord + '. ' + s.title); }));
    var dt = h('input', { class: 'input', type: 'date', value: todayStr() });
    MF.modal({
      title: '重排计划', width: 480,
      body: h('div', null, h('p', { class: 'small muted' }, '从所选步骤起，按各步的计划周数依次重新排布计划日期（含其未完成的实验）；已通过/完成的步骤不变。'),
        MF.field('从哪一步开始重排', sel), MF.field('该步骤的新开始日期', dt)),
      buttons: [{ label: '取消', value: null }, { label: '重排', kind: 'primary', onClick: async function (ctl) {
        try {
          await api('POST', '/api/methods/' + p.id + '/reschedule', { from_stage: sel.value, start_date: dt.value });
          ctl.close(true);
        } catch (e) { ctl.error(e.message || '重排失败'); ctl.setBusy(false); return false; }
      } }]
    }).then(function (ok) { if (ok) { MF.toast('计划已重排', 'ok'); MF.reload(); } });
  }

  function cloneMethod(p) {
    api('GET', '/api/projects').catch(function () { return []; }).then(function (projs) {
      var isAdmin = MF.hasRole && MF.hasRole('admin');
      var opts = (projs || []).filter(function (x) {
        if (x.status !== 'active') return false;
        return isAdmin || (x.my_roles || []).some(function (r) { return r === 'owner' || r === 'member'; });
      }).map(function (x) { return { value: String(x.id), label: tx(x.code) + ' ' + tx(x.name, '') }; });
      if (!opts.some(function (o) { return o.value === String(p.project_id); })) opts.unshift({ value: String(p.project_id), label: tx(p.project && p.project.code) + ' ' + tx(p.project && p.project.name, '') + '（当前）' });
      return dialog({
        title: '克隆方法', okLabel: '克隆', initial: tx(p.name, '') + '（副本）',
        make: function (draft) {
          var inp = mkInput('text', draft);
          var sel = mkSelect(opts, String(p.project_id));
          return {
            node: h('div', null,
              h('p', { class: 'muted' }, '将以相同的技术模板创建新方法，并复制被测属性/基质/用途与各阶段已填写的章节内容；检查清单重置，签署、团队（仅您为负责人）、实验及结果、附件不会复制。可克隆到同一项目或另一个您有权新增方法的项目。'),
              field('新方法名称', inp), field('目标项目', sel, '只能选择您是负责人或成员、且处于“进行中”的项目。')),
            read: function () { return { title: inp.value, project_id: sel.value }; }
          };
        },
        ok: function (d) {
          if (!String(d.title).trim()) throw new Error('请填写新方法名称');
          return api('POST', '/api/methods/' + p.id + '/clone', { title: String(d.title).trim(), project_id: toInt(d.project_id) });
        }
      });
    }).then(function (r) { if (r && r.result && r.result.id) { MF.toast('已克隆为新方法', 'ok'); go('/m/' + r.result.id); } });
  }

  function editMethod(p) {
    var frozen = anyLocked(p);
    var keys = [['name', '方法名称', frozen], ['analyte', '被测属性', frozen], ['matrix', '样品基质', frozen], ['intended_use', '预期用途', frozen], ['phase', '研发阶段（如 I 期/BLA）', false], ['method_version', '方法版本（如 V0.1）', false]];
    dialog({
      title: '编辑方法基本信息', okLabel: '保存', width: 640,
      initial: { name: s0(p.name), analyte: s0(p.analyte), matrix: s0(p.matrix), intended_use: s0(p.intended_use), phase: s0(p.phase), method_version: s0(p.method_version),
        planned_start: s0(p.planned_start).slice(0, 10), planned_end: s0(p.planned_end).slice(0, 10), reason: '' },
      make: function (d) {
        var ctr = {};
        var node = h('div', null, frozen ? h('div', { class: 'callout callout-warn small' }, '已有阶段通过评审（立项章节签署覆盖了方法名称、被测属性、样品基质、预期用途），这四项已冻结，不可修改。如确需修改，请先由负责人/批准人重新打开“立项”阶段。') : null);
        keys.forEach(function (k) {
          ctr[k[0]] = k[0] === 'intended_use' ? mkArea(d[k[0]], 3) : mkInput('text', d[k[0]]);
          if (k[2]) { ctr[k[0]].disabled = true; ctr[k[0]].classList.add('mt-ro'); }
          node.appendChild(field(k[1], ctr[k[0]]));
        });
        ctr.planned_start = mkInput('date', d.planned_start);
        ctr.planned_end = mkInput('date', d.planned_end);
        ctr.reason = mkInput('text', d.reason, '修改原因（可选，计入审计）');
        node.appendChild(h('div', { class: 'mt-form2' }, field('计划开始', ctr.planned_start), field('计划结束', ctr.planned_end)));
        node.appendChild(field('修改原因', ctr.reason));
        return { node: node, read: function () { var o = {}; Object.keys(ctr).forEach(function (k) { o[k] = ctr[k].value; }); return o; } };
      },
      ok: function (d) {
        if (!d.name.trim()) throw new Error('方法名称不能为空');
        var patch = {};
        keys.forEach(function (k) { if (!k[2] && d[k[0]] !== s0(p[k[0]])) patch[k[0]] = d[k[0]]; });
        ['planned_start', 'planned_end'].forEach(function (k) { if (d[k] && d[k] !== s0(p[k]).slice(0, 10)) patch[k] = d[k]; });
        if (!Object.keys(patch).length) throw new Error('没有修改内容');
        if (d.reason.trim()) patch.reason = d.reason.trim();
        return api('PATCH', '/api/methods/' + p.id, patch);
      }
    }).then(function (r) { if (r) { MF.toast('已保存', 'ok'); MF.reload(); } });
  }

  function setMethodStatus(p, status) {
    if (status === 'active') {
      // 非进行中 -> 进行中：须原因 + 口令（重新认证）
      signAction({
        title: '恢复为进行中：' + tx(p.code),
        meaning: '我确认将方法 ' + tx(p.code) + '（' + tx(p.name, '') + '）由“' + tx(p.status_label) + '”恢复为“进行中”，恢复后阶段内容可再次修改。该操作将写入审计日志。',
        needComment: true, commentRequired: true, commentLabel: '恢复原因（必填）'
      }, function (r) {
        return api('PATCH', '/api/methods/' + p.id, { status: 'active', reason: r.comment, password: r.password });
      }).then(function (r) { if (r) { MF.toast('方法已恢复为进行中', 'ok'); MF.reload(); } });
      return;
    }
    var cfg = {
      completed: { t: '完成方法', intro: '将方法标记为“已完成”。要求全部阶段已通过/完成且无失效阶段，否则系统会拒绝并说明原因。', req: false, kind: 'primary' },
      archived: { t: '归档方法', intro: '归档后方法不再出现在进行中列表，阶段/实验/附件均不可修改；可由方法负责人恢复（须原因+口令）。', req: false, kind: 'primary' },
      cancelled: { t: '取消方法', intro: '取消后方法停止推进，内容不可修改；记录会保留。请说明取消原因。', req: true, kind: 'danger' }
    }[status];
    askReason(cfg.t + '：' + tx(p.code), cfg.req ? '原因（必填）' : '原因（可选）', { intro: cfg.intro, okLabel: cfg.t, kind: cfg.kind, required: cfg.req, placeholder: cfg.req ? '必填' : '可选，计入审计' }).then(function (reason) {
      if (reason === null) return null;
      var body = { status: status };
      if (reason) body.reason = reason;
      return api('PATCH', '/api/methods/' + p.id, body).then(function () { MF.toast('方法状态已更新', 'ok'); MF.reload(); }, function (e) {
        if (status === 'completed' && e && e.status === 422) return infoModal('无法完成方法', h('div', { class: 'callout callout-err' }, errMsg(e)));
        fail(e);
      });
    });
  }

  function changeLifecycle(p) {
    dialog({
      title: '变更生命周期：' + tx(p.code), okLabel: '下一步：签名确认', initial: '',
      make: function () {
        var opts = LIFE.filter(function (x) { return x[0] !== p.lifecycle; }).map(function (x) { return { value: x[0], label: x[1] }; });
        var sel = mkSelect(opts, opts[0] && opts[0].value);
        return {
          node: h('div', null,
            h('p', { class: 'muted' }, 'V0.2 仅提供“开发”阶段的完整流程；验证/转移/常规使用/停用在此作为状态字段手动记录，并写入审计日志。当前生命周期：', h('b', null, lifeLabel(p)), '。'),
            field('新的生命周期', sel)),
          read: function () { return sel.value; }
        };
      },
      ok: function (v) { if (!v) throw new Error('请选择新的生命周期'); return v; }
    }).then(function (r) {
      if (!r) return;
      var to = r.result;
      var toL = (LIFE.filter(function (x) { return x[0] === to; })[0] || [0, to])[1];
      return signAction({
        title: '变更生命周期：' + lifeLabel(p) + ' → ' + toL,
        meaning: '我确认将方法 ' + tx(p.code) + ' 的生命周期由“' + lifeLabel(p) + '”变更为“' + toL + '”。该变更及原因将写入审计日志。',
        needComment: true, commentRequired: true, commentLabel: '变更原因（必填）'
      }, function (s) {
        return api('POST', '/api/methods/' + p.id + '/lifecycle', { lifecycle: to, reason: s.comment, password: s.password });
      }).then(function (x) { if (x) { MF.toast('生命周期已变更为“' + toL + '”', 'ok'); MF.reload(); } });
    });
  }

  // =====================================================================  总览
  function renderOverview(body, p, alive) {
    body.appendChild(h('div', { class: 'muted' }, '加载中…'));
    var stages = p.stages || [];
    var thr = (MF.state && MF.state.app && MF.state.app.rpn_threshold) || 120;
    var sthr = (MF.state && MF.state.app && MF.state.app.severity_threshold) || 8;
    var riskP = stages.some(function (s) { return s.key === 'risk'; }) ? api('GET', '/api/methods/' + p.id + '/stages/risk').catch(function () { return null; }) : Promise.resolve(null);
    return Promise.all([api('GET', '/api/methods/' + p.id + '/experiments').catch(function () { return null; }), riskP]).then(function (rs) {
      if (!alive()) return;
      var exps = rs[0], risk = rs[1];
      MF.clear(body);
      if (MF.guide && MF.guide.nextStepCard && p.status === 'active') body.appendChild(MF.guide.nextStepCard(p));
      if (MF.records) { var ln = MF.records.lineage(p); if (ln) body.appendChild(ln); }
      var today = todayStr();

      // ---- 概要卡片
      var locked = stages.filter(function (s) { return STAGE_LOCKED.indexOf(s.status) >= 0 && !s.stale; }).length;
      var sum = p.summary || {};
      var expCard;
      var expOverdue = 0;
      if (exps) {
        var live = exps.filter(function (e) { return e.status !== 'cancelled'; });
        var done = exps.filter(function (e) { return e.status === 'done'; }).length;
        var running = exps.filter(function (e) { return e.status === 'running'; }).length;
        var late = exps.filter(function (e) { return e.added_after_plan && e.status !== 'cancelled'; }).length;
        expOverdue = exps.filter(function (e) { return (e.status === 'planned' || e.status === 'running') && e.planned_end && String(e.planned_end).slice(0, 10) < today; }).length;
        expCard = h('div', { class: 'card mt-stat' }, h('div', { class: 'muted small' }, '实验完成'), h('div', { class: 'mt-big' }, done + ' / ' + live.length),
          h('div', { class: 'small muted' }, '进行中 ' + running + (exps.length - live.length ? '，已取消 ' + (exps.length - live.length) : '') + (late ? '，方案后新增 ' + late : '')),
          h('a', { class: 'small', href: '#/m/' + p.id + '/experiments' }, '查看实验 →'));
      } else {
        expCard = h('div', { class: 'card mt-stat' }, h('div', { class: 'muted small' }, '实验完成'), h('div', { class: 'mt-big' }, '—'), h('div', { class: 'small muted' }, '暂时无法读取'));
      }
      var riskCard;
      var fm = risk && risk.data && risk.data.sections && risk.data.sections.fmea;
      if (Array.isArray(fm)) {
        var rows = fm.filter(function (r) { return r && (r.mode || r.S || r.O || r.D); });
        var high = rows.filter(function (r) { var S = toInt(r.S, NaN), O = toInt(r.O, NaN), D = toInt(r.D, NaN); return isFinite(S) && isFinite(O) && isFinite(D) && (S * O * D >= thr || S >= sthr); });
        riskCard = h('div', { class: 'card mt-stat' }, h('div', { class: 'muted small' }, '高风险项（FMEA）'),
          h('div', { class: 'mt-big', style: high.length ? 'color:var(--c-err,#dc2626)' : '' }, String(high.length)),
          h('div', { class: 'small muted' }, 'RPN ≥ ' + thr + ' 或严重度 ≥ ' + sthr + '；共 ' + rows.length + ' 项'));
      } else {
        riskCard = h('div', { class: 'card mt-stat' }, h('div', { class: 'muted small' }, '高风险项（FMEA）'), h('div', { class: 'mt-big' }, '—'), h('div', { class: 'small muted' }, '风险评估阶段尚未填写'));
      }
      var overdueN = (sum.overdue || []).length;
      body.appendChild(h('div', { class: 'mt-grid4' },
        h('div', { class: 'card mt-stat' }, h('div', { class: 'muted small' }, '总进度'), h('div', { class: 'mt-big' }, (isNum(sum.progress) ? sum.progress : 0) + '%'), MF.progressBar(isNum(sum.progress) ? sum.progress : 0)),
        h('div', { class: 'card mt-stat' }, h('div', { class: 'muted small' }, '阶段通过'), h('div', { class: 'mt-big' }, locked + ' / ' + stages.length),
          h('div', { class: 'small muted' }, sum.current_stage ? '当前：' + tx(sum.current_stage.title) : '全部阶段已通过')),
        expCard, riskCard,
        h('div', { class: 'card mt-stat' }, h('div', { class: 'muted small' }, '逾期'),
          h('div', { class: 'mt-big', style: (overdueN || expOverdue) ? 'color:var(--c-err,#dc2626)' : '' }, String(overdueN + expOverdue)),
          h('div', { class: 'small muted' }, '阶段 ' + overdueN + ' · 实验 ' + (exps ? expOverdue : '—')))));

      // ---- 阶段步进条
      var cur = sum.current_stage && sum.current_stage.key;
      body.appendChild(h('div', { class: 'card' }, h('h3', null, '阶段进度'),
        h('p', { class: 'muted small' }, '点击阶段进入编辑页。“🔒 G1”表示该阶段设有评审门，须由指定角色的非编辑者电子签名后方可锁定并进入下一阶段。'),
        h('div', { class: 'mt-steps' }, stages.map(function (s) { return stageCard(p, s, cur); }))));

      // ---- 甘特
      body.appendChild(h('div', { class: 'card' }, h('h3', null, '计划与实际（甘特图）'), gantt(stages, today)));

      // ---- 成员 + 方法信息
      body.appendChild(h('div', { class: 'mt-two' }, membersCard(p), infoCard(p)));
    });
  }

  function stageCard(p, s, curKey) {
    var gateKey = s.gate ? s.gate.split(/\s+/)[0] : '';
    var roles = (s.gate_roles || []).map(roleLabel).join(' + ');
    var pct = isNum(s.progress) ? s.progress : 0;
    var range = (s.planned_start || s.planned_end) ? fdate(s.planned_start) + ' ~ ' + fdate(s.planned_end) : '未设置计划日期';
    var over = STAGE_LOCKED.indexOf(s.status) < 0 && s.planned_end && String(s.planned_end).slice(0, 10) < todayStr();
    return h('a', { class: 'mt-stage mt-st-' + s.status + (s.key === curKey ? ' mt-cur' : ''), href: '#/m/' + p.id + '/stage/' + s.key, title: tx(s.desc, '') },
      h('div', { class: 'mt-stage-top' }, h('span', { class: 'mt-ord' }, String(tx(s.ord, '·'))),
        s.gate ? h('span', { class: 'mt-gate' }, '🔒 ' + gateKey) : h('span', { class: 'mt-gate mt-nogate' }, '无评审门')),
      h('div', { class: 'mt-stage-title' }, tx(s.title)),
      MF.statusBadge(s.status, tx(s.status_label, ''), !!s.stale),
      MF.progressBar(pct),
      h('div', { class: 'small' }, pct + '%'),
      h('div', { class: 'small ' + (over ? 'mt-over-txt' : 'muted') }, (over ? '逾期 · ' : '') + range),
      s.gate ? h('div', { class: 'small muted' }, '签署：' + (roles || '—')) : h('div', { class: 'small muted' }, '自检后完成'));
  }

  function gantt(stages, today) {
    var tms = ymd(today);
    var dates = [];
    stages.forEach(function (s) { [s.planned_start, s.planned_end, s.actual_start, s.actual_end].forEach(function (d) { var v = ymd(d); if (v !== null) dates.push(v); }); });
    if (!dates.length) return h('div', { class: 'empty' }, '尚无计划日期');
    var min = Math.min.apply(null, dates), max = Math.max.apply(null, dates);
    var showToday = tms >= min - 60 * DAY && tms <= max + 60 * DAY;
    if (showToday) { min = Math.min(min, tms); max = Math.max(max, tms); }
    min -= 2 * DAY; max += 3 * DAY;
    var span = max - min;
    function pc(v) { return ((v - min) / span * 100).toFixed(3); }
    // 月份刻度
    var ticks = [];
    var d = new Date(min); d = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1));
    while (d.getTime() <= max) {
      if (d.getTime() >= min) ticks.push({ v: d.getTime(), l: d.getUTCFullYear() + '-' + p2(d.getUTCMonth() + 1) });
      d = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1));
    }
    if (!ticks.length || (ticks[0].v - min) / span > 0.08) { var d0 = new Date(min); ticks.unshift({ v: min, l: d0.getUTCFullYear() + '-' + p2(d0.getUTCMonth() + 1) }); }
    ticks = ticks.filter(function (t) { return (t.v - min) / span < 0.93; });
    var axis = h('div', { class: 'mt-axis' }, ticks.map(function (t) { return h('div', { class: 'mt-tick', style: 'left:' + pc(t.v) + '%' }, t.l); }));
    var wrap = h('div', { class: 'mt-gantt' }, h('div', { class: 'mt-grow', style: 'border-top:0' }, h('div', null), axis));
    stages.forEach(function (s) {
      var ps = ymd(s.planned_start), pe = ymd(s.planned_end);
      var as = ymd(s.actual_start), ae = ymd(s.actual_end);
      var lockedS = STAGE_LOCKED.indexOf(s.status) >= 0;
      var over = !lockedS && pe !== null && pe < tms;
      var track = h('div', { class: 'mt-track' });
      ticks.forEach(function (t) { track.appendChild(h('div', { class: 'mt-grid', style: 'left:' + pc(t.v) + '%' })); });
      if (ps !== null && pe !== null && pe >= ps) {
        var w = Math.max((pe + DAY - ps) / span * 100, 0.6);
        track.appendChild(h('div', { class: 'mt-plan' + (over ? ' mt-over' : ''), style: 'left:' + pc(ps) + '%;width:' + w.toFixed(3) + '%', title: '计划：' + fdate(s.planned_start) + ' ~ ' + fdate(s.planned_end) }));
      }
      if (as !== null) {
        var open = ae === null && !lockedS;
        var end = ae !== null ? ae : (open ? Math.max(tms, as) : as);
        if (end < as) end = as;
        var w2 = Math.max((end + DAY - as) / span * 100, 0.6);
        track.appendChild(h('div', { class: 'mt-act mt-act-' + s.status + (open ? ' mt-open' : ''), style: 'left:' + pc(as) + '%;width:' + w2.toFixed(3) + '%',
          title: '实际：' + fdate(s.actual_start) + ' ~ ' + (ae !== null ? fdate(s.actual_end) : '进行中') + '（' + tx(s.status_label, '') + '）' }));
      }
      if (showToday) track.appendChild(h('div', { class: 'mt-today', style: 'left:' + pc(tms) + '%' }));
      var lbl = h('div', { class: 'mt-glabel' }, String(tx(s.ord, '·')) + '. ' + tx(s.title),
        over ? h('div', { class: 'mt-over-txt small' }, '逾期 ' + Math.max(1, Math.floor((tms - pe) / DAY)) + ' 天') : null);
      wrap.appendChild(h('div', { class: 'mt-grow' }, lbl, track));
    });
    var legend = h('div', { class: 'mt-legend' },
      h('span', null, h('i', { style: 'background:var(--c-muted,#9ca3af);opacity:.45' }), '计划'),
      h('span', null, h('i', { style: 'background:var(--c-err,#dc2626);opacity:.75' }), '计划（逾期）'),
      h('span', null, h('i', { style: 'background:var(--c-ok,#16a34a)' }), '实际（已通过）'),
      h('span', null, h('i', { style: 'background:var(--c-warn,#d97706)' }), '实际（进行中）'),
      h('span', null, h('i', { style: 'background:var(--c-primary,#2563eb)' }), '实际（待复核）'),
      showToday ? h('span', null, h('i', { style: 'background:var(--c-err,#dc2626);width:3px;height:12px;border-radius:0' }), '今天 ' + today) : h('span', null, '今天 ' + today + '（不在图表范围内）'));
    return h('div', null, h('div', { class: 'mt-gwrap' }, wrap), legend);
  }

  function infoCard(p) {
    var pr = p.project || {};
    var kvs = [['方法编号', p.code], ['所属项目', tx(pr.code) + ' ' + tx(pr.name, '')], ['技术模板', p.technique_label || (p.meta && p.meta.template_label) || p.technique], ['模板版本', p.template_version],
      ['方法版本', p.method_version], ['生命周期', lifeLabel(p)], ['开发状态', p.status_label],
      ['被测属性', p.analyte], ['样品基质', p.matrix], ['预期用途', p.intended_use], ['研发阶段', p.phase],
      ['计划周期', fdate(p.planned_start) + ' ~ ' + fdate(p.planned_end)], ['方法负责人', p.owner_name],
      ['创建时间', fdt(p.created_at)], ['最近更新', fdt(p.updated_at)]];
    var cells = [];
    kvs.forEach(function (r) {
      var v = r[0] === '所属项目' ? h('a', { href: '#/pr/' + p.project_id }, tx(r[1])) : tx(r[1]);
      cells.push(h('div', { class: 'k' }, r[0]), h('div', { class: 'v' }, v));
    });
    return h('div', { class: 'card' }, h('h3', null, '方法信息'), h('div', { class: 'kv' }, cells));
  }

  function membersCard(p) {
    var byUser = {}, order = [];
    (p.members || []).forEach(function (m) {
      if (!byUser[m.user_id]) { byUser[m.user_id] = { name: tx(m.display_name, '用户#' + m.user_id), username: m.username, roles: [] }; order.push(m.user_id); }
      byUser[m.user_id].roles.push(m.role);
    });
    var hasRev = (p.members || []).some(function (m) { return m.role === 'reviewer'; });
    var hasApp = (p.members || []).some(function (m) { return m.role === 'approver'; });
    var canManage = !!(p.permissions && p.permissions.can_manage_members) && p.status === 'active' && (!p.project || p.project.status === 'active');
    var tbl = order.length ? h('div', { class: 'mt-tw' }, h('table', { class: 'table' },
      h('thead', null, h('tr', null, h('th', null, '成员'), h('th', null, '账号'), h('th', null, '方法角色'))),
      h('tbody', null, order.map(function (id) {
        var u = byUser[id];
        return h('tr', null, h('td', null, u.name), h('td', { class: 'muted' }, tx(u.username)),
          h('td', null, u.roles.map(function (r) { return badge(roleLabel(r), r === 'owner' ? 'info' : (r === 'viewer' ? 'muted' : 'ok')); })));
      })))) : h('div', { class: 'empty' }, '暂无成员');
    return h('div', { class: 'card' },
      h('div', { class: 'toolbar' }, h('h3', { style: 'margin:0' }, '方法团队'), h('span', { class: 'spacer' }),
        canManage ? h('button', { class: 'btn btn-sm', onclick: function () { editMembers(p); } }, '调整成员') : null),
      tbl,
      (!hasRev || !hasApp) ? h('div', { class: 'callout callout-warn small', style: 'margin-top:8px' },
        '方法团队中' + [!hasRev ? '尚无“复核人”' : '', !hasApp ? '尚无“批准人(QA)”' : ''].filter(Boolean).join('、') + '，对应评审门将无法提交，请方法负责人或项目负责人尽快补充。') : null,
      h('p', { class: 'small muted', style: 'margin-bottom:0' }, '方法团队成员只能从所属项目的团队中选择；职责分离：在某阶段编辑/保存/提交过内容的人，不能复核/批准该阶段；同一版本同一人不得重复签署。'));
  }

  // 方法角色所需的全局角色（与后端 GLOBAL_NEED 一致）
  var GLOBAL_NEED = { owner: ['author', 'admin'], author: ['author', 'admin'], reviewer: ['reviewer'], approver: ['approver'], viewer: null };
  function userFitsRole(u, role) {
    var need = GLOBAL_NEED[role];
    if (!need) return true;
    return (u.roles || []).some(function (r) { return need.indexOf(r) >= 0; });
  }

  function editMembers(p) {
    Promise.all([
      api('GET', '/api/projects/' + p.project_id).catch(function () { return null; }),
      api('GET', '/api/users').catch(function () { return []; })
    ]).then(function (rs) {
      var proj = rs[0], users = rs[1] || [];
      var gl = {};                                     // 全局角色/账号
      users.forEach(function (u) { gl[u.id] = u; });
      var cand = {}, candOrder = [];                   // 候选人 = 项目成员 ∪ 管理员 ∪ 现有方法成员
      function addCand(id, name, username, active) {
        if (cand[id]) return;
        var g = gl[id] || {};
        cand[id] = { id: id, name: tx(name, '用户#' + id) + (username ? '（' + username + '）' : ''), roles: g.roles || [], active: active !== false && g.active !== false };
        candOrder.push(id);
      }
      if (proj) (proj.members || []).forEach(function (m) { if (m.active !== false) addCand(m.user_id, m.display_name, m.username, m.active); });
      users.forEach(function (u) { if ((u.roles || []).indexOf('admin') >= 0 && u.active !== false) addCand(u.id, u.display_name, u.username, u.active); });
      (p.members || []).forEach(function (m) { addCand(m.user_id, m.display_name, m.username, m.active); });
      var initial = (p.members || []).map(function (m) { return { user_id: String(m.user_id), role: m.role }; });
      var roleKeys = ['owner', 'author', 'reviewer', 'approver', 'viewer'];
      var roleOpts = roleKeys.map(function (r) { return { value: r, label: roleLabel(r) }; });
      function optsFor(role) {
        var o = [{ value: '', label: '— 请选择 —' }];
        candOrder.forEach(function (id) { var c = cand[id]; if (c.active && userFitsRole(c, role)) o.push({ value: String(id), label: c.name }); });
        return o;
      }
      return dialog({
        title: '调整方法团队', okLabel: '保存', width: 720, initial: initial,
        make: function (rows) {
          rows = rows.map(function (r) { return { user_id: r.user_id, role: r.role }; });
          var box = h('div', { class: 'mt-tw' });
          function paint() {
            MF.clear(box);
            var tb = h('tbody', null);
            rows.forEach(function (r, i) {
              var rs = mkSelect(roleOpts, r.role);
              var os = optsFor(r.role);
              if (r.user_id && !os.some(function (o) { return o.value === r.user_id; })) {
                var c = cand[r.user_id];
                os.push({ value: r.user_id, label: (c ? c.name : '用户#' + r.user_id) + '（全局角色不符，需更换）' });
              }
              var us = mkSelect(os, r.user_id);
              us.onchange = function () { r.user_id = us.value; };
              rs.onchange = function () { r.role = rs.value; if (r.user_id && !(cand[r.user_id] && userFitsRole(cand[r.user_id], r.role))) r.user_id = ''; paint(); };
              tb.appendChild(h('tr', null, h('td', null, rs), h('td', null, us),
                h('td', null, h('button', { class: 'btn btn-sm btn-danger', type: 'button', onclick: function () { rows.splice(i, 1); paint(); } }, '移除'))));
            });
            box.appendChild(h('table', { class: 'table' }, h('thead', null, h('tr', null, h('th', null, '方法角色'), h('th', null, '用户（项目成员）'), h('th', null, ''))), tb));
            box.appendChild(h('button', { class: 'btn btn-sm', type: 'button', onclick: function () { rows.push({ user_id: '', role: 'author' }); paint(); } }, '＋ 添加成员/角色'));
          }
          paint();
          var node = h('div', null,
            h('div', { class: 'callout small' },
              h('div', null, '候选人只来自所属项目 ', h('b', null, tx(p.project && p.project.code)), ' 的团队（及管理员），并按全局角色过滤：负责人/开发人员需具备“开发人员”或管理员，复核人/批准人需具备对应全局角色。如缺人，请项目负责人先把他加入项目团队。'),
              h('ul', { style: 'margin:4px 0 4px 18px;padding:0' },
                h('li', null, '方法负责人：改方法信息、重新打开已通过阶段、变更生命周期、完成/归档；至少保留一名。'),
                h('li', null, '开发人员：编辑阶段与实验、提交复核。'),
                h('li', null, '复核人 / 批准人(QA)：在评审门电子签名；批准人也可重新打开已通过阶段与变更生命周期。'),
                h('li', null, '只读：仅查看。')),
              h('div', null, '职责分离：同一人不能同时担任（负责人/开发人员）与（复核人/批准人）；复核人与批准人不能是同一人；有阶段待复核时不能增删复核人/批准人。')),
            box);
          return { node: node, read: function () { return rows; } };
        },
        ok: function (rows) {
          var seen = {}, out = [], byUser = {};
          function nm(id) { return cand[id] ? cand[id].name : '用户#' + id; }
          for (var i = 0; i < rows.length; i++) {
            var r = rows[i];
            if (!r.user_id) throw new Error('第 ' + (i + 1) + ' 行（' + roleLabel(r.role) + '）未选择用户');
            var k = r.user_id + '|' + r.role;
            if (seen[k]) throw new Error('存在重复的成员角色：' + nm(r.user_id) + ' / ' + roleLabel(r.role));
            if (cand[r.user_id] && !userFitsRole(cand[r.user_id], r.role)) throw new Error(nm(r.user_id) + ' 的全局角色不允许担任“' + roleLabel(r.role) + '”');
            seen[k] = 1; out.push({ user_id: toInt(r.user_id), role: r.role });
            (byUser[r.user_id] = byUser[r.user_id] || {})[r.role] = 1;
          }
          if (!out.some(function (r) { return r.role === 'owner'; })) throw new Error('至少保留一名方法负责人');
          Object.keys(byUser).forEach(function (id) {
            var rr = byUser[id];
            if ((rr.owner || rr.author) && (rr.reviewer || rr.approver)) throw new Error(nm(id) + ' 不能同时担任编辑类角色（负责人/开发人员）和签署类角色（复核人/批准人）——职责分离');
            if (rr.reviewer && rr.approver) throw new Error(nm(id) + ' 不能同时是复核人和批准人');
          });
          return api('PUT', '/api/methods/' + p.id + '/members', { members: out });
        }
      });
    }).then(function (r) { if (r) { MF.toast('团队已更新', 'ok'); MF.reload(); } }, fail);
  }


  // =====================================================================  阶段外壳
  function renderStagePage(body, p, key) {
    var s = (p.stages || []).filter(function (x) { return x.key === key; })[0];
    if (!s) {
      body.appendChild(h('div', { class: 'card' }, h('h3', null, '阶段不存在'), h('p', { class: 'muted' }, '方法中没有阶段“' + tx(key) + '”。'),
        h('a', { class: 'btn', href: '#/m/' + p.id }, '返回总览')));
      return;
    }
    body.appendChild(h('div', { class: 'mt-chips' }, (p.stages || []).map(function (x) {
      var blk = (x.blocked_by || []).length > 0;
      return h('a', { class: 'mt-chip' + (x.key === key ? ' mt-on' : '') + (blk ? ' mt-blocked' : ''), href: '#/m/' + p.id + '/stage/' + x.key,
        title: blk ? '尚未开放：需先完成 ' + x.blocked_by.map(function (b) { return '第 ' + b.step + ' 步“' + b.title + '”'; }).join('、') : tx(x.status_label, '') + (x.stale ? '（已失效）' : '') },
        h('span', { class: 'mt-dot mt-dot-' + x.status }), String(tx(x.ord, '·')) + ' ' + tx(x.title), x.gate ? h('span', { class: 'mt-gate' }, '🔒') : null, blk ? h('span', { class: 'mt-gate' }, '⛔') : null);
    })));
    var holder = h('div', { class: 'mt-stage-holder' });
    body.appendChild(holder);
    if (typeof MF.renderStage !== 'function') {
      holder.appendChild(h('div', { class: 'card' }, h('h3', null, tx(s.title)), h('div', { class: 'callout callout-warn' }, '阶段编辑模块尚未加载（stage.js）。请刷新页面或联系管理员。'),
        h('div', { class: 'kv' }, h('div', { class: 'k' }, '状态'), h('div', { class: 'v' }, tx(s.status_label)), h('div', { class: 'k' }, '进度'), h('div', { class: 'v' }, tx(s.progress) + '%'))));
      return;
    }
    try {
      var r = MF.renderStage(holder, p.id, key, p);
      if (r && typeof r.then === 'function') return r.catch(function (e) { holder.appendChild(h('div', { class: 'callout callout-err' }, '阶段页面渲染失败：' + errMsg(e))); });
    } catch (e) {
      holder.appendChild(h('div', { class: 'callout callout-err' }, '阶段页面渲染失败：' + errMsg(e)));
    }
  }

  // =====================================================================  实验列表
  var EXP_LABEL = { planned: '计划中', running: '进行中', done: '已完成', cancelled: '已取消' };
  var EXP_KIND = { planned: 'muted', running: 'warn', done: 'ok', cancelled: 'err' };
  var expUI = { pid: null, stage: '', status: '', group: false, q: '' };

  function expActions(e) {
    return ({
      planned: [{ l: '开始', to: 'running', k: 'primary' }, { l: '取消', to: 'cancelled', k: 'danger' }],
      running: [{ l: '完成', to: 'done', k: 'primary' }, { l: '取消', to: 'cancelled', k: 'danger' }],
      done: [{ l: '重新打开', to: 'running', k: '' }],
      cancelled: [{ l: '恢复计划', to: 'planned', k: '' }]
    })[e.status] || [];
  }

  // 变更实验状态（列表与详情共用）。opts.noConclusionDialog：详情页不弹结论框
  function changeExpStatus(e, to, opts) {
    opts = opts || {};
    var chain = Promise.resolve({ reason: '' });
    if (to === 'cancelled') {
      chain = askReason('取消实验 ' + tx(e.code, ''), '取消原因', { kind: 'danger', okLabel: '确认取消', placeholder: '说明为何取消，将计入偏离/说明与审计' }).then(function (r) { return r === null ? null : { reason: r }; });
    } else if (e.status === 'done' && to === 'running') {
      chain = askReason('重新打开实验 ' + tx(e.code, ''), '重新打开的原因', { okLabel: '重新打开' }).then(function (r) { return r === null ? null : { reason: r }; });
    } else if (to === 'done' && !String(e.conclusion || '').trim() && !opts.noConclusionDialog) {
      chain = dialog({
        title: '完成实验 ' + tx(e.code, '') + ' - 填写结论', okLabel: '保存结论并完成', initial: '',
        make: function (d) {
          var ta = mkArea(d, 4, '实验结论（对照接受标准）');
          return { node: h('div', null, h('p', { class: 'muted' }, '完成实验须先填写结论。' + (e.acceptance ? '接受标准：' + e.acceptance : '')), field('结论', ta)), read: function () { return ta.value; } };
        },
        ok: function (c) {
          if (!c.trim()) throw new Error('请填写结论');
          return api('PUT', '/api/experiments/' + e.id, { version: e.version, conclusion: c.trim() });
        }
      }).then(function (r) { return r ? { reason: '' } : null; });
    }
    return chain.then(function (c) {
      if (!c) return false;
      return api('POST', '/api/experiments/' + e.id + '/status', { status: to, reason: c.reason }).then(function () {
        MF.toast('实验状态已更新为“' + EXP_LABEL[to] + '”', 'ok');
        return true;
      });
    }).catch(function (err) {
      fail(err);
      if (opts.onError) opts.onError(err);
      return false;
    });
  }

  function renderExperiments(body, p, alive) {
    if (expUI.pid !== p.id) expUI = { pid: p.id, stage: '', status: '', group: false, q: '' };
    body.appendChild(h('div', { class: 'muted' }, '加载中…'));
    return Promise.all([api('GET', '/api/methods/' + p.id + '/experiments'), api('GET', '/api/users').catch(function () { return []; })]).then(function (rs) {
      if (!alive()) return;
      var exps = rs[0] || [], users = rs[1] || [];
      var names = {};
      users.forEach(function (u) { names[u.id] = tx(u.display_name, u.username); });
      uniqueMembers(p).forEach(function (m) { names[m.id] = m.name; });
      var can = canEdit(p);
      var today = todayStr();
      MF.clear(body);

      var listBox = h('div', null);
      var selStage = mkSelect([{ value: '', label: '全部阶段' }].concat((p.stages || []).map(function (s) { return { value: s.key, label: s.ord + '. ' + s.title }; })).concat([{ value: '__none', label: '未关联阶段' }]), expUI.stage);
      var selStatus = mkSelect([{ value: '', label: '全部状态' }].concat(Object.keys(EXP_LABEL).map(function (k) { return { value: k, label: EXP_LABEL[k] }; })), expUI.status);
      var q = mkInput('text', expUI.q, '搜索编号/名称'); q.style.maxWidth = '200px';
      var grp = h('input', { type: 'checkbox' }); grp.checked = !!expUI.group;
      function paint() {
        expUI.stage = selStage.value; expUI.status = selStatus.value; expUI.group = grp.checked; expUI.q = q.value;
        var qq = q.value.trim().toLowerCase();
        var rows = exps.filter(function (e) {
          if (selStage.value === '__none' ? !!e.stage_key : (selStage.value && e.stage_key !== selStage.value)) return false;
          if (selStatus.value && e.status !== selStatus.value) return false;
          if (qq && (s0(e.code) + ' ' + s0(e.title)).toLowerCase().indexOf(qq) < 0) return false;
          return true;
        });
        MF.clear(listBox);
        if (!rows.length) { listBox.appendChild(h('div', { class: 'empty' }, exps.length ? '没有符合筛选条件的实验' : '尚未登记实验。点击“新增实验”开始。')); return; }
        var tb = h('tbody', null);
        function row(e) {
          var over = (e.status === 'planned' || e.status === 'running') && e.planned_end && String(e.planned_end).slice(0, 10) < today;
          var acts = h('td', { class: 'mt-nowrap' });
          if (can && !e.locked) {
            expActions(e).forEach(function (a) {
              acts.appendChild(h('button', { class: 'btn btn-sm ' + (a.k ? 'btn-' + a.k : ''), style: 'margin-right:4px', onclick: function (ev) {
                ev.currentTarget.disabled = true;
                changeExpStatus(e, a.to).then(function (ok) { if (ok) MF.reload(); else paint(); });
              } }, a.l));
            });
          } else if (e.locked) acts.appendChild(h('span', { class: 'small muted' }, '阶段已锁定'));
          var cb = (can && !e.locked && (e.status === 'planned' || e.status === 'running'))
            ? h('input', { type: 'checkbox', 'aria-label': '选择', onchange: function (ev) { if (ev.target.checked) sel[e.id] = true; else delete sel[e.id]; syncBulk(); } }) : null;
          if (cb && sel[e.id]) cb.checked = true;
          return h('tr', null,
            h('td', null, cb),
            h('td', { class: 'mt-nowrap' }, tx(e.code)),
            h('td', null, h('a', { href: '#/m/' + p.id + '/exp/' + e.id }, tx(e.title, '（未命名）')),
              e.added_after_plan ? h('span', { class: 'mt-tag', title: '方案提交/批准后新增的实验，在文档中单列' }, '方案后新增') : null),
            h('td', null, stageTitle(p, e.stage_key)),
            h('td', null, e.owner_id ? tx(names[e.owner_id], '用户#' + e.owner_id) : '—'),
            h('td', { class: 'mt-nowrap ' + (over ? 'mt-over-txt' : '') }, fdate(e.planned_start) + ' ~ ' + fdate(e.planned_end) + (over ? ' 逾期' : '')),
            h('td', null, badge(EXP_LABEL[e.status] || tx(e.status), EXP_KIND[e.status] || 'muted')),
            h('td', null, '📎 ' + toInt(e.attachments)),
            h('td', null, e.locked ? h('span', { title: '所属阶段已锁定/待复核，实验记录只读' }, '🔒') : ''),
            acts);
        }
        if (grp.checked) {
          var order = (p.stages || []).map(function (s) { return s.key; }).concat(['']);
          order.forEach(function (k) {
            var part = rows.filter(function (e) { return (e.stage_key || '') === k; });
            if (!part.length) return;
            tb.appendChild(h('tr', null, h('td', { colspan: '10', style: 'background:var(--c-bg,#f3f4f6);font-weight:600' }, stageTitle(p, k) + '（' + part.length + '）')));
            part.forEach(function (e) { tb.appendChild(row(e)); });
          });
        } else rows.forEach(function (e) { tb.appendChild(row(e)); });
        listBox.appendChild(h('div', { class: 'mt-tw' }, h('table', { class: 'table' },
          h('thead', null, h('tr', null, [h('th', null, can ? h('input', { type: 'checkbox', 'aria-label': '全选', onchange: function (ev) {
            tb.querySelectorAll('input[type=checkbox]').forEach(function (x) { x.checked = ev.target.checked; x.dispatchEvent(new Event('change')); });
          } }) : null)].concat(['编号', '名称', '阶段', '负责人', '计划起止', '状态', '附件', '', '操作'].map(function (c) { return h('th', null, c); })))), tb)));
        syncBulk();
      }
      var sel = {};
      var bulkInfo = h('span', { class: 'small muted' });
      function bulkRun(action) {
        var ids = Object.keys(sel).map(Number);
        if (!ids.length) return;
        var run = async function (reason) {
          try {
            var r = await api('POST', '/api/methods/' + p.id + '/experiments/bulk', { ids: ids, action: action, reason: reason || '' });
            if ((r.failed || []).length) {
              var codes = {}; exps.forEach(function (e) { codes[e.id] = e.code; });
              await MF.modal({ title: '部分实验未能处理', width: 560, body: h('div', null, h('p', null, '成功 ' + r.done.length + ' 个，失败 ' + r.failed.length + ' 个：'),
                h('ul', null, r.failed.map(function (f) { return h('li', null, tx(codes[f.id], '#' + f.id) + '：' + tx(f.error)); }))), buttons: [{ label: '知道了', kind: 'primary', value: true }] });
            } else MF.toast('已处理 ' + r.done.length + ' 个实验', 'ok');
            MF.reload();
          } catch (e) { MF.toast(e.message || '操作失败', 'err'); }
        };
        if (action === 'cancel') {
          var ta = h('textarea', { class: 'textarea', rows: 3, placeholder: '取消原因（必填，将计入每个实验的偏离/说明与审计）' });
          MF.modal({ title: '批量取消 ' + ids.length + ' 个实验', body: ta, buttons: [{ label: '返回', value: null }, { label: '确认取消', kind: 'danger', onClick: async function (ctl) {
            if (!ta.value.trim()) { ctl.error('请填写取消原因'); ctl.setBusy(false); return false; }
            ctl.close(ta.value.trim());
          } }] }).then(function (reason) { if (reason) run(reason); });
        } else if (action === 'confirm_examples') {
          MF.confirm('确认选中的 ' + ids.length + ' 个实验的设计与接受标准已逐项核对、符合本产品？系统将删除其中的“示例值”标记，并写入审计记录。方案提交/批准后这些内容会被冻结。').then(function (ok) { if (ok) run(''); });
        } else {
          MF.confirm('把选中的 ' + ids.length + ' 个实验设为“进行中”？（需“开发方案”阶段已批准）').then(function (ok) { if (ok) run(''); });
        }
      }
      var bulkStart = h('button', { class: 'btn btn-sm btn-primary', type: 'button', hidden: true, onclick: function () { bulkRun('start'); } }, '批量开始');
      var bulkCancel = h('button', { class: 'btn btn-sm btn-danger', type: 'button', hidden: true, onclick: function () { bulkRun('cancel'); } }, '批量取消');
      var bulkConfirm = h('button', { class: 'btn btn-sm', type: 'button', hidden: true, title: '我已逐项核对所选实验的设计与接受标准，删除其中的“示例值”标记', onclick: function () { bulkRun('confirm_examples'); } }, '确认示例值');
      function syncBulk() {
        var n = Object.keys(sel).length;
        bulkStart.hidden = bulkCancel.hidden = bulkConfirm.hidden = !n;
        bulkInfo.textContent = n ? '已选 ' + n + ' 个' : '';
      }
      selStage.onchange = selStatus.onchange = grp.onchange = paint; q.oninput = paint;

      var done = exps.filter(function (e) { return e.status === 'done'; }).length;
      body.appendChild(h('div', { class: 'card' },
        h('div', { class: 'toolbar mt-tb' }, h('h3', { style: 'margin:0' }, '实验（' + exps.length + '）'), h('span', { class: 'small muted' }, '已完成 ' + done),
          h('span', { class: 'spacer' }), selStage, selStatus, q, h('label', { class: 'small' }, grp, ' 按阶段分组'),
          bulkInfo, bulkConfirm, bulkStart, bulkCancel,
          can ? h('button', { class: 'btn btn-primary btn-sm', onclick: function () { newExperiment(p, names); } }, '新增实验') : null),
        !can ? h('div', { class: 'hint small muted' }, hasEditRole(p) ? '本方法或所属项目当前不是“进行中”，实验不可修改。' : '您在本方法中没有编辑权限（仅方法负责人/开发人员可新增、修改实验）。') : null,
        planFrozen(p) ? h('div', { class: 'callout callout-warn small' }, '“开发方案”阶段已提交/批准：方案内实验的名称、目的、设计、接受标准、所属阶段已冻结（结果、结论、偏离、日期、负责人仍可维护，也不可删除）；此后新增的实验会带“方案后新增”标记，并在文档中单列。如需修改方案内实验，请先撤回或重新打开“开发方案”阶段。') : null,
        h('p', { class: 'small muted' }, '状态流转：计划中 → 进行中 → 已完成；完成须先填写结论；取消须写明原因；开始实验需“开发方案”阶段已批准。所属阶段进入待复核/已通过后，实验记录自动锁定。'),
        listBox));
      paint();
    });
  }

  function stageOptions(p, includeNone, currentKey) {
    var out = includeNone ? [{ value: '', label: '（不关联阶段）' }] : [];
    (p.stages || []).forEach(function (s) {
      var lock = (s.status === 'approved' || s.status === 'completed' || s.status === 'in_review') && s.key !== currentKey;
      out.push({ value: s.key, label: s.ord + '. ' + s.title + (lock ? '（已锁定）' : ''), disabled: lock });
    });
    return out;
  }

  function newExperiment(p, names) {
    var members = uniqueMembers(p);
    var me = MF.state && MF.state.user ? MF.state.user.id : '';
    if (!members.some(function (m) { return String(m.id) === String(me); })) me = members.length ? members[0].id : '';
    var firstOpen = (p.stages || []).filter(function (s) { return ['approved', 'completed', 'in_review'].indexOf(s.status) < 0; })[0];
    var late = planFrozen(p);          // 方案已提交/批准：新增实验必须有设计和接受标准
    dialog({
      title: '新增实验', okLabel: '创建', width: 680,
      initial: { title: '', code: '', stage_key: firstOpen ? firstOpen.key : '', owner_id: String(me), objective: '', design: '', acceptance: '', planned_start: '', planned_end: '' },
      make: function (d) {
        var c = {
          title: mkInput('text', d.title, '必填'), code: mkInput('text', d.code, '留空自动编号，如 EXP-05'),
          stage_key: mkSelect(stageOptions(p, true), d.stage_key),
          owner_id: mkSelect(members.map(function (m) { return { value: String(m.id), label: m.name }; }), d.owner_id),
          objective: mkArea(d.objective, 2), design: mkArea(d.design, 3), acceptance: mkArea(d.acceptance, 2),
          planned_start: mkInput('date', d.planned_start), planned_end: mkInput('date', d.planned_end)
        };
        var node = h('div', null,
          planFrozen(p) ? h('div', { class: 'callout callout-warn small' }, '“开发方案”阶段已提交/批准：本实验将标记为“方案后新增”，并在文档中单列；方案内实验的设计不再可改。') : null,
          h('div', { class: 'mt-form2' }, field('实验名称 *', c.title), field('实验编号', c.code), field('所属阶段', c.stage_key), field('负责人（方法团队成员）', c.owner_id),
            field('计划开始', c.planned_start), field('计划结束', c.planned_end)),
          field('目的', c.objective), field(late ? '设计（样品、条件、重复数、对照） *' : '设计（样品、条件、重复数、对照）', c.design, late ? '方案已提交/批准，必须填写，否则方案阶段无法重新复核' : null),
            field(late ? '接受标准 *' : '接受标准', c.acceptance, late ? '方案已提交/批准，必须填写' : null));
        return { node: node, read: function () { var o = {}; Object.keys(c).forEach(function (k) { o[k] = c[k].value; }); return o; } };
      },
      ok: function (d) {
        if (!d.title.trim()) throw new Error('请填写实验名称');
        if (late && !d.design.trim()) throw new Error('开发方案已提交/批准，新增实验必须填写“设计”');
        if (late && !d.acceptance.trim()) throw new Error('开发方案已提交/批准，新增实验必须填写“接受标准”');
        if (d.planned_start && d.planned_end && d.planned_end < d.planned_start) throw new Error('计划结束不能早于计划开始');
        var body = { title: d.title.trim(), objective: d.objective, design: d.design, acceptance: d.acceptance,
          stage_key: d.stage_key || null, planned_start: d.planned_start || null, planned_end: d.planned_end || null };
        if (d.code.trim()) body.code = d.code.trim();
        if (d.owner_id) body.owner_id = toInt(d.owner_id);
        return api('POST', '/api/methods/' + p.id + '/experiments', body);
      }
    }).then(function (r) { if (r && r.result) { MF.toast('实验已创建', 'ok'); MF.reload(); } });
  }

  // =====================================================================  实验详情
  var VERDICTS = ['待评估', '符合', '不符合'];
  var detailKeyHandler = null;

  function normRows(rs) {
    return (Array.isArray(rs) ? rs : []).map(function (r) {
      r = r && typeof r === 'object' ? r : {};
      return { metric: s0(r.metric), value: s0(r.value), criterion: s0(r.criterion), verdict: VERDICTS.indexOf(r.verdict) >= 0 ? r.verdict : (r.verdict ? s0(r.verdict) : '待评估') };
    });
  }
  function cleanRows(rs) {
    return normRows(rs).filter(function (r) { return r.metric.trim() || r.value.trim() || r.criterion.trim(); });
  }

  function renderExpDetail(body, p, eid, alive) {
    body.appendChild(h('div', { class: 'muted' }, '加载中…'));
    return Promise.all([api('GET', '/api/experiments/' + eid), api('GET', '/api/users').catch(function () { return []; })]).then(function (rs) {
      if (!alive()) return;
      var e0 = rs[0];
      if (e0.method_id !== p.id) throw new Error('该实验不属于本方法');
      var users = rs[1] || [];
      var names = {};
      users.forEach(function (u) { names[u.id] = tx(u.display_name, u.username); });
      uniqueMembers(p).forEach(function (m) { names[m.id] = m.name; });
      crumbs([{ label: '项目', href: '/projects' }, { label: tx(p.project && p.project.code, '项目'), href: '/pr/' + p.project_id },
        { label: tx(p.code) + ' ' + tx(p.name, ''), href: '/m/' + p.id }, { label: '实验', href: '/m/' + p.id + '/experiments' }, { label: tx(e0.code) }]);
      var st = { e: e0, draft: mkDraft(e0), atts: e0.attachments_list || [] };
      var expStage = (p.stages || []).filter(function (s) { return s.key === e0.stage_key; })[0];

      function mkDraft(e) {
        return { title: s0(e.title), stage_key: s0(e.stage_key), objective: s0(e.objective), design: s0(e.design), acceptance: s0(e.acceptance),
          planned_start: s0(e.planned_start).slice(0, 10), planned_end: s0(e.planned_end).slice(0, 10), owner_id: e.owner_id ? String(e.owner_id) : '',
          deviations: s0(e.deviations), conclusion: s0(e.conclusion), results: normRows(e.results) };
      }
      function diff() {
        var d = st.draft, e = st.e, out = {};
        ['title', 'objective', 'design', 'acceptance', 'deviations', 'conclusion'].forEach(function (k) { if (s0(d[k]) !== s0(e[k])) out[k] = d[k]; });
        ['stage_key', 'planned_start', 'planned_end'].forEach(function (k) { if (s0(d[k]) !== s0(e[k]).slice(0, k === 'stage_key' ? 999 : 10)) out[k] = d[k] || null; });
        if (s0(d.owner_id) !== (e.owner_id ? String(e.owner_id) : '')) out.owner_id = d.owner_id ? toInt(d.owner_id) : null;
        if (JSON.stringify(cleanRows(d.results)) !== JSON.stringify(cleanRows(e.results))) out.results = cleanRows(d.results);
        return out;
      }
      function isDirty() { return Object.keys(diff()).length > 0; }

      var root = h('div', null);
      MF.clear(body);
      body.appendChild(root);

      function ro() { return !!st.e.locked || !canEdit(p); }
      // 方案提交/批准后，方案内（非 added_after_plan）实验的 名称/目的/设计/接受标准/所属阶段 冻结
      function dfrozen() { return !st.e.added_after_plan && planFrozen(p); }

      function refreshAtts() {
        return api('GET', '/api/experiments/' + eid).then(function (e) { st.atts = e.attachments_list || []; paintAtts(); }, fail);
      }

      var attBox = h('div', null);
      function paintAtts() {
        MF.clear(attBox);
        var canUp = canEdit(p) && !st.e.locked;
        var fileIn = h('input', { type: 'file' });
        var desc = mkInput('text', '', '说明（可选）'); desc.style.maxWidth = '260px';
        var upBtn = h('button', { class: 'btn btn-sm btn-primary', disabled: !canUp, onclick: function () {
          var f = fileIn.files && fileIn.files[0];
          if (!f) { MF.toast('请先选择文件', 'warn'); return; }
          upBtn.disabled = true; upBtn.textContent = '上传中…';
          var url = '/api/methods/' + p.id + '/attachments?filename=' + encodeURIComponent(f.name) + '&experiment_id=' + st.e.id +
            (st.e.stage_key ? '&stage_key=' + encodeURIComponent(st.e.stage_key) : '') + (desc.value.trim() ? '&description=' + encodeURIComponent(desc.value.trim()) : '');
          Promise.resolve(MF.upload(url, f)).then(function () { MF.toast('已上传：' + f.name, 'ok'); return refreshAtts(); }, function (err) { fail(err); upBtn.disabled = false; upBtn.textContent = '上传'; });
        } }, '上传');
        attBox.appendChild(h('div', { class: 'toolbar mt-tb' }, fileIn, desc, upBtn, canUp ? null : h('span', { class: 'small muted' }, st.e.locked ? '阶段已锁定，不能新增附件' : '无编辑权限')));
        if (!st.atts.length) { attBox.appendChild(h('div', { class: 'empty' }, '暂无附件（原始数据、色谱图、FCS 文件等可上传于此，系统自动记录 SHA-256）')); return; }
        attBox.appendChild(h('div', { class: 'mt-tw' }, h('table', { class: 'table' },
          h('thead', null, h('tr', null, ['文件名', '大小', 'SHA-256', '上传人', '时间', '说明', '操作'].map(function (c) { return h('th', null, c); }))),
          h('tbody', null, st.atts.map(function (a) {
            return h('tr', null, h('td', null, tx(a.filename)), h('td', { class: 'mt-nowrap' }, fsize(a.size)), h('td', { class: 'mt-hash', title: tx(a.sha256, '') }, tx(a.sha256, '').slice(0, 12)),
              h('td', null, tx(a.uploader)), h('td', { class: 'mt-nowrap' }, fdt(a.uploaded_at)), h('td', null, tx(a.description)),
              h('td', { class: 'mt-nowrap' },
                h('a', { class: 'btn btn-sm', href: '/api/attachments/' + a.id + '/download', style: 'margin-right:4px' }, '下载'),
                h('button', { class: 'btn btn-sm', style: 'margin-right:4px', onclick: function () {
                  api('POST', '/api/attachments/' + a.id + '/verify').then(function (r) {
                    if (r && r.intact) MF.toast('校验通过：文件完整，与登记的 SHA-256 一致', 'ok');
                    else MF.toast('校验失败：文件内容与登记值不一致或文件丢失！', 'err');
                  }, fail);
                } }, '校验'),
                canUp ? h('button', { class: 'btn btn-sm btn-danger', onclick: function () {
                  askReason('删除附件 ' + tx(a.filename, ''), '删除原因', { kind: 'danger', okLabel: '删除' }).then(function (r) {
                    if (r === null) return;
                    api('DELETE', '/api/attachments/' + a.id + '?reason=' + encodeURIComponent(r)).then(function () { MF.toast('附件已删除（记录保留在审计中）', 'ok'); return refreshAtts(); }, fail);
                  });
                } }, '删除') : null));
          })))));
      }

      function save() {
        var d = diff();
        if (!Object.keys(d).length) { MF.toast('没有需要保存的修改', 'warn'); return Promise.resolve(false); }
        if (!st.draft.title.trim()) { MF.toast('实验名称不能为空', 'err'); return Promise.resolve(false); }
        d.version = st.e.version;
        return api('PUT', '/api/experiments/' + eid, d).then(function (e) {
          st.e = e; st.draft = mkDraft(e); setDirty(false); MF.toast('已保存（版本 ' + tx(e.version) + '）', 'ok'); paint(); return true;
        }, function (err) {
          fail(err);
          if (err && err.status === 409) { var b = h('button', { class: 'btn btn-sm', onclick: function () { MF.reload(); } }, '刷新页面'); root.insertBefore(h('div', { class: 'callout callout-err' }, '保存冲突或被锁定：' + errMsg(err) + ' ', b), root.firstChild); }
          return false;
        });
      }

      function onKey(ev) {
        if (!root.isConnected || location.hash.indexOf('/exp/' + eid) < 0) { document.removeEventListener('keydown', onKey); return; }
        if ((ev.ctrlKey || ev.metaKey) && String(ev.key).toLowerCase() === 's') {
          ev.preventDefault();
          if (!ro()) save();
        }
      }
      if (detailKeyHandler) document.removeEventListener('keydown', detailKeyHandler);
      detailKeyHandler = onKey;
      document.addEventListener('keydown', onKey);

      var dirtyEl, saveBtn, resetBtn, statusBtns = [];
      function touch() {
        var dirty = isDirty();
        setDirty(dirty);
        if (dirtyEl) dirtyEl.textContent = dirty ? '● 有未保存的修改' : '';
        if (saveBtn) saveBtn.disabled = !dirty || ro();
        if (resetBtn) resetBtn.disabled = !dirty;
        statusBtns.forEach(function (b) { b.disabled = dirty; b.title = dirty ? '请先保存修改再变更状态' : ''; });
      }

      function paint() {
        MF.clear(root);
        statusBtns = [];
        var e = st.e, locked = !!e.locked, readonly = ro();
        var D = st.draft;
        function bind(ctrl, key, ev, force) { ctrl[ev || 'oninput'] = function () { D[key] = ctrl.value; touch(); }; if (readonly || force) { if (ctrl.tagName === 'SELECT') ctrl.disabled = true; else ctrl.readOnly = true; ctrl.classList.add('mt-ro'); } return ctrl; }

        // 标题行
        root.appendChild(h('div', { style: 'margin-bottom:8px' }, h('a', { href: '#/m/' + p.id + '/experiments' }, '← 返回实验列表')));
        root.appendChild(h('div', { class: 'mt-title' }, h('span', { class: 'mt-code' }, tx(e.code)), h('h3', { style: 'margin:0' }, tx(e.title, '（未命名）')),
          badge(EXP_LABEL[e.status] || tx(e.status), EXP_KIND[e.status] || 'muted'), locked ? badge('🔒 已锁定', 'warn') : null,
          e.added_after_plan ? h('span', { class: 'mt-tag', title: '方案提交/批准后新增的实验，在文档中单列' }, '方案后新增') : null,
          h('span', { class: 'small muted' }, '版本 ' + tx(e.version) + ' · 更新于 ' + fdt(e.updated_at))));
        if (locked) {
          root.appendChild(h('div', { class: 'callout callout-warn' }, '本实验所属阶段“' + stageTitle(p, e.stage_key) + '”当前为“' + (expStage ? tx(expStage.status_label) : '锁定') +
            '”，实验记录已锁定，不能修改、变更状态或增删附件。如需修改，请先在阶段页撤回提交或由负责人/批准人重新打开该阶段。'));
        } else if (!canEdit(p)) {
          root.appendChild(h('div', { class: 'callout' }, hasEditRole(p) ? '本方法或所属项目当前不是“进行中”，实验不可修改，当前为只读。' : '您在本方法中没有编辑权限（仅方法负责人/开发人员可修改实验），当前为只读。'));
        }
        if (!locked && dfrozen()) {
          root.appendChild(h('div', { class: 'callout callout-warn' }, '“开发方案”阶段已提交/批准：本实验属于方案内实验，名称、目的、设计、接受标准、所属阶段已冻结，不可修改也不可删除；结果、结论、偏离、日期、负责人仍可维护。如需修改，请先撤回或重新打开“开发方案”阶段。'));
        }

        // 状态操作
        var actBox = h('div', { class: 'toolbar' }, h('span', { class: 'muted small' }, '状态操作：'));
        if (!readonly) {
          expActions(e).forEach(function (a) {
            var b = h('button', { class: 'btn btn-sm ' + (a.k ? 'btn-' + a.k : ''), onclick: function () {
              b.disabled = true;
              changeExpStatus(e, a.to, { noConclusionDialog: true, onError: function () { if (a.to === 'done' && !String(e.conclusion || '').trim() && concEl) concEl.focus(); } })
                .then(function (ok) { if (ok) MF.reload(); else touch(); });
            } }, a.l === '取消' ? '取消实验' : (a.l === '开始' ? '开始实验' : (a.l === '完成' ? '完成实验' : a.l)));
            statusBtns.push(b); actBox.appendChild(b);
          });
        } else actBox.appendChild(h('span', { class: 'small muted' }, '只读'));
        actBox.appendChild(h('span', { class: 'spacer' }));
        actBox.appendChild(h('span', { class: 'small muted' }, '实际：' + fdate(e.actual_start) + ' ~ ' + fdate(e.actual_end)));
        root.appendChild(h('div', { class: 'card' }, actBox,
          h('div', { class: 'small muted' }, e.status === 'planned' ? '开始实验需“开发方案”阶段已批准；' : '', '完成实验须先填写并保存结论；取消、重新打开须填写原因。')));

        // 保存条
        dirtyEl = h('span', { class: 'mt-dirty' });
        saveBtn = h('button', { class: 'btn btn-primary btn-sm', onclick: function () { save(); } }, '保存（Ctrl+S）');
        resetBtn = h('button', { class: 'btn btn-sm', onclick: function () { st.draft = mkDraft(st.e); setDirty(false); paint(); } }, '放弃修改');
        if (!readonly) root.appendChild(h('div', { class: 'mt-savebar' }, saveBtn, resetBtn, dirtyEl));

        // 基本信息
        var df = dfrozen();
        var titleIn = bind(mkInput('text', D.title), 'title', null, df);
        var stageSel = bind(mkSelect(stageOptions(p, !e.stage_key, e.stage_key), D.stage_key), 'stage_key', 'onchange', df);
        var ownerOpts = uniqueMembers(p).map(function (m) { return { value: String(m.id), label: m.name }; });
        if (e.owner_id && !ownerOpts.some(function (o) { return o.value === String(e.owner_id); })) ownerOpts.push({ value: String(e.owner_id), label: tx(names[e.owner_id], '用户#' + e.owner_id) });
        ownerOpts.unshift({ value: '', label: '（未指定）' });
        var ownerSel = bind(mkSelect(ownerOpts, D.owner_id), 'owner_id', 'onchange');
        root.appendChild(h('div', { class: 'card' }, h('h3', null, '设计'),
          h('div', { class: 'mt-form2' }, field('实验名称', titleIn), field('所属阶段', stageSel), field('负责人', ownerSel),
            field('计划开始', bind(mkInput('date', D.planned_start), 'planned_start')), field('计划结束', bind(mkInput('date', D.planned_end), 'planned_end'))),
          field('目的', bind(mkArea(D.objective, 2), 'objective', null, df)),
          field('设计（样品、条件、重复数、对照）', bind(mkArea(D.design, 4), 'design', null, df)),
          field('接受标准', bind(mkArea(D.acceptance, 2), 'acceptance', null, df))));

        // 结果表
        var tbody = h('tbody', null);
        function paintRows0() {
          MF.clear(tbody);
          D.results.forEach(function (r, i) {
            function inp(key, ph) { var x = mkInput('text', r[key], ph); x.oninput = function () { r[key] = x.value; touch(); }; if (readonly) { x.readOnly = true; x.classList.add('mt-ro'); } return x; }
            var vs = mkSelect(VERDICTS.map(function (v) { return { value: v, label: v }; }), r.verdict);
            if (VERDICTS.indexOf(r.verdict) < 0) { vs.appendChild(h('option', { value: r.verdict }, r.verdict)); vs.value = r.verdict; }
            vs.className = 'select ' + (r.verdict === '符合' ? 'mt-v-ok' : (r.verdict === '不符合' ? 'mt-v-no' : ''));
            vs.onchange = function () { r.verdict = vs.value; vs.className = 'select ' + (r.verdict === '符合' ? 'mt-v-ok' : (r.verdict === '不符合' ? 'mt-v-no' : '')); touch(); };
            if (readonly) vs.disabled = true;
            tbody.appendChild(h('tr', { class: 'mt-res' }, h('td', null, inp('metric', '如 主峰纯度')), h('td', null, inp('value', '实测值')), h('td', null, inp('criterion', '如 ≥ 95%')), h('td', { style: 'width:120px' }, vs),
              h('td', { style: 'width:60px' }, readonly ? null : h('button', { class: 'btn btn-sm btn-danger', type: 'button', onclick: function () { D.results.splice(i, 1); paintRows(); touch(); } }, '删除'))));
          });
          if (!D.results.length) tbody.appendChild(h('tr', null, h('td', { colspan: '5', class: 'muted small' }, '尚无结果行。')));
        }
        function paintRows() {            // + the machine verdict (criterion evaluated against the value) under every verdict
          paintRows0();
          var trs = tbody.querySelectorAll('tr.mt-res');
          D.results.forEach(function (r, i) {
            var td = trs[i] && trs[i].children[3];
            if (!td || !r.auto) return;
            var conflict = r.auto !== r.verdict && r.verdict && r.verdict !== '待评估';
            td.appendChild(h('div', { class: 'small', style: 'margin-top:2px;color:' + (r.auto === '符合' ? 'var(--c-ok,#16a34a)' : 'var(--c-err,#dc2626)') },
              '自动判定：' + r.auto + (conflict ? '　⚠ 人工判定不同' : '')));
          });
        }
        paintRows();
        root.appendChild(h('div', { class: 'card' }, h('div', { class: 'toolbar' }, h('h3', { style: 'margin:0' }, '结果'), h('span', { class: 'spacer' }),
          (MF.records ? MF.records.resultTools(D, function () { paintRows(); touch(); }, readonly) : null),
          readonly ? null : h('button', { class: 'btn btn-sm', type: 'button', onclick: function () { D.results.push({ metric: '', value: '', criterion: '', verdict: '待评估' }); paintRows(); touch(); } }, '＋ 添加结果行')),
          e.acceptance ? h('div', { class: 'small muted' }, '接受标准：', h('span', { 'data-notranslate': '1' }, e.acceptance)) : null,
          h('div', { class: 'mt-tw' }, h('table', { class: 'table' }, h('thead', null, h('tr', null, ['指标', '结果', '判据', '结论', ''].map(function (c) { return h('th', null, c); }))), tbody)),
          h('div', { class: 'small muted' }, '“符合/不符合”由实验人员对照判据判定；不符合项应在“偏离/说明”中记录调查。')));

        if (MF.records) root.appendChild(MF.records.runsPanel(p, e, locked));

        // 偏离与结论
        var concEl = bind(mkArea(D.conclusion, 4, '对照接受标准给出明确结论（完成实验前必填）'), 'conclusion');
        root.appendChild(h('div', { class: 'card' }, h('h3', null, '偏离与结论'),
          field('偏离 / 说明', bind(mkArea(D.deviations, 3, '偏离方案的操作、异常、取消原因等（取消实验时系统会自动追加原因）'), 'deviations')),
          field('结论', concEl)));

        // 附件
        root.appendChild(h('div', { class: 'card' }, h('h3', null, '附件'), attBox));
        paintAtts();

        // 删除实验
        var canDel = canEdit(p) && !locked && !df && (e.status === 'planned' || e.status === 'cancelled');
        if (canDel) {
          root.appendChild(h('div', { class: 'card' }, h('h3', null, '删除实验'),
            h('p', { class: 'muted small' }, '仅“计划中/已取消”且未锁定的实验可删除（已开始的实验请改为取消并说明原因）。删除会记录在审计日志中。'),
            h('button', { class: 'btn btn-danger btn-sm', onclick: function () {
              askReason('删除实验 ' + tx(e.code, ''), '删除原因', { kind: 'danger', okLabel: '删除实验' }).then(function (r) {
                if (r === null) return;
                api('DELETE', '/api/experiments/' + eid + '?reason=' + encodeURIComponent(r)).then(function () { setDirty(false); MF.toast('实验已删除', 'ok'); go('/m/' + p.id + '/experiments'); }, fail);
              });
            } }, '删除本实验')));
        }
        touch();
      }
      paint();
    });
  }

  // =====================================================================  文档（Word + PDF）
  var DOC_KINDS = [
    { kind: 'plan', title: '《方法开发方案》', keys: ['charter', 'atp', 'tech', 'risk', 'plan'], scope: '覆盖阶段：立项、ATP、技术选择、风险评估、开发方案',
      desc: '用于在开展实验前获得批准：包含立项背景、分析目标概况、技术选择与试剂策略、FMEA 风险评估、实验设计与签署记录。' },
    { kind: 'report', title: '《方法开发报告》', keys: null, scope: '覆盖阶段：全部阶段',
      desc: '用于方法开发结束后进入验证：在方案基础上增加可行性与优化、稳健性、控制策略、预验证结论及全部实验记录。' }
  ];
  var DOC_KIND_NAME = { plan: '方案', report: '报告' };
  function genDoc(mid, kind, btn) {
    return api('POST', '/api/methods/' + mid + '/docs', { kind: kind, lang: docsUI.lang || MF.lang || 'zh', async: true }).then(function (j) {
      if (!j || !j.job_id) return j;                       // (an older server answers synchronously)
      return new Promise(function (resolve, reject) {
        var t0 = Date.now();
        (function poll() {
          api('GET', '/api/jobs/' + j.job_id).then(function (st) {
            if (st.status === 'done') resolve(st.result);
            else if (st.status === 'error') { var e = new Error(st.error || '生成失败'); e.status = st.code; reject(e); }
            else { if (btn) btn.textContent = '生成中… 已用 ' + Math.round((Date.now() - t0) / 1000) + ' 秒（Word + PDF 约需 20–60 秒）'; setTimeout(poll, 1500); }
          }, reject);
        })();
      });
    });
  }
  var SAMPLE_WORD = '示例值';
  var docsUI = { mid: null, last: null };

  function docBtn(d, label, extraCls) {
    return h('a', { class: 'btn btn-sm ' + (extraCls || ''), href: '/api/docs/' + d.id + '/download', download: tx(d.filename, ''), title: tx(d.filename, '') }, label);
  }
  function docStatusKind(label) {
    label = String(label || '');
    if (label.indexOf('完整性') >= 0) return 'err';
    return label.indexOf('已批准') >= 0 ? 'ok' : 'warn';
  }

  function renderDocs(body, p, alive) {
    if (docsUI.mid !== p.id) docsUI = { mid: p.id, last: null };
    body.appendChild(h('div', { class: 'muted' }, '加载中…'));
    var warnReq = {};
    DOC_KINDS.forEach(function (k) { warnReq[k.kind] = api('GET', '/api/methods/' + p.id + '/stages/' + k.kind + '/checks').catch(function () { return null; }); });
    return Promise.all([
      api('GET', '/api/methods/' + p.id + '/docs'),
      api('GET', '/api/system/capabilities').catch(function () { return null; }),
      warnReq.plan, warnReq.report
    ]).then(function (rs) {
      if (!alive()) return;
      var docs = rs[0] || [], caps = rs[1];
      var checks = { plan: rs[2], report: rs[3] };
      draw(body, p, alive, docs, caps, checks);
    });
  }

  function draw(body, p, alive, docs, caps, checks) {
    MF.clear(body);
    var canGen = !!(p.permissions && p.permissions.can_generate_docs);
    var pdfOk = caps ? !!caps.pdf : null;

    // 能力提示
    body.appendChild(h('div', { class: 'callout' },
      '每次生成会同时产出 Word（.docx，可更新目录）与 PDF 两份文件，并计入审计。只有当所含阶段全部通过评审并锁定（且无失效阶段）时，才生成“已批准版本”；否则生成“草稿（含未复核内容）”，页眉、封面和水印会标注未批准的阶段，不得作为批准文件使用。',
      h('div', { class: 'small', style: 'margin-top:4px' }, 'PDF 导出：',
        pdfOk === null ? h('span', { class: 'muted' }, '未能确认服务器是否支持 PDF，生成后以实际结果为准。')
          : (pdfOk ? badge('可用', 'ok') : badge('不可用', 'warn')),
        caps && caps.pdf_note ? h('span', { class: 'muted' }, '　' + caps.pdf_note) : null)));

    // 完整性警告
    var curBad = p.signatures_ok === false || docs.some(function (d) { return d.signatures_ok === false; });
    if (curBad) {
      var bad = p.bad_signatures || (docs[0] && docs[0].bad_signatures) || [];
      body.appendChild(h('div', { class: 'callout callout-err' }, h('b', null, '签名完整性校验失败：'),
        '本方法已签署阶段的内容与签署时的哈希不一致。此时生成或已生成的文档均会标注“完整性校验失败”，请先联系管理员/QA 核查，不得作为批准文件使用。',
        bad.length ? h('ul', { style: 'margin:4px 0 0 18px;padding:0' }, bad.map(function (b) {
          return h('li', null, tx(b.title || b.stage) + (b.revision !== undefined ? '（R' + b.revision + '）' : '') + '：' + (b.problems || []).join('；'));
        })) : null));
    }

    // 上一次生成的结果（Word + PDF 下载）
    if (docsUI.last) body.appendChild(lastResult(docsUI.last));

    // 文档语言（英文文档：固定文字与章节标题为英文；模板预置正文与用户填写内容保持原样）
    var langSel = h('select', { class: 'select', style: 'width:auto' }, [h('option', { value: 'zh' }, '中文'), h('option', { value: 'en' }, 'English')]);
    langSel.value = docsUI.lang || MF.lang || 'zh';
    langSel.onchange = function () { docsUI.lang = langSel.value; };
    docsUI.lang = langSel.value;
    body.appendChild(h('div', { class: 'card' }, h('div', { class: 'row', style: 'gap:10px;align-items:center;flex-wrap:wrap' }, h('strong', null, '文档语言'), langSel,
      h('span', { class: 'small muted' }, '选 English 时，封面、表头、章节标题、签署页等固定文字为英文；模板预置的正文以及用户自己填写的内容保持原样（用英文填写即得到英文文档）。'))));
    // 生成卡片
    var cards = h('div', { class: 'mt-two' });
    DOC_KINDS.forEach(function (k) {
      var keys = k.keys || (p.stages || []).map(function (s) { return s.key; });
      var inc = (p.stages || []).filter(function (s) { return keys.indexOf(s.key) >= 0; });
      var bad = inc.filter(function (s) { return STAGE_LOCKED.indexOf(s.status) < 0 || s.stale; });
      var ck = checks[k.kind];
      var sampleWarns = ck && ck.warns ? ck.warns.filter(function (w) { return String(w).indexOf(SAMPLE_WORD) >= 0; }) : [];
      var btn = h('button', { class: 'btn btn-primary', disabled: !canGen, onclick: function () {
        btn.disabled = true; btn.textContent = '生成中，约需 20–60 秒…';
        genDoc(p.id, k.kind, btn).then(function (r) {
          // 兼容旧响应 {id, filename}
          var list = r && Array.isArray(r.docs) ? r.docs : (r && r.id ? [{ id: r.id, format: 'docx', filename: r.filename }] : []);
          docsUI.last = { kind: k.kind, gen_id: r && r.gen_id, docs: list, pdf_available: !!(r && r.pdf_available), pdf_note: r && r.pdf_note ? String(r.pdf_note) : '' };
          MF.toast('已生成' + k.title, 'ok');
          return renderDocs(body, p, alive);
        }, function (e) { fail(e); btn.disabled = false; btn.textContent = '生成' + k.title; });
      } }, '生成' + k.title);
      cards.appendChild(h('div', { class: 'card' }, h('h3', null, k.title), h('p', { class: 'muted' }, k.desc), h('p', { class: 'small' }, k.scope),
        h('div', { class: 'small', style: 'margin-bottom:6px' }, '生成前检查（所含阶段状态）：'),
        h('div', { class: 'mt-chips' }, inc.map(function (s) {
          var okS = STAGE_LOCKED.indexOf(s.status) >= 0 && !s.stale;
          return h('a', { class: 'mt-chip', href: '#/m/' + p.id + '/stage/' + s.key }, h('span', { class: 'mt-dot mt-dot-' + s.status }), tx(s.title), badge(tx(s.status_label, '') + (s.stale ? '·已失效' : ''), okS ? 'ok' : 'warn'));
        })),
        bad.length ? h('div', { class: 'callout callout-warn small' }, '⚠ 以下阶段尚未通过/已失效：' + bad.map(function (s) { return s.title; }).join('、') + '。现在生成将得到“草稿（含未复核内容）”，文档带“草稿—不得作为批准文件使用”标识。')
          : h('div', { class: 'callout callout-ok small' }, '所含阶段均已通过，将生成“已批准版本”。'),
        sampleWarns.length ? h('div', { class: 'callout callout-warn small' }, sampleWarns.map(function (w) { return h('div', null, '⚠ ' + w); }),
          h('div', { class: 'muted' }, '请按 ATP 确认后删去标记。')) : null,
        canGen ? null : h('div', { class: 'hint small muted' }, '您没有生成文档的权限（需方法团队的负责人/开发人员/复核人/批准人，或管理员）。'),
        btn));
    });
    body.appendChild(cards);

    // 历史：按 gen_id 分组，每组显示 Word 与 PDF
    var groups = [], idx = {};
    docs.forEach(function (d) {
      var key = d.gen_id ? 'g' + d.gen_id : 'd' + d.id;
      if (idx[key] === undefined) { idx[key] = groups.length; groups.push({ key: key, items: [] }); }
      groups[idx[key]].items.push(d);
    });
    body.appendChild(h('div', { class: 'card' }, h('h3', null, '生成历史（' + groups.length + ' 次，共 ' + docs.length + ' 个文件）'),
      groups.length ? h('div', { class: 'mt-tw' }, h('table', { class: 'table' },
        h('thead', null, h('tr', null, ['版本', '类型', '状态', '生成人', '时间', '数据哈希', 'Word', 'PDF'].map(function (c) { return h('th', null, c); }))),
        h('tbody', null, groups.map(function (g) {
          var d0 = g.items[0];
          var word = g.items.filter(function (d) { return d.format !== 'pdf'; })[0];
          var pdf = g.items.filter(function (d) { return d.format === 'pdf'; })[0];
          var genBad = g.items.some(function (d) { return d.generated_signatures_ok === false; });
          return h('tr', null, h('td', null, tx(d0.version_label)), h('td', null, DOC_KIND_NAME[d0.kind] || tx(d0.kind)),
            h('td', null, badge(tx(d0.status_label, '未知'), docStatusKind(d0.status_label)),
              genBad && String(d0.status_label || '').indexOf('完整性') < 0 ? badge('生成时完整性校验失败', 'err') : null,
              d0.signatures_ok === false ? h('div', { class: 'small', style: 'color:var(--c-err,#dc2626)' }, '当前完整性校验失败') : null),
            h('td', null, tx(d0.display_name)), h('td', { class: 'mt-nowrap' }, fdt(d0.created_at)),
            h('td', { class: 'mt-hash', title: tx(d0.data_hash, '') }, tx(d0.data_hash, '').slice(0, 12)),
            h('td', null, word ? docBtn(word, '下载 .docx') : h('span', { class: 'muted small' }, '—')),
            h('td', null, pdf ? docBtn(pdf, '下载 .pdf') : h('button', { class: 'btn btn-sm', disabled: true, title: pdfOk === false && caps && caps.pdf_note ? caps.pdf_note : '该次生成时没有产出 PDF' }, '无 PDF')));
        })))) : h('div', { class: 'empty' }, '尚未生成过文档')));
  }

  function lastResult(last) {
    var word = last.docs.filter(function (d) { return d.format !== 'pdf'; })[0];
    var pdf = last.docs.filter(function (d) { return d.format === 'pdf'; })[0];
    var note = last.pdf_note || '未检测到 LibreOffice（soffice），无法转换为 PDF。安装 LibreOffice 后重新生成，或在“管理→设置”中配置 soffice_path；Word 文档不受影响。';
    var pdfBtn = pdf ? docBtn(pdf, '下载 PDF', 'btn-primary')
      : h('button', { class: 'btn btn-sm', disabled: true, title: note }, '下载 PDF（不可用）');
    return h('div', { class: 'card', style: 'border-color:var(--c-ok,#16a34a)' },
      h('div', { class: 'toolbar' }, h('h3', { style: 'margin:0' }, '已生成：《方法开发' + (DOC_KIND_NAME[last.kind] || '') + '》'), h('span', { class: 'spacer' }),
        h('button', { class: 'btn btn-sm', onclick: function () { docsUI.last = null; MF.reload(); } }, '关闭')),
      h('div', { class: 'mt-actions' }, word ? docBtn(word, '下载 Word（.docx）', 'btn-primary') : null, pdfBtn),
      pdf ? null : h('div', { class: 'callout callout-warn small' }, 'PDF 未生成：' + note),
      h('div', { class: 'small muted' }, [word, pdf].filter(Boolean).map(function (d) { return tx(d.filename); }).join('　|　')));
  }

  // =====================================================================  审计
  var ACTION_LABEL = {
    'project.create': '创建项目', 'project.update': '修改项目', 'project.members': '调整项目成员',
    'method.create': '创建方法', 'method.update': '修改方法', 'method.members': '调整方法团队', 'method.clone': '克隆方法', 'method.lifecycle': '变更生命周期',
    'stage.save': '保存阶段', 'stage.submit': '提交复核', 'stage.complete': '阶段完成', 'stage.sign': '电子签名', 'stage.reject': '退回', 'stage.approved': '阶段通过',
    'stage.withdraw': '撤回提交', 'stage.reopen': '重新打开', 'experiment.create': '新增实验', 'experiment.update': '修改实验', 'experiment.status': '实验状态', 'experiment.delete': '删除实验',
    'attachment.add': '上传附件', 'attachment.delete': '删除附件', 'kb.lesson': '沉淀经验', 'document.generate': '生成文档'
  };
  var auditUI = { q: '' };
  function renderAudit(body, p, alive) {
    body.appendChild(h('div', { class: 'muted' }, '加载中…'));
    return api('GET', '/api/methods/' + p.id + '/audit?limit=1000').then(function (rows) {
      if (!alive()) return;
      rows = rows || [];
      MF.clear(body);
      var q = mkInput('text', auditUI.q, '按动作/用户/对象/原因筛选'); q.style.maxWidth = '260px';
      var tb = h('tbody', null);
      var cnt = h('span', { class: 'small muted' });
      var verifyBox = h('div', null);
      function paint() {
        auditUI.q = q.value;
        var qq = q.value.trim().toLowerCase();
        MF.clear(tb);
        var n = 0;
        rows.forEach(function (r) {
          var act = s0(r.action), lbl = ACTION_LABEL[act] || '';
          var hay = (act + ' ' + lbl + ' ' + s0(r.username) + ' ' + s0(r.entity_type) + ' ' + s0(r.entity_id) + ' ' + s0(r.reason)).toLowerCase();
          if (qq && hay.indexOf(qq) < 0) return;
          n++;
          var detail = h('tr', { style: 'display:none' }, h('td', { colspan: '6' }, h('pre', { class: 'mt-pre' }, detailText(r))));
          var open = false;
          var tr = h('tr', { class: 'mt-clickrow', title: '点击展开/收起详情', onclick: function () { open = !open; detail.style.display = open ? '' : 'none'; mark.textContent = open ? '▼' : '▶'; } },
            h('td', { class: 'mt-nowrap' }, fdt(r.ts)), h('td', null, tx(r.username)),
            h('td', null, h('div', null, tx(lbl, tx(act))), lbl ? h('div', { class: 'small muted' }, act) : null),
            h('td', null, tx(r.entity_type) + (r.entity_id ? ' #' + r.entity_id : '')), h('td', null, tx(r.reason)), null);
          var mark = h('td', { class: 'small muted' }, '▶');
          tr.appendChild(mark);
          tb.appendChild(tr); tb.appendChild(detail);
        });
        cnt.textContent = '共 ' + rows.length + ' 条' + (qq ? '，匹配 ' + n + ' 条' : '') + (rows.length >= 1000 ? '（仅显示最近 1000 条）' : '');
        if (!n) tb.appendChild(h('tr', null, h('td', { colspan: '6', class: 'empty' }, '没有匹配的审计记录')));
      }
      function detailText(r) {
        var o = { details: r.details, hash: r.hash, prev_hash: r.prev_hash };
        try { return JSON.stringify(o, null, 2); } catch (e) { return String(r.details); }
      }
      q.oninput = paint;
      var verifyBtn = (MF.hasRole && MF.hasRole('admin', 'approver')) ? h('button', { class: 'btn btn-sm', onclick: function () {
        verifyBtn.disabled = true;
        api('GET', '/api/audit/verify').then(function (r) {
          MF.clear(verifyBox);
          if (r && r.ok) verifyBox.appendChild(h('div', { class: 'callout callout-ok' }, '审计链校验通过：共 ' + tx(r.count, '0') + ' 条记录（全库），未发现篡改、删除或乱序。'));
          if (r && r.signatures_ok === false) verifyBox.appendChild(h('div', { class: 'callout callout-err' }, h('b', null, '签名完整性校验失败：'),
            h('ul', { style: 'margin:4px 0 0 18px;padding:0' }, (r.bad_signatures || []).map(function (b) { return h('li', null, tx(b.project) + ' / ' + tx(b.method) + ' / ' + tx(b.stage_title || b.stage) + '（R' + tx(b.revision) + '）：' + (b.problems || []).join('；')); }))));
          else verifyBox.appendChild(h('div', { class: 'callout callout-err' }, '审计链校验失败！首个异常记录 ID：' + tx(r && r.first_bad_id) + '（此前 ' + tx(r && r.count, '0') + ' 条正常）。请立即联系管理员并保留现场。'));
        }, fail).then(function () { verifyBtn.disabled = false; });
      } }, '校验审计链') : null;
      body.appendChild(h('div', { class: 'card' },
        h('div', { class: 'toolbar mt-tb' }, h('h3', { style: 'margin:0' }, '方法审计日志'), cnt, h('span', { class: 'spacer' }), q, verifyBtn),
        h('p', { class: 'small muted' }, '审计日志仅追加、采用哈希链，记录谁在何时做了什么及原因。点击一行展开详情。' + (verifyBtn ? '“校验审计链”校验的是全库的链。' : '')),
        verifyBox,
        h('div', { class: 'mt-tw' }, h('table', { class: 'table' }, h('thead', null, h('tr', null, ['时间', '用户', '动作', '对象', '原因', ''].map(function (c) { return h('th', null, c); }))), tb))));
      paint();
    });
  }

  // =====================================================================  知识
  var KB_KINDS = [['rule', '规则与原则'], ['pitfall', '易错点'], ['howto', '操作指南'], ['reference', '参考资料'], ['lesson', '经验教训']];
  var kbUI = { q: '' };
  function renderKb(body, p, alive) {
    body.appendChild(h('div', { class: 'muted' }, '加载中…'));
    return api('GET', '/api/methods/' + p.id + '/kb').then(function (items) {
      if (!alive()) return;
      items = items || [];
      MF.clear(body);
      var q = mkInput('text', kbUI.q, '搜索标题/内容/标签'); q.style.maxWidth = '280px';
      var list = h('div', null);
      function paint() {
        kbUI.q = q.value;
        var qq = q.value.trim().toLowerCase();
        MF.clear(list);
        var shown = 0;
        var kinds = KB_KINDS.slice();
        var known = KB_KINDS.map(function (k) { return k[0]; });
        items.forEach(function (it) { if (known.indexOf(it.kind) < 0 && kinds.every(function (k) { return k[0] !== it.kind; })) kinds.push([it.kind, tx(it.kind, '其他')]); });
        kinds.forEach(function (k) {
          var part = items.filter(function (it) {
            if (it.kind !== k[0]) return false;
            if (!qq) return true;
            return (s0(it.title) + ' ' + s0(it.body) + ' ' + (it.tags || []).join(' ') + ' ' + s0(it.source)).toLowerCase().indexOf(qq) >= 0;
          });
          if (!part.length) return;
          shown += part.length;
          var grpEl = h('details', { class: 'mt-kbg' }, h('summary', null, k[1] + '（' + part.length + '）'));
          grpEl.open = !!qq || k[0] === 'lesson';
          list.appendChild(grpEl);
          part.forEach(function (it) {
            grpEl.appendChild(h('div', { class: 'mt-kbi' },
              h('div', { style: 'font-weight:600' }, tx(it.title)),
              h('div', { class: 'mt-kb-body' }, tx(it.body, '')),
              h('div', { class: 'small muted' },
                (it.stages && it.stages.length) ? '适用阶段：' + it.stages.map(function (s) { return stageTitle(p, s); }).join('、') + '　' : '',
                it.source ? '来源：' + it.source : ''),
              (it.tags && it.tags.length) ? h('div', null, it.tags.map(function (t) { return badge(tx(t), 'muted'); })) : null));
          });
        });
        if (!shown) list.appendChild(h('div', { class: 'empty' }, items.length ? '没有匹配的条目' : '暂无与本方法相关的知识条目'));
      }
      q.oninput = paint;

      // 沉淀经验
      var can = canEdit(p);
      var tIn = mkInput('text', '', '一句话概括，如 “FcR 阻断不足导致背景升高”');
      var bIn = mkArea('', 4, '发生了什么、原因、如何避免/解决。沉淀后将出现在同类方法的知识推荐中。');
      var sSel = mkSelect([{ value: '', label: '（不限阶段）' }].concat((p.stages || []).map(function (s) { return { value: s.key, label: s.ord + '. ' + s.title }; })), '');
      var addBtn = h('button', { class: 'btn btn-primary btn-sm', onclick: function () {
        if (!tIn.value.trim() || !bIn.value.trim()) { MF.toast('请填写标题和内容', 'err'); return; }
        addBtn.disabled = true;
        api('POST', '/api/methods/' + p.id + '/lessons', { title: tIn.value.trim(), body: bIn.value.trim(), stage_key: sSel.value || null }).then(function () {
          MF.toast('经验已沉淀', 'ok'); MF.reload();
        }, function (e) { fail(e); addBtn.disabled = false; });
      } }, '沉淀经验');
      body.appendChild(h('div', { class: 'card' },
        h('div', { class: 'toolbar mt-tb' }, h('h3', { style: 'margin:0' }, '本方法相关知识（' + items.length + '）'), h('span', { class: 'spacer' }), q),
        h('p', { class: 'small muted' }, '按本方法的技术模板筛选的规则、易错点、操作指南和经验教训。在阶段页中也会按阶段推荐。'),
        list));
      body.appendChild(h('div', { class: 'card' }, h('h3', null, '沉淀经验'),
        can ? h('div', null, h('p', { class: 'small muted' }, '把本方法中学到的教训记录下来，供后续同类方法参考（记为“经验教训”，来源标注为本方法）。'),
          field('标题', tIn), field('关联阶段', sSel), field('内容', bIn), addBtn)
          : h('div', { class: 'muted' }, '仅方法负责人/开发人员可沉淀经验。')));
      paint();
    });
  }

  // =====================================================================  路由
  MF.route('/m/:mid', function (params, container) {
    return shell(container, params.mid, 'overview', function (body, p, alive) { return renderOverview(body, p, alive); });
  });
  MF.route('/m/:mid/stage/:key', function (params, container) {
    return shell(container, params.mid, 'stage', function (body, p) { return renderStagePage(body, p, params.key); },
      function (p) { return [{ label: stageTitle(p, params.key) }]; });
  });
  MF.route('/m/:mid/exp/:eid', function (params, container) {
    return shell(container, params.mid, 'experiments', function (body, p, alive) { return renderExpDetail(body, p, toInt(params.eid), alive); },
      function () { return [{ label: '实验', href: '/m/' + params.mid + '/experiments' }, { label: '实验 #' + params.eid }]; });
  });
  MF.route('/m/:mid/:tab', function (params, container) {
    var tab = params.tab;
    var labels = { experiments: '实验', docs: '文档', audit: '审计', kb: '知识' };
    (MF.methodTabs || []).forEach(function (t) { labels[t.k] = t.l; });
    if (!labels[tab]) {
      return shell(container, params.mid, '', function (body) {
        body.appendChild(h('div', { class: 'card' }, h('h3', null, '页面不存在'), h('p', { class: 'muted' }, '没有名为“' + tx(tab) + '”的方法页面。'), h('a', { class: 'btn', href: '#/m/' + params.mid }, '返回总览')));
      });
    }
    return shell(container, params.mid, tab, function (body, p, alive) {
      var xt = (MF.methodTabs || []).filter(function (t) { return t.k === tab; })[0];
      if (xt) return xt.render(body, p, alive);
      if (tab === 'experiments') return renderExperiments(body, p, alive);
      if (tab === 'docs') return renderDocs(body, p, alive);
      if (tab === 'audit') return renderAudit(body, p, alive);
      return renderKb(body, p, alive);
    }, function () { return [{ label: labels[tab] }]; });
  });
})();
