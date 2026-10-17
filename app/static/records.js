/* MethodFlow - 记录类功能的前端（records.js）
 *   运行记录面板（实验详情页）、结果表工具（计算器 / CSV 导入）、偏离记录标签页、检查包与修订版按钮、章节评论
 * 通过 MF.records.* 钩子被 method.js / stage.js 调用；通过 MF.methodTabs 注册方法页标签。 */
(function () {
  'use strict';
  var MF = window.MF, h = MF.h;
  var api = MF.api;
  var OPT = null;

  function opts() {
    if (OPT) return Promise.resolve(OPT);
    return api('GET', '/api/registry/options').then(function (o) { OPT = o; return o; });
  }
  function sel(list, value, allowEmpty) {
    var s = h('select', { class: 'select' }, (allowEmpty ? [h('option', { value: '' }, '（不选）')] : []).concat(list.map(function (x) { return h('option', { value: String(x.key) }, x.label); })));
    if (value !== undefined && value !== null) s.value = String(value);
    return s;
  }
  function canEdit(p) { return !!(p.permissions && p.permissions.can_edit_content) && p.status === 'active'; }
  function label(list, key) { var x = (list || []).filter(function (i) { return i.key === key; })[0]; return x ? x.label : key; }
  function multi(items, selected) {
    var box = h('div', { class: 'row', style: { flexDirection: 'column', alignItems: 'flex-start', gap: '2px', maxHeight: '140px', overflowY: 'auto', border: '1px solid var(--c-border,#d0d7de)', borderRadius: '6px', padding: '6px' } });
    var checks = {};
    if (!items.length) box.appendChild(h('span', { class: 'small muted' }, '（台账里还没有可选项）'));
    items.forEach(function (it) {
      var c = h('input', { type: 'checkbox' });
      c.checked = (selected || []).indexOf(it.id) >= 0;
      checks[it.id] = c;
      box.appendChild(h('label', { class: 'small' }, c, ' ', it.text));
    });
    box.values = function () { return Object.keys(checks).filter(function (k) { return checks[k].checked; }).map(Number); };
    return box;
  }
  function err(e) { return (e && e.message) || '操作失败'; }

  // ------------------------------------------------------------------ result table tools
  function parseCsv(text) {
    var ls = String(text || '').split(/\r?\n/).filter(function (l) { return l.trim(); });
    if (!ls.length) return [];
    var delim = ls[0].indexOf('\t') >= 0 ? '\t' : (ls[0].indexOf(';') >= 0 && ls[0].indexOf(',') < 0 ? ';' : ',');
    function cells(l) {
      var out = [], cur = '', q = false;
      for (var i = 0; i < l.length; i++) {
        var ch = l[i];
        if (ch === '"') { if (q && l[i + 1] === '"') { cur += '"'; i++; } else q = !q; }
        else if (ch === delim && !q) { out.push(cur); cur = ''; }
        else cur += ch;
      }
      out.push(cur);
      return out.map(function (x) { return x.trim(); });
    }
    var rows = ls.map(cells);
    var head = rows[0].map(function (x) { return x.toLowerCase(); });
    var mi = head.indexOf('metric'), vi = head.indexOf('value'), ci = head.indexOf('criterion');
    var hasHead = mi >= 0 || head.indexOf('指标') >= 0 || head.indexOf('结果') >= 0 || head.indexOf('判据') >= 0;
    if (hasHead) {
      if (mi < 0) mi = head.indexOf('指标');
      if (vi < 0) vi = head.indexOf('结果') >= 0 ? head.indexOf('结果') : head.indexOf('实测值');
      if (ci < 0) ci = head.indexOf('判据');
      rows = rows.slice(1);
    } else { mi = 0; vi = 1; ci = 2; }
    return rows.map(function (r) { return { metric: r[mi] || '', value: vi >= 0 ? (r[vi] || '') : '', criterion: ci >= 0 ? (r[ci] || '') : '', verdict: '待评估' }; })
      .filter(function (r) { return r.metric || r.value; });
  }

  function resultTools(D, repaint, readonly) {
    if (readonly) return null;
    var file = h('input', { type: 'file', accept: '.csv,.tsv,.txt', style: { display: 'none' } });
    file.addEventListener('change', function () {
      var f = file.files && file.files[0];
      if (!f) return;
      var rd = new FileReader();
      rd.onload = function () {
        var rows = parseCsv(String(rd.result));
        if (!rows.length) { MF.toast('文件里没有可导入的行（需要“指标, 结果, 判据”三列）', 'warn'); return; }
        MF.confirm('从“' + f.name + '”导入 ' + rows.length + ' 行结果，追加到结果表？（列：指标、结果、判据，有表头时按表头识别）').then(function (ok) {
          if (!ok) return;
          rows.forEach(function (r) { D.results.push(r); });
          repaint();
          MF.toast('已导入 ' + rows.length + ' 行（记得保存）', 'ok');
        });
      };
      rd.readAsText(f, 'utf-8');
      file.value = '';
    });
    return h('span', { class: 'row', style: { gap: '6px' } },
      MF.calc ? h('button', { class: 'btn btn-sm', type: 'button', onclick: function () { MF.calc.open(function (rows) { rows.forEach(function (r) { D.results.push(r); }); repaint(); }); } }, '统计计算器') : null,
      h('button', { class: 'btn btn-sm', type: 'button', onclick: function () { file.click(); } }, '导入 CSV'), file);
  }

  // ------------------------------------------------------------------ run records (experiment page)
  function runDialog(p, e, run) {
    return Promise.all([opts(), api('GET', '/api/materials'), api('GET', '/api/equipment')]).then(function (rs) {
      var o = rs[0];
      var today = new Date(); var iso = today.getFullYear() + '-' + ('0' + (today.getMonth() + 1)).slice(-2) + '-' + ('0' + today.getDate()).slice(-2);
      var date = h('input', { class: 'input', type: 'date', value: (run && run.run_date) || iso });
      var team = (p.members || []).filter(function (m) { return ['owner', 'author', 'reviewer', 'approver'].indexOf(m.role) >= 0; });
      var seen = {}, people = [];
      team.forEach(function (m) { if (!seen[m.user_id]) { seen[m.user_id] = 1; people.push({ key: m.user_id, label: m.display_name }); } });
      var analyst = sel(people, run ? run.analyst_id : (MF.state.user && MF.state.user.id));
      var outcome = sel(o.run_outcomes, run ? run.outcome : 'valid');
      var mats = multi(rs[1].map(function (m) { return { id: m.id, text: m.code + ' ' + m.name + (m.lot ? ' / ' + m.lot : '') + (m.expiry_state === 'expired' ? '  ⚠已过期' : '') }; }), run && run.materials);
      var eqs = multi(rs[2].map(function (q) { return { id: q.id, text: q.code + ' ' + q.name + (q.calibration_state === 'overdue' ? '  ⚠校准过期' : '') }; }), run && run.equipment);
      var summary = h('textarea', { class: 'textarea', rows: 3, placeholder: '这次运行做了什么、样品/批次、异常' });
      summary.value = run ? run.summary : '';
      var body = h('div', null, h('div', { class: 'form-grid' }, MF.field('运行日期', date), MF.field('分析员', analyst), MF.field('结果状态', outcome)),
        MF.field('使用的材料', mats, { hint: '来自“台账”页；过期或隔离的材料会在记录上显示警示。' }), MF.field('使用的仪器', eqs), MF.field('运行摘要', summary));
      return MF.modal({
        title: run ? '修改运行记录 ' + run.code : '新增运行记录', width: 640, body: body,
        buttons: [{ label: '取消', value: null }, { label: '保存', kind: 'primary', onClick: async function (ctl) {
          var d = { run_date: date.value, analyst_id: Number(analyst.value), outcome: outcome.value, summary: summary.value, materials: mats.values(), equipment: eqs.values() };
          try {
            if (run) { d.version = run.version; await api('PUT', '/api/runs/' + run.id, d); }
            else { d.experiment_id = e.id; await api('POST', '/api/methods/' + p.id + '/runs', d); }
            ctl.close(true);
          } catch (x) { ctl.error(err(x)); ctl.setBusy(false); return false; }
        } }]
      });
    });
  }

  function runsPanel(p, e, locked) {
    var card = h('div', { class: 'card' });
    function paint() {
      MF.clear(card);
      card.appendChild(h('div', { class: 'toolbar' }, h('h3', { style: { margin: 0 } }, '运行记录'), h('span', { class: 'spacer' }),
        (canEdit(p) && !locked) ? h('button', { class: 'btn btn-sm btn-primary', type: 'button', onclick: function () { runDialog(p, e, null).then(function (ok) { if (ok) { MF.toast('已新增运行记录', 'ok'); paint(); } }); } }, '＋ 新增运行记录') : null));
      var holder = h('div', null, MF.loading());
      card.appendChild(holder);
      api('GET', '/api/methods/' + p.id + '/runs?experiment_id=' + e.id).then(function (runs) {
        MF.clear(holder);
        if (!runs.length) { holder.appendChild(h('div', { class: 'small muted' }, '还没有运行记录。每次实际执行实验时记录日期、分析员、仪器、材料和结果，由第二人核对。')); return; }
        holder.appendChild(h('div', { class: 'mt-tw' }, h('table', { class: 'table' },
          h('thead', null, h('tr', null, ['编号', '日期', '分析员', '材料 / 仪器', '结果', '核对', ''].map(function (t) { return h('th', null, t); }))),
          h('tbody', null, runs.map(function (r) {
            var me = MF.state.user || {};
            var canVerify = !r.verified && me.id && me.id !== r.analyst_id && me.id !== r.created_by && !!(p.my_roles || []).length;
            return h('tr', null,
              h('td', null, r.code), h('td', null, MF.fmt.date(r.run_date)), h('td', null, r.analyst_name),
              h('td', { class: 'small' }, (r.material_items.concat(r.equipment_items)).map(function (i) { return h('div', null, i.label); }),
                (r.warnings || []).map(function (w) { return h('div', { style: { color: 'var(--c-err,#c0392b)' } }, '⚠ ' + w); })),
              h('td', null, MF.badge(r.outcome_label, r.outcome === 'valid' ? 'ok' : 'warn'), r.summary ? h('div', { class: 'small muted' }, r.summary) : null),
              h('td', null, r.verified ? MF.badge('已核对：' + r.verified_name, 'ok') : MF.badge('待核对', 'muted')),
              h('td', { style: { whiteSpace: 'nowrap' } },
                canVerify ? h('button', { class: 'btn btn-sm', type: 'button', onclick: function () {
                  MF.confirm('确认您已核对运行记录 ' + r.code + '（材料、仪器、日期、结果）与原始记录一致？').then(function (ok) {
                    if (!ok) return;
                    api('POST', '/api/runs/' + r.id + '/verify').then(function () { MF.toast('已核对', 'ok'); paint(); }, function (x) { MF.toast(err(x), 'err'); });
                  });
                } }, '核对') : null,
                (canEdit(p) && !locked && !r.verified) ? h('button', { class: 'btn btn-sm', type: 'button', onclick: function () { runDialog(p, e, r).then(function (ok) { if (ok) paint(); }); } }, '修改') : null));
          })))));
      }, function (x) { MF.clear(holder); holder.appendChild(MF.errorBox(x, paint)); });
    }
    paint();
    return card;
  }

  // ------------------------------------------------------------------ header actions (method page)
  function headerActions(p) {
    var out = [];
    out.push(h('a', { class: 'btn btn-sm', href: '/api/methods/' + p.id + '/dossier', title: '下载检查包（zip）：内容、实验、运行、偏离、签名清单、审计追踪、附件与哈希清单、已生成文档', download: '' }, '检查包'));
    var perm = p.permissions || {};
    var anyLocked = (p.stages || []).some(function (s) { return s.status === 'approved' || s.status === 'completed'; });
    if (perm.can_change_lifecycle && anyLocked && p.status === 'active') {
      out.push(h('button', { class: 'btn btn-sm', type: 'button', title: '方法已批准后要变更：创建一个新的修订版（保留旧版）', onclick: function () {
        var note = h('textarea', { class: 'textarea', rows: 4, placeholder: '变更说明（必填）：改什么、为什么、对已批准内容的影响' });
        var ver = h('input', { class: 'input', type: 'text', placeholder: '留空自动递增，如 V1.1' });
        MF.modal({ title: '创建修订版', width: 560, body: h('div', null, h('p', { class: 'small muted' }, '会复制当前内容（保持“已确认”状态）为一个新的方法，指向本方法；本方法不变。新方法需重新走各阶段评审。'),
          MF.field('变更说明', note, { required: true }), MF.field('新方法版本', ver)),
          buttons: [{ label: '取消', value: null }, { label: '创建', kind: 'primary', onClick: async function (ctl) {
            try { var r = await api('POST', '/api/methods/' + p.id + '/revise', { note: note.value, version: ver.value }); ctl.close(r.id); }
            catch (x) { ctl.error(err(x)); ctl.setBusy(false); return false; }
          } }] }).then(function (id) { if (id) { MF.toast('已创建修订版', 'ok'); MF.navigate('/m/' + id); } });
      } }, '创建修订版'));
    }
    return out;
  }

  function lineage(p) {
    var parts = [];
    if (p.revision_of_info) parts.push(h('div', { class: 'callout' }, '本方法是 ', h('a', { href: '#/m/' + p.revision_of_info.id }, p.revision_of_info.code + ' ' + (p.revision_of_info.method_version || '')), ' 的修订版。变更说明：' + (p.revision_note || '—')));
    if ((p.revisions || []).length) parts.push(h('div', { class: 'small muted' }, '后续修订版：', p.revisions.map(function (r) { return h('a', { href: '#/m/' + r.id, style: { marginRight: '8px' } }, r.code + ' ' + (r.method_version || '')); })));
    return parts.length ? h('div', null, parts) : null;
  }

  // ------------------------------------------------------------------ deviations tab
  function devDialog(p, dev) {
    return opts().then(function (o) {
      return api('GET', '/api/methods/' + p.id + '/experiments').then(function (exps) {
        var title = h('input', { class: 'input', type: 'text', maxlength: 300, value: dev ? dev.title : '' });
        var cls = sel(o.deviation_classes, dev ? dev.classification : 'minor');
        var stageSel = sel((p.stages || []).map(function (s) { return { key: s.key, label: s.ord + '. ' + s.title }; }), dev ? dev.stage_key : '', true);
        var expSel = sel(exps.map(function (x) { return { key: x.id, label: x.code + ' ' + x.title }; }), dev ? dev.experiment_id : '', true);
        function area(v, rows, ph) { var t = h('textarea', { class: 'textarea', rows: rows, placeholder: ph || '' }); t.value = v || ''; return t; }
        var desc = area(dev && dev.description, 4, '发生了什么、何时、在哪个实验/步骤');
        var impact = area(dev && dev.impact, 2, '对结果、ATP 判据、已批准内容的影响');
        var cause = area(dev && dev.root_cause, 2, '根本原因（关闭前必填）');
        var action = area(dev && dev.action, 2, '纠正与预防措施（关闭前必填）');
        var status = dev ? sel(o.deviation_status.filter(function (s) { return s.key !== 'closed'; }), dev.status) : null;
        return MF.modal({
          title: dev ? '偏离 ' + dev.code : '新增偏离', width: 680,
          body: h('div', null, MF.field('标题', title, { required: true }), h('div', { class: 'form-grid' }, MF.field('分类', cls), dev ? MF.field('状态', status) : null),
            h('div', { class: 'form-grid' }, MF.field('关联步骤', stageSel), MF.field('关联实验', expSel)),
            MF.field('偏离描述', desc), MF.field('影响评估', impact), MF.field('根本原因', cause), MF.field('纠正 / 预防措施', action)),
          buttons: [{ label: '取消', value: null }, { label: '保存', kind: 'primary', onClick: async function (ctl) {
            var d = { title: title.value, classification: cls.value, description: desc.value, impact: impact.value, root_cause: cause.value, action: action.value,
              stage_key: stageSel.value || null, experiment_id: expSel.value ? Number(expSel.value) : null };
            try {
              if (dev) { d.version = dev.version; d.status = status.value; await api('PUT', '/api/deviations/' + dev.id, d); }
              else await api('POST', '/api/methods/' + p.id + '/deviations', d);
              ctl.close(true);
            } catch (x) { ctl.error(err(x)); ctl.setBusy(false); return false; }
          } }]
        });
      });
    });
  }

  function renderDeviations(body, p, alive) {
    var holder = h('div');
    body.appendChild(h('div', { class: 'card' }, h('div', { class: 'toolbar' }, h('h3', { style: { margin: 0 } }, '偏离记录'), h('span', { class: 'spacer' }),
      canEdit(p) ? h('button', { class: 'btn btn-sm btn-primary', type: 'button', onclick: function () { devDialog(p, null).then(function (ok) { if (ok) { MF.toast('已记录偏离', 'ok'); paint(); } }); } }, '＋ 新增偏离') : null),
      h('p', { class: 'small muted' }, '偏离 = 与方案不一致的情况。未关闭的“主要/严重”偏离会阻止其所属步骤提交；关闭需要电子签名（不能由提出人关闭，主要/严重须批准人）。'), holder));
    function paint() {
      MF.clear(holder); holder.appendChild(MF.loading());
      api('GET', '/api/methods/' + p.id + '/deviations').then(function (list) {
        if (alive && !alive()) return;
        MF.clear(holder);
        if (!list.length) { holder.appendChild(h('div', { class: 'empty' }, '暂无偏离记录。')); return; }
        holder.appendChild(h('div', { class: 'mt-tw' }, h('table', { class: 'table' },
          h('thead', null, h('tr', null, ['编号', '标题', '分类', '状态', '关联', '提出', ''].map(function (t) { return h('th', null, t); }))),
          h('tbody', null, list.map(function (d) {
            var closed = d.status === 'closed';
            return h('tr', null, h('td', null, d.code), h('td', null, d.title, d.description ? h('div', { class: 'small muted' }, d.description.slice(0, 120)) : null),
              h('td', null, MF.badge(d.classification_label, d.classification === 'minor' ? 'muted' : (d.classification === 'major' ? 'warn' : 'err'))),
              h('td', null, MF.badge(d.status_label, closed ? 'ok' : 'warn'), closed ? h('div', { class: 'small muted' }, d.closed_name + ' · ' + MF.fmt.date(d.closed_at)) : null),
              h('td', { class: 'small' }, [d.stage_key ? ((p.stages || []).filter(function (s) { return s.key === d.stage_key; })[0] || {}).title : '', d.experiment_code].filter(Boolean).join(' / ') || '—'),
              h('td', { class: 'small' }, d.opened_name + ' · ' + MF.fmt.date(d.opened_at)),
              h('td', { style: { whiteSpace: 'nowrap' } },
                closed ? h('button', { class: 'btn btn-sm', type: 'button', onclick: async function () {
                  var r = await MF.askSign({ title: '重新打开偏离 ' + d.code, meaning: '我确认重新打开偏离 ' + d.code + '。', needComment: true, commentRequired: true, commentLabel: '重新打开的原因（必填）' });
                  if (!r) return;
                  try { await api('POST', '/api/deviations/' + d.id + '/reopen', { password: r.password, reason: r.comment }); MF.toast('已重新打开', 'ok'); paint(); } catch (x) { MF.toast(err(x), 'err'); }
                } }, '重新打开') : [
                  canEdit(p) ? h('button', { class: 'btn btn-sm', type: 'button', onclick: function () { devDialog(p, d).then(function (ok) { if (ok) paint(); }); } }, '编辑') : null,
                  h('button', { class: 'btn btn-sm btn-primary', type: 'button', style: { marginLeft: '4px' }, onclick: async function () {
                    var r = await MF.askSign({ title: '关闭偏离 ' + d.code, meaning: '我确认偏离 ' + d.code + '（' + d.title + '）已完成调查和处理，同意关闭。', needComment: true, commentRequired: true, commentLabel: '关闭说明（必填）' });
                    if (!r) return;
                    try { await api('POST', '/api/deviations/' + d.id + '/close', { password: r.password, note: r.comment }); MF.toast('偏离已关闭', 'ok'); paint(); } catch (x) { MF.toast(err(x), 'err'); }
                  } }, '关闭')]));
          })))));
      }, function (x) { MF.clear(holder); holder.appendChild(MF.errorBox(x, paint)); });
    }
    paint();
  }

  // ------------------------------------------------------------------ section comments (stage page)
  function commentDialog(ctx, secKey, secTitle, onChange) {
    var list = h('div'), ta = h('textarea', { class: 'textarea', rows: 3, placeholder: '写评论；用 @用户名 提醒同事' });
    var base = '/api/methods/' + ctx.mid + '/stages/' + ctx.key + '/comments';
    function paint() {
      MF.clear(list); list.appendChild(MF.loading());
      api('GET', base).then(function (all) {
        MF.clear(list);
        var mine = all.filter(function (c) { return (c.section_key || '') === secKey; });
        if (!mine.length) list.appendChild(h('div', { class: 'small muted' }, '还没有评论。'));
        mine.forEach(function (c) {
          list.appendChild(h('div', { class: 'card', style: { marginBottom: '6px', padding: '8px', opacity: c.resolved ? 0.6 : 1 } },
            h('div', { class: 'small muted' }, c.user_name + ' · ' + MF.fmt.datetime(c.created_at) + (c.resolved ? ' · 已处理（' + c.resolved_name + '）' : '')),
            h('div', { style: { whiteSpace: 'pre-wrap' } }, c.body),
            h('button', { class: 'btn btn-sm', type: 'button', style: { marginTop: '4px' }, onclick: function () {
              api('POST', '/api/comments/' + c.id + '/resolve', { resolved: !c.resolved }).then(function () { paint(); if (onChange) onChange(); }, function (x) { MF.toast(err(x), 'err'); });
            } }, c.resolved ? '重新打开' : '标为已处理')));
        });
      }, function (x) { MF.clear(list); list.appendChild(MF.errorBox(x, paint)); });
    }
    paint();
    return MF.modal({ title: '评论：' + (secTitle || '整个阶段'), width: 620, body: h('div', null, list, MF.field('新评论', ta)),
      buttons: [{ label: '关闭', value: null }, { label: '发表', kind: 'primary', onClick: async function (ctl) {
        if (!ta.value.trim()) { ctl.error('请填写评论内容'); ctl.setBusy(false); return false; }
        try { await api('POST', base, { section_key: secKey, body: ta.value }); ta.value = ''; paint(); if (onChange) onChange(); } catch (x) { ctl.error(err(x)); }
        ctl.setBusy(false); return false;
      } }] });
  }

  // one request serves all the comment buttons of a stage page (they are created together); a change forces a fresh load
  function fetchComments(ctx, force) {
    var now = Date.now();
    if (force || !ctx._cmt || now - ctx._cmt.t > 1500) ctx._cmt = { t: now, p: api('GET', '/api/methods/' + ctx.mid + '/stages/' + ctx.key + '/comments') };
    return ctx._cmt.p;
  }

  function commentButton(ctx, sec) {
    var key = sec ? sec.key : '';
    var btn = h('button', { class: 'btn btn-sm btn-ghost', type: 'button', title: '评论 / 讨论', 'aria-label': '评论' }, '💬');
    function count(force) {
      fetchComments(ctx, force === true).then(function (all) {
        var open = all.filter(function (c) { return (c.section_key || '') === key && !c.resolved; }).length;
        var total = all.filter(function (c) { return (c.section_key || '') === key; }).length;
        btn.textContent = '💬' + (total ? ' ' + (open ? open : '✓') : '');
        btn.title = total ? (open + ' 条未处理 / 共 ' + total + ' 条') : '评论 / 讨论';
      }, function () { /* ignore */ });
    }
    btn.addEventListener('click', function () { commentDialog(ctx, key, sec ? sec.title : '', function () { count(true); }); });
    count();
    return btn;
  }

  MF.methodTabs = MF.methodTabs || [];
  MF.methodTabs.push({ k: 'deviations', l: '偏离', render: renderDeviations });
  MF.records = { resultTools: resultTools, runsPanel: runsPanel, headerActions: headerActions, lineage: lineage, commentButton: commentButton };
})();
