/* MethodFlow - 台账、审计追踪审核、全局搜索页（extras.js）
 *   /registry        试剂/材料与仪器/设备台账（批号、效期、校准到期）
 *   /audit-review    审计追踪审核记录（管理员/批准人，电子签名）
 *   /search          全局搜索
 *   MF.setMyEmail()  设置本人邮箱（用于邮件通知） */
(function () {
  'use strict';
  var MF = window.MF, h = MF.h, api = MF.api;
  function err(e) { return (e && e.message) || '操作失败'; }
  function canWrite() { return MF.hasRole('author', 'admin', 'approver'); }
  function canAdmin() { return MF.hasRole('admin', 'approver'); }
  function opts() { return api('GET', '/api/registry/options'); }
  function sel(list, value, allowEmpty, emptyLabel) {
    var s = h('select', { class: 'select' }, (allowEmpty ? [h('option', { value: '' }, emptyLabel || '（全部）')] : []).concat(list.map(function (x) { return h('option', { value: x.key }, x.label); })));
    if (value !== undefined && value !== null) s.value = value;
    return s;
  }
  function text(v, ph, type) { var i = h('input', { class: 'input', type: type || 'text', placeholder: ph || '' }); i.value = v || ''; return i; }
  function expiryChip(state, date) {
    if (state === 'expired') return MF.badge('已过期 ' + MF.fmt.date(date), 'err');
    if (state === 'soon') return MF.badge('30 天内到期 ' + MF.fmt.date(date), 'warn');
    if (state === 'ok') return MF.badge(MF.fmt.date(date), 'ok');
    return MF.badge('未设置', 'muted');
  }
  function calChip(state, date) {
    if (state === 'overdue') return MF.badge('校准过期 ' + MF.fmt.date(date), 'err');
    if (state === 'soon') return MF.badge('30 天内到期 ' + MF.fmt.date(date), 'warn');
    if (state === 'ok') return MF.badge(MF.fmt.date(date), 'ok');
    return MF.badge('未设置', 'muted');
  }

  // ------------------------------------------------------------------ registry
  function materialDialog(o, m) {
    var f = { name: text(m && m.name), kind: sel(o.material_kinds, m ? m.kind : 'reagent'), supplier: text(m && m.supplier), catalog_no: text(m && m.catalog_no), lot: text(m && m.lot),
      grade: text(m && m.grade), concentration: text(m && m.concentration), storage: text(m && m.storage), received_at: text(m && m.received_at, '', 'date'), expiry_at: text(m && m.expiry_at, '', 'date'),
      status: sel(o.material_status, m ? m.status : 'active'), notes: h('textarea', { class: 'textarea', rows: 2 }), critical: h('input', { type: 'checkbox' }) };
    f.notes.value = (m && m.notes) || '';
    f.critical.checked = !!(m && m.critical);
    var body = h('div', null, MF.field('名称', f.name, { required: true }),
      h('div', { class: 'form-grid' }, MF.field('类别', f.kind), MF.field('状态', f.status), MF.field('供应商', f.supplier), MF.field('货号', f.catalog_no), MF.field('批号', f.lot), MF.field('规格/等级', f.grade),
        MF.field('浓度', f.concentration), MF.field('储存条件', f.storage), MF.field('接收日期', f.received_at), MF.field('效期', f.expiry_at)),
      h('label', { class: 'small' }, f.critical, ' 关键试剂/材料（需数据表、批放行与桥接规则）'), MF.field('备注', f.notes));
    return MF.modal({ title: m ? '修改材料 ' + m.code : '新增材料', width: 680, body: body, buttons: [{ label: '取消', value: null }, { label: '保存', kind: 'primary', onClick: async function (ctl) {
      var d = {}; Object.keys(f).forEach(function (k) { d[k] = f[k].value; }); d.critical = f.critical.checked;
      d.received_at = d.received_at || null; d.expiry_at = d.expiry_at || null;
      try { if (m) await api('PUT', '/api/materials/' + m.id, d); else await api('POST', '/api/materials', d); ctl.close(true); } catch (e) { ctl.error(err(e)); ctl.setBusy(false); return false; }
    } }] });
  }
  function equipmentDialog(o, q) {
    var f = { name: text(q && q.name), model: text(q && q.model), serial_no: text(q && q.serial_no), location: text(q && q.location), last_calibration: text(q && q.last_calibration, '', 'date'),
      calibration_due: text(q && q.calibration_due, '', 'date'), status: sel(o.equipment_status, q ? q.status : 'active'), notes: h('textarea', { class: 'textarea', rows: 2 }) };
    f.notes.value = (q && q.notes) || '';
    return MF.modal({ title: q ? '修改仪器 ' + q.code : '新增仪器', width: 640, body: h('div', null, MF.field('名称', f.name, { required: true }),
      h('div', { class: 'form-grid' }, MF.field('型号', f.model), MF.field('序列号/资产号', f.serial_no), MF.field('位置', f.location), MF.field('状态', f.status), MF.field('上次校准', f.last_calibration), MF.field('校准到期', f.calibration_due)), MF.field('备注', f.notes)),
      buttons: [{ label: '取消', value: null }, { label: '保存', kind: 'primary', onClick: async function (ctl) {
        var d = {}; Object.keys(f).forEach(function (k) { d[k] = f[k].value; }); d.last_calibration = d.last_calibration || null; d.calibration_due = d.calibration_due || null;
        try { if (q) await api('PUT', '/api/equipment/' + q.id, d); else await api('POST', '/api/equipment', d); ctl.close(true); } catch (e) { ctl.error(err(e)); ctl.setBusy(false); return false; }
      } }] });
  }

  MF.route('/registry', async function (params, c) {
    MF.setCrumbs([{ label: '台账' }]);
    var o = await opts();
    var tab = 'materials', showAll = false;
    var holder = h('div');
    var qIn = h('input', { class: 'input', type: 'search', placeholder: '搜索名称、批号、货号、编号', style: { maxWidth: '280px' } });
    var kindSel = sel(o.material_kinds, '', true, '全部类别');
    var stateSel = sel([{ key: 'expired', label: '已过期/校准过期' }, { key: 'soon', label: '30 天内到期' }], '', true, '全部状态');
    var allBox = h('input', { type: 'checkbox' });
    var tabs = h('div', { class: 'tabs' });
    var alerts = h('div');
    function drawTabs() {
      MF.clear(tabs);
      [['materials', '试剂 / 材料'], ['equipment', '仪器 / 设备']].forEach(function (t) {
        tabs.appendChild(h('a', { class: 'tab' + (tab === t[0] ? ' tab-active' : ''), href: 'javascript:void(0)', onclick: function () { tab = t[0]; kindSel.style.display = tab === 'materials' ? '' : 'none'; drawTabs(); load(); } }, t[1]));
      });
    }
    async function drawAlerts() {
      try {
        var a = await api('GET', '/api/registry/alerts');
        MF.clear(alerts);
        if (a.materials.length || a.equipment.length) {
          alerts.appendChild(h('div', { class: 'callout callout-warn' }, h('strong', null, '需要关注：'),
            a.materials.length ? h('div', null, '材料：' + a.materials.map(function (m) { return m.name + (m.lot ? '/' + m.lot : '') + (m.state === 'expired' ? '（已过期）' : '（' + MF.fmt.date(m.expiry_at) + ' 到期）'); }).join('；')) : null,
            a.equipment.length ? h('div', null, '仪器：' + a.equipment.map(function (e) { return e.name + (e.state === 'overdue' ? '（校准过期）' : '（' + MF.fmt.date(e.calibration_due) + ' 校准到期）'); }).join('；')) : null));
        }
      } catch (e) { /* ignore */ }
    }
    async function load() {
      MF.clear(holder); holder.appendChild(MF.loading());
      var q = '?q=' + encodeURIComponent(qIn.value.trim()) + (showAll ? '&all=1' : '');
      try {
        if (tab === 'materials') {
          var rows = await api('GET', '/api/materials' + q + '&kind=' + encodeURIComponent(kindSel.value) + '&state=' + (stateSel.value === 'overdue' ? 'expired' : encodeURIComponent(stateSel.value)));
          MF.clear(holder);
          if (!rows.length) { holder.appendChild(h('div', { class: 'card empty' }, '没有材料记录。点“新增”登记试剂、参比品、标准品、耗材。')); return; }
          holder.appendChild(h('div', { class: 'card' }, h('div', { class: 'mt-tw' }, h('table', { class: 'table' },
            h('thead', null, h('tr', null, ['编号', '名称', '类别', '批号', '供应商/货号', '效期', '状态', ''].map(function (t) { return h('th', null, t); }))),
            h('tbody', null, rows.map(function (m) {
              return h('tr', { style: { opacity: m.active ? 1 : 0.55 } }, h('td', null, m.code), h('td', null, m.name, m.critical ? MF.badge('关键', 'warn') : null), h('td', null, m.kind_label), h('td', null, m.lot || '—'),
                h('td', { class: 'small' }, [m.supplier, m.catalog_no].filter(Boolean).join(' / ') || '—'), h('td', null, expiryChip(m.expiry_state, m.expiry_at)),
                h('td', null, MF.badge(m.status_label, m.status === 'active' ? 'ok' : 'warn'), m.active ? null : MF.badge('已停用', 'muted')),
                h('td', { style: { whiteSpace: 'nowrap' } }, canWrite() ? h('button', { class: 'btn btn-sm', type: 'button', onclick: function () { materialDialog(o, m).then(function (ok) { if (ok) { load(); drawAlerts(); } }); } }, '编辑') : null,
                  canAdmin() ? h('button', { class: 'btn btn-sm', type: 'button', style: { marginLeft: '4px' }, onclick: function () {
                    api('DELETE', '/api/materials/' + m.id + (m.active ? '' : '?restore=1')).then(function () { load(); drawAlerts(); }, function (e) { MF.toast(err(e), 'err'); });
                  } }, m.active ? '停用' : '恢复') : null));
            }))))));
        } else {
          var eq = await api('GET', '/api/equipment' + q + '&state=' + (stateSel.value === 'expired' ? 'overdue' : encodeURIComponent(stateSel.value)));
          MF.clear(holder);
          if (!eq.length) { holder.appendChild(h('div', { class: 'card empty' }, '没有仪器记录。点“新增”登记仪器及其校准到期日。')); return; }
          holder.appendChild(h('div', { class: 'card' }, h('div', { class: 'mt-tw' }, h('table', { class: 'table' },
            h('thead', null, h('tr', null, ['编号', '名称', '型号', '序列号/资产号', '位置', '校准到期', '状态', ''].map(function (t) { return h('th', null, t); }))),
            h('tbody', null, eq.map(function (q2) {
              return h('tr', { style: { opacity: q2.active ? 1 : 0.55 } }, h('td', null, q2.code), h('td', null, q2.name), h('td', null, q2.model || '—'), h('td', null, q2.serial_no || '—'), h('td', null, q2.location || '—'),
                h('td', null, calChip(q2.calibration_state, q2.calibration_due)), h('td', null, MF.badge(q2.status_label, q2.status === 'active' ? 'ok' : 'warn'), q2.active ? null : MF.badge('已停用', 'muted')),
                h('td', { style: { whiteSpace: 'nowrap' } }, canWrite() ? h('button', { class: 'btn btn-sm', type: 'button', onclick: function () { equipmentDialog(o, q2).then(function (ok) { if (ok) { load(); drawAlerts(); } }); } }, '编辑') : null,
                  canAdmin() ? h('button', { class: 'btn btn-sm', type: 'button', style: { marginLeft: '4px' }, onclick: function () {
                    api('DELETE', '/api/equipment/' + q2.id + (q2.active ? '' : '?restore=1')).then(function () { load(); drawAlerts(); }, function (e) { MF.toast(err(e), 'err'); });
                  } }, q2.active ? '停用' : '恢复') : null));
            }))))));
        }
      } catch (e) { MF.clear(holder); holder.appendChild(MF.errorBox(e, load)); }
    }
    c.appendChild(h('div', { class: 'page-head' }, h('div', null, h('h1', null, '台账：试剂 / 材料 与 仪器 / 设备'),
      h('p', null, '登记批号、效期、校准到期日。运行记录引用这里的条目：用了过期试剂或校准过期的仪器，会在记录上自动警示。')),
      canWrite() ? h('button', { class: 'btn btn-primary', type: 'button', onclick: function () {
        (tab === 'materials' ? materialDialog(o, null) : equipmentDialog(o, null)).then(function (ok) { if (ok) { MF.toast('已新增', 'ok'); load(); drawAlerts(); } });
      } }, '＋ 新增') : null));
    c.appendChild(alerts);
    c.appendChild(tabs);
    c.appendChild(h('div', { class: 'toolbar', style: { display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap', margin: '8px 0' } }, qIn, kindSel, stateSel,
      canAdmin() ? h('label', { class: 'small' }, allBox, ' 显示已停用') : null));
    c.appendChild(holder);
    var timer = null;
    qIn.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(load, 250); });
    kindSel.addEventListener('change', load); stateSel.addEventListener('change', load);
    allBox.addEventListener('change', function () { showAll = allBox.checked; load(); });
    drawTabs(); drawAlerts(); load();
  });

  // ------------------------------------------------------------------ audit-trail review
  MF.route('/audit-review', async function (params, c) {
    MF.setCrumbs([{ label: '管理', href: '/admin' }, { label: '审计追踪审核' }]);
    if (!canAdmin()) { c.appendChild(h('div', { class: 'card empty' }, '审计追踪审核仅管理员或批准人可用。')); return; }
    var data = await api('GET', '/api/audit-reviews');
    var st = data.status;
    var iso = function (d) { return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2); };
    c.appendChild(h('div', { class: 'page-head' }, h('div', null, h('h1', null, '审计追踪审核'),
      h('p', null, '法规要求定期审核审计追踪。这里记录谁在什么时候审核了哪段时间的审计追踪、校验了哈希链与签名完整性、结论如何；签署需要重新输入密码。')),
      h('button', { class: 'btn btn-primary', type: 'button', onclick: function () {
        var from = text(iso(new Date(Date.now() - 30 * 86400000)), '', 'date'), to = text(iso(new Date()), '', 'date');
        var scope = sel([{ key: 'all', label: '全部（整个系统）' }], 'all'), concl = sel([{ key: 'no_issue', label: '未发现异常' }, { key: 'issues_found', label: '发现异常' }], 'no_issue');
        var finds = h('textarea', { class: 'textarea', rows: 4, placeholder: '发现与处理（发现异常时必填）' });
        MF.modal({ title: '新建审计追踪审核记录', width: 600, body: h('div', null, h('div', { class: 'form-grid' }, MF.field('起始日期（UTC）', from), MF.field('截止日期（UTC）', to)), MF.field('范围', scope), MF.field('结论', concl), MF.field('发现与处理', finds),
          h('p', { class: 'small muted' }, '提交时系统会校验审计哈希链、锚点、触发器和全部已签署阶段的签名，并把结果与审核的条目数一起保存。')),
          buttons: [{ label: '取消', value: null }, { label: '签署并保存', kind: 'primary', onClick: async function (ctl) {
            var r = await MF.askSign({ title: '签署审计追踪审核', meaning: '我已审核 ' + from.value + ' 至 ' + to.value + ' 的审计追踪，结论：' + (concl.value === 'no_issue' ? '未发现异常' : '发现异常') + '。', needComment: false });
            if (!r) { ctl.setBusy(false); return false; }
            try { await api('POST', '/api/audit-reviews', { scope: scope.value, period_from: from.value, period_to: to.value, conclusion: concl.value, findings: finds.value, password: r.password }); ctl.close(true); }
            catch (e) { ctl.error(err(e)); ctl.setBusy(false); return false; }
          } }] }).then(function (ok) { if (ok) { MF.toast('审核记录已保存', 'ok'); MF.reload(); } });
      } }, '＋ 新建审核记录')));
    c.appendChild(h('div', { class: 'callout ' + (st.overdue ? 'callout-warn' : 'callout-ok') },
      st.last ? '上次审核：' + MF.fmt.datetime(st.last) + '（' + st.days_since + ' 天前）。' : '尚无审核记录。',
      st.interval_days ? ' 要求每 ' + st.interval_days + ' 天至少审核一次' + (st.overdue ? '，现已逾期。' : '。') : ' 未设置提醒周期（config.json 的 audit_review_days）。'));
    c.appendChild(h('div', { class: 'card' }, data.items.length ? h('div', { class: 'mt-tw' }, h('table', { class: 'table' },
      h('thead', null, h('tr', null, ['签署时间', '审核人', '期间', '范围', '条目数', '哈希链/签名', '结论', '发现与处理'].map(function (t) { return h('th', null, t); }))),
      h('tbody', null, data.items.map(function (r) {
        return h('tr', null, h('td', null, MF.fmt.datetime(r.signed_at)), h('td', null, r.reviewer_name), h('td', null, MF.fmt.date(r.period_from) + ' ~ ' + MF.fmt.date(r.period_to)),
          h('td', null, r.scope === 'all' ? '全部' : '方法 #' + r.method_id), h('td', null, String(r.entries_checked)), h('td', null, MF.badge(r.chain_ok ? '完好' : '异常', r.chain_ok ? 'ok' : 'err')),
          h('td', null, MF.badge(r.conclusion_label, r.conclusion === 'no_issue' ? 'ok' : 'warn')), h('td', { class: 'small' }, r.findings || '—'));
      })))) : h('div', { class: 'empty' }, '暂无审核记录。')));
  });

  // ------------------------------------------------------------------ search
  MF.route('/search', async function (params, c) {
    var q = (MF.query().q || '').trim();
    MF.setCrumbs([{ label: '搜索' }]);
    var input = h('input', { class: 'input', type: 'search', value: q, placeholder: '搜索项目、方法、实验、偏离、知识库、资源链接、材料…', style: { maxWidth: '480px' } });
    input.addEventListener('keydown', function (e) { if (e.key === 'Enter') MF.navigate('/search?q=' + encodeURIComponent(input.value.trim())); });
    c.appendChild(h('div', { class: 'page-head' }, h('div', null, h('h1', null, '全局搜索'), input)));
    if (q.length < 2) { c.appendChild(h('div', { class: 'card empty' }, '请输入至少 2 个字符，按回车搜索。')); return; }
    var res;
    try { res = await api('GET', '/api/search?q=' + encodeURIComponent(q)); } catch (e) { c.appendChild(MF.errorBox(e, MF.reload)); return; }
    var groups = [['projects', '项目', function (x) { return ['/pr/' + x.id, x.code + ' ' + x.title]; }], ['methods', '方法', function (x) { return ['/m/' + x.id, x.code + ' ' + x.title]; }],
      ['experiments', '实验', function (x) { return ['/m/' + x.method_id + '/exp/' + x.id, x.code + ' ' + x.title + '（' + x.method_code + '）']; }],
      ['deviations', '偏离', function (x) { return ['/m/' + x.method_id + '/deviations', x.code + ' ' + x.title + '（' + x.method_code + '）']; }],
      ['kb', '知识库', function (x) { return ['/kb?q=' + encodeURIComponent(q), x.title]; }],
      ['links', '资源链接', function (x) { return ['/kb/links?q=' + encodeURIComponent(q), (MF.lang === 'en' && x.title_en) ? x.title_en : x.title]; }],
      ['materials', '材料', function (x) { return ['/registry', x.code + ' ' + x.title]; }]];
    c.appendChild(h('p', { class: 'muted' }, '共 ' + res.total + ' 条结果'));
    groups.forEach(function (g) {
      var list = res[g[0]] || [];
      if (!list.length) return;
      c.appendChild(h('div', { class: 'card' }, h('h3', null, g[1] + '（' + list.length + '）'), h('ul', null, list.map(function (x) { var r = g[2](x); return h('li', null, h('a', { href: '#' + r[0] }, r[1])); }))));
    });
    if (!res.total) c.appendChild(h('div', { class: 'card empty' }, '没有找到与“' + q + '”相关的内容。'));
  });

  // ------------------------------------------------------------------ own e-mail
  MF.setMyEmail = function () {
    var u = MF.state.user || {};
    var em = h('input', { class: 'input', type: 'email', value: u.email || '', placeholder: 'name@example.org' });
    MF.modal({ title: '设置我的邮箱', width: 460, body: h('div', null, h('p', { class: 'small muted' }, '用于接收邮件通知（需管理员在 config.json 中配置 SMTP）；留空表示不接收。'), MF.field('邮箱', em)),
      buttons: [{ label: '取消', value: null }, { label: '保存', kind: 'primary', onClick: async function (ctl) {
        try { var r = await api('POST', '/api/me/email', { email: em.value.trim() }); u.email = r.email; ctl.close(true); } catch (e) { ctl.error(err(e)); ctl.setBusy(false); return false; }
      } }] }).then(function (ok) { if (ok) MF.toast('邮箱已保存', 'ok'); });
  };
})();
