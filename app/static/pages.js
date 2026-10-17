/* MethodFlow pages (API v2): dashboard, projects, project page, methods list, new project / new method,
   knowledge base, admin. Method-level views (/m/:mid...) live in method.js / stage.js. */
(function () {
  'use strict';
  var MF = window.MF;
  var h = MF.h;

  /* ---------------------------------------------------------------- shared helpers */
  var STAGE_TITLES = {
    charter: '立项与背景', atp: '分析目标概况（ATP）', tech: '技术选择与试剂策略', risk: '风险评估（FMEA）', plan: '开发方案与实验设计',
    explore: '可行性与优化实验', robust: '稳健性、稳定性与参数范围', control: '参比品与控制策略', report: '预验证与开发报告'
  };
  var ALL_ROLES = ['admin', 'author', 'reviewer', 'approver', 'viewer'];
  var ROLE_HINT = {
    admin: '管理用户、备份、系统设置，查看全部项目与方法', author: '新建项目 / 方法、编辑内容', reviewer: '可被指定为方法复核人', approver: '可被指定为方法批准人（QA）、停用知识条目', viewer: '仅查看'
  };
  var PROJECT_STATUS_OPTS = [['active', '进行中'], ['paused', '暂停'], ['completed', '完成'], ['archived', '归档']];
  var METHOD_STATUS_OPTS = [['active', '进行中'], ['completed', '完成'], ['archived', '归档'], ['cancelled', '取消']];
  var LIFECYCLE_OPTS = [['development', '开发'], ['validation', '验证'], ['transfer', '转移'], ['routine', '常规使用'], ['retired', '停用']];
  var PHASE_OPTS = ['', '临床前', '临床 I 期', '临床 II 期', '临床 III 期 / 关键研究', '商业化'];

  /* user-written names are shown as written in both languages */
  function nt(t) { return t ? h('span', { 'data-notranslate': '1' }, t) : ''; }
  function str(v) { return v === null || v === undefined || (typeof v === 'number' && !isFinite(v)) ? '' : String(v); }
  function dash(v) { var s = str(v); return s === '' ? '—' : s; }
  function todayStr() { var d = new Date(); return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2); }
  function link(text, href, cls) { return h('a', { href: '#' + href, class: cls || null }, text); }
  function empty(text) { return h('div', { class: 'empty' }, text); }
  function cardWith(title, extra, body) {
    return h('div', { class: 'card' }, h('div', { class: 'card-h' }, h('h3', null, title), h('span', { class: 'spacer' }), extra || null), body);
  }
  function fail(e) { if (e && e.status === 401) return; MF.toast((e && e.message) || '操作失败', 'err'); }
  function joinNames(list, n) {
    list = list || [];
    n = n || 2;
    var shown = list.slice(0, n).map(str).join('、');
    return list.length > n ? shown + ' 等' + list.length + '项' : shown;
  }
  function roleBadges(roles) {
    return (roles || []).map(function (r) { return MF.badge(MF.roleLabel(r), r === 'admin' ? 'warn' : 'muted'); }).reduce(function (a, b) { a.push(b, ' '); return a; }, []);
  }
  function requireLoginRole(c, roles, msg) {
    if (MF.hasRole.apply(null, roles)) return true;
    c.appendChild(h('div', { class: 'callout callout-warn' }, msg));
    return false;
  }
  function th(list) { return h('thead', null, h('tr', null, list.map(function (t) { return h('th', null, t); }))); }
  function intOrNull(v) { var n = parseInt(v, 10); return isFinite(n) ? n : null; }
  function debounce(fn, ms) { var t = null; return function () { clearTimeout(t); t = setTimeout(fn, ms); }; }
  function sel(options, value, extra) {
    var s = h('select', { class: 'select', style: { width: 'auto' } }, options.map(function (o) { return h('option', { value: o[0] }, o[1]); }));
    s.value = value === null || value === undefined ? '' : String(value);
    if (s.selectedIndex < 0) s.selectedIndex = 0;
    return s;
  }
  function riskBadges(row) {
    var out = [];
    if (row.overdue && row.overdue.length) out.push(h('span', { class: 'badge badge-err', title: row.overdue.join('、') }, '逾期 ' + row.overdue.length), ' ');
    if (row.stale && row.stale.length) out.push(h('span', { class: 'badge badge-warn', title: row.stale.join('、') }, '失效 ' + row.stale.length), ' ');
    if (row.signatures_ok === false) out.push(h('span', { class: 'badge badge-err', title: '已签署阶段的电子签名与内容不一致' }, '完整性校验失败'));
    return out;
  }
  function stage(cur, active) {
    if (cur && cur.title) return [str(cur.title), ' ', MF.statusBadge(cur.status, null, false)];
    return active ? '全部阶段已完成' : '—';
  }
  function progressCell(p) { return h('div', { class: 'progress-line' }, MF.progressBar(p), h('span', { class: 'pct' }, MF.fmt.pct(p))); }

  /* a modal asking for a reason (and optionally the current password) */
  function reasonDialog(o) {
    var reason = h('textarea', { class: 'textarea', rows: 3, placeholder: o.reasonLabel || '原因' });
    var pw = h('input', { class: 'input', type: 'password', autocomplete: 'current-password' });
    return MF.modal({
      title: o.title, width: 480,
      body: h('div', null, o.meaning ? h('div', { class: 'callout' }, o.meaning) : null,
        MF.field(o.reasonLabel || '原因', reason, { required: true }),
        o.password ? MF.field('当前账号密码（重新认证）', pw, { required: true }) : null),
      buttons: [{ label: '取消', value: null }, {
        label: o.okLabel || '确认', kind: o.danger ? 'danger' : 'primary',
        onClick: function (ctl) {
          if (!reason.value.trim()) { ctl.error('请填写' + (o.reasonLabel || '原因')); return false; }
          if (o.password && !pw.value) { ctl.error('请输入密码以重新认证'); return false; }
          ctl.close({ reason: reason.value.trim(), password: pw.value });
          return false;
        }
      }]
    });
  }

  /* checkbox list of users with mutual exclusion */
  function userPicker(users, onChange) {
    var boxes = [];
    var list = h('div', { class: 'picker' });
    if (!users.length) list.appendChild(h('div', { class: 'hint', style: { padding: '8px' } }, '（无可选成员）'));
    users.forEach(function (u) {
      var cb = h('input', { type: 'checkbox', value: String(u.id), onchange: onChange });
      var lab = h('label', null, cb, h('span', null, str(u.display_name) || str(u.username)), h('span', { class: 'small muted' }, '@' + str(u.username)));
      boxes.push({ uid: u.id, cb: cb, lab: lab });
      list.appendChild(lab);
    });
    return {
      el: list,
      count: users.length,
      values: function () { return boxes.filter(function (b) { return b.cb.checked; }).map(function (b) { return b.uid; }); },
      lock: function (taken) {
        boxes.forEach(function (b) {
          var off = !b.cb.checked && taken.indexOf(b.uid) >= 0;
          b.cb.disabled = off;
          b.lab.classList.toggle('off', off);
          b.lab.title = off ? '该用户已被选为其他角色（同一人不能兼任）' : '';
        });
      }
    };
  }

  /* project team editor: one row per user with a role select.  current: {uid: role} */
  function teamEditor(users, current, opts) {
    opts = opts || {};
    var rows = [];
    var body = h('tbody');
    users.forEach(function (u) {
      var canOwn = (u.roles || []).indexOf('author') >= 0 || (u.roles || []).indexOf('admin') >= 0;
      var s = h('select', { class: 'select', style: { width: 'auto', minWidth: '130px' }, 'aria-label': '项目角色：' + str(u.display_name) },
        h('option', { value: '' }, '不加入'),
        canOwn ? h('option', { value: 'owner' }, '项目负责人') : null,
        h('option', { value: 'member' }, '项目成员'),
        h('option', { value: 'viewer' }, '只读成员'));
      s.value = current[u.id] || '';
      if (s.selectedIndex < 0) s.selectedIndex = 0;
      if (opts.onChange) s.addEventListener('change', opts.onChange);
      rows.push({ uid: u.id, sel: s });
      body.appendChild(h('tr', { class: u.active ? '' : 'row-warn' },
        h('td', null, str(u.display_name) || str(u.username), u.active ? null : [' ', MF.badge('已停用', 'muted')]),
        h('td', { class: 'mono small' }, str(u.username)),
        h('td', null, roleBadges(u.roles)),
        h('td', null, s)));
    });
    var el = users.length ? h('div', { class: 'table-wrap' }, h('table', { class: 'table' }, th(['姓名', '账号', '系统角色', '项目角色']), body)) : empty('暂无可选用户');
    return {
      el: el,
      get: function () {
        return rows.filter(function (r) { return r.sel.value; }).map(function (r) { return { user_id: r.uid, role: r.sel.value }; });
      }
    };
  }

  /* methods table (project page and methods list) */
  function methodsTable(rows, opts) {
    opts = opts || {};
    var heads = ['编号', '名称'];
    if (opts.showProject) heads.push('所属项目');
    heads = heads.concat(['技术', '生命周期', '状态', '进度', '当前阶段', '提示', '负责人']);
    return h('div', { class: 'table-wrap' }, h('table', { class: 'table' }, th(heads),
      h('tbody', null, rows.map(function (m) {
        return h('tr', { class: 'row-link', onclick: function (e) { if (e.target.tagName !== 'A') MF.navigate('/m/' + m.id); } },
          h('td', { class: 'mono nowrap' }, str(m.code)),
          h('td', null, h('a', { href: '#/m/' + m.id, class: 'strong' }, nt(str(m.name)) || '（未命名方法）')),
          opts.showProject ? h('td', null, m.project_id ? [link(str(m.project_code), '/pr/' + m.project_id, 'mono nowrap'), h('div', { class: 'small muted' }, nt(str(m.project_name)))] : '—') : null,
          h('td', { title: str(m.technique_label), style: { minWidth: '96px' } }, dash(str(m.technique_label).split(/[（(]/)[0].trim() || m.technique), m.template_version ? h('span', { class: 'small muted' }, ' v' + str(m.template_version)) : null),
          h('td', null, MF.lifecycleBadge(m.lifecycle, m.lifecycle_label)),
          h('td', null, MF.methodStatusBadge(m.status, m.status_label)),
          h('td', { style: { minWidth: '110px' } }, progressCell(m.progress)),
          h('td', null, stage(m.current_stage, m.status === 'active')),
          h('td', null, riskBadges(m)),
          h('td', { class: 'nowrap' }, dash(m.owner_name)));
      }))));
  }

  /* ---------------------------------------------------------------- cards */
  function projectCard(p) {
    var warnings = [];
    if (p.overdue && p.overdue.length) warnings.push(h('span', { class: 'badge badge-err', title: p.overdue.join('、') }, '逾期：' + joinNames(p.overdue)));
    if (p.stale && p.stale.length) warnings.push(h('span', { class: 'badge badge-warn', title: p.stale.join('、') }, '失效：' + joinNames(p.stale)));
    return h('a', { class: 'card link-card pcard', href: '#/pr/' + p.id },
      h('div', { class: 'row', style: { gap: '8px' } }, h('span', { class: 'small muted mono' }, str(p.code)), MF.projectStatusBadge(p.status, p.status_label), h('span', { class: 'spacer' }),
        (p.my_roles || []).slice(0, 2).map(function (r) { return MF.badge(MF.roleLabel(r, 'project'), 'muted'); })),
      h('div', { class: 'title' }, nt(str(p.name)) || '（未命名项目）'),
      h('div', { class: 'small muted' }, str(p.product)),
      h('div', { class: 'progress-line' }, MF.progressBar(p.progress), h('span', { class: 'pct' }, MF.fmt.pct(p.progress))),
      h('div', { class: 'small' }, '方法 ' + (Number(p.method_count) || 0) + ' 个'),
      warnings.length ? h('div', { class: 'row', style: { gap: '6px' } }, warnings) : null,
      h('div', { class: 'small muted' }, '计划完成：' + MF.fmt.date(p.planned_end)));
  }

  function methodCard(m) {
    var warnings = [];
    if (m.overdue && m.overdue.length) warnings.push(h('span', { class: 'badge badge-err', title: m.overdue.join('、') }, '逾期：' + joinNames(m.overdue, 1)));
    if (m.stale && m.stale.length) warnings.push(h('span', { class: 'badge badge-warn', title: m.stale.join('、') }, '失效：' + joinNames(m.stale, 1)));
    return h('a', { class: 'card link-card pcard', href: '#/m/' + m.id },
      h('div', { class: 'row', style: { gap: '8px' } }, h('span', { class: 'small muted mono' }, str(m.code)), MF.lifecycleBadge(m.lifecycle, m.lifecycle_label),
        MF.methodStatusBadge(m.status, m.status_label), h('span', { class: 'spacer' }),
        (m.my_roles || []).slice(0, 2).map(function (r) { return MF.badge(MF.roleLabel(r, 'method'), 'muted'); })),
      h('div', { class: 'title' }, nt(str(m.name)) || '（未命名方法）'),
      h('div', { class: 'small muted' }, str(m.project_code), m.project_name ? ' · ' : '', nt(str(m.project_name)), m.technique_label ? ' · ' + str(m.technique_label) : ''),
      h('div', { class: 'progress-line' }, MF.progressBar(m.progress), h('span', { class: 'pct' }, MF.fmt.pct(m.progress))),
      h('div', { class: 'small' }, m.current_stage ? ['当前阶段：'].concat(stage(m.current_stage, true)) : (m.status === 'active' ? '全部阶段已完成' : '')),
      warnings.length ? h('div', { class: 'row', style: { gap: '6px' } }, warnings) : null);
  }

  function stat(n, label, color) {
    return h('div', { class: 'stat' }, h('div', { class: 'n', style: color ? { color: color } : null }, String(n)), h('div', { class: 'l' }, label));
  }

  /* ---------------------------------------------------------------- dashboard */
  MF.route('/', async function (params, c) {
    MF.setCrumbs([{ label: '工作台' }]);
    var d = await MF.api('GET', '/api/dashboard');
    var user = MF.state.user || {};
    var toReview = d.to_review || [], mine = d.my_stages || [], exps = d.my_experiments || [], projects = d.projects || [], methods = d.methods || [];
    var overdueN = mine.filter(function (x) { return x.overdue; }).length + exps.filter(function (x) { return x.overdue; }).length;
    var activeMethods = methods.filter(function (m) { return m.status === 'active'; });
    var activeProjects = projects.filter(function (p) { return p.status === 'active'; });

    c.appendChild(h('div', { class: 'page-head' },
      h('div', null, h('h1', null, '工作台'), h('p', null, '你好，' + (user.display_name || user.username || '') + '。以下是需要你处理的事项。')),
      h('span', { class: 'spacer' }),
      MF.hasRole('author', 'admin') ? h('a', { class: 'btn', href: '#/projects/new' }, '＋ 新建项目') : null,
      MF.hasRole('author', 'admin') && projects.length ? h('a', { class: 'btn btn-primary', href: '#/methods/new' }, '＋ 新增方法') : null));

    c.appendChild(h('div', { class: 'stat-row' },
      stat(toReview.length, '待我复核 / 处理', toReview.length ? 'var(--c-info)' : null),
      stat(mine.length, '我负责的阶段'),
      stat(overdueN, '已逾期事项', overdueN ? 'var(--c-err)' : null),
      stat(exps.length, '我的进行中实验'),
      stat(activeMethods.length, '进行中的方法'),
      stat(activeProjects.length, '进行中的项目')));

    function methodLink(x, suffix) { return '/m/' + x.method_id + suffix; }
    var reviewBody = toReview.length ? h('ul', { class: 'list' }, toReview.map(function (t) {
      var stale = t.role === 'stale';
      return h('li', null,
        h('div', { class: 'grow' }, h('a', { href: '#' + methodLink(t, '/stage/' + encodeURIComponent(str(t.stage_key))) }, str(t.stage)),
          h('div', { class: 'small muted' }, str(t.method_code) + ' ' + str(t.method) + (t.project_code ? ' · ' + str(t.project_code) : ''))),
        stale ? MF.badge('已失效，需重新提交复核', 'warn') : MF.badge('待你以' + (str(t.role_label) || MF.roleLabel(t.role)) + '身份复核', 'info'));
    })) : empty('暂无待复核事项');
    var mineBody = mine.length ? h('ul', { class: 'list' }, mine.map(function (s) {
      return h('li', null,
        h('div', { class: 'grow' }, h('a', { href: '#' + methodLink(s, '/stage/' + encodeURIComponent(str(s.stage_key))) }, str(s.stage)),
          h('div', { class: 'small muted' }, str(s.method_code) + ' ' + str(s.method) + (s.project_code ? ' · ' + str(s.project_code) : ''))),
        MF.statusBadge(s.status, s.status_label, false),
        h('span', { class: 'small nowrap ' + (s.overdue ? 'overdue' : 'muted') }, (s.overdue ? '已逾期 ' : '计划 ') + MF.fmt.date(s.planned_end)));
    })) : empty('暂无进行中的阶段');
    c.appendChild(h('div', { class: 'grid-2', style: { marginBottom: '16px' } },
      cardWith('待我复核 / 处理', toReview.length ? MF.badge(String(toReview.length), 'info') : null, reviewBody),
      cardWith('我负责的阶段', mine.length ? MF.badge(String(mine.length), 'muted') : null, mineBody)));

    var expHolder = h('div');
    var expAll = false;
    var EXP_MAX = 8;
    function drawExps() {
      MF.clear(expHolder);
      if (!exps.length) { expHolder.appendChild(empty('暂无分配给你的进行中实验')); return; }
      var rows = expAll ? exps : exps.slice(0, EXP_MAX);
      expHolder.appendChild(h('div', { class: 'table-wrap' }, h('table', { class: 'table' },
        th(['实验', '方法', '状态', '计划完成']),
        h('tbody', null, rows.map(function (e) {
          return h('tr', null,
            h('td', null, h('a', { href: '#/m/' + e.method_id + '/exp/' + e.id }, (str(e.code) ? str(e.code) + ' ' : '') + str(e.title))),
            h('td', null, str(e.method_code) + ' ' + str(e.method)),
            h('td', null, MF.badge(e.status_label || str(e.status) || '—', e.status === 'running' ? 'warn' : 'muted')),
            h('td', { class: e.overdue ? 'overdue' : '' }, (e.overdue ? '已逾期 ' : '') + MF.fmt.date(e.planned_end)));
        })))));
      if (exps.length > EXP_MAX) expHolder.appendChild(h('div', { style: { textAlign: 'center', marginTop: '8px' } },
        h('button', { class: 'btn btn-sm', type: 'button', onclick: function () { expAll = !expAll; drawExps(); } }, expAll ? '收起' : '显示全部 ' + exps.length + ' 项')));
    }
    drawExps();
    c.appendChild(cardWith('我的实验', exps.length ? MF.badge(String(exps.length), 'muted') : null, expHolder));

    c.appendChild(h('div', { class: 'row', style: { margin: '8px 0 12px' } }, h('h2', { style: { margin: 0 } }, '项目'), h('span', { class: 'spacer' }),
      link('查看全部项目 →', '/projects')));
    var showP = projects.slice(0, 6);
    c.appendChild(showP.length ? h('div', { class: 'grid', style: { marginBottom: '16px' } }, showP.map(projectCard)) :
      h('div', { class: 'card empty' }, '还没有项目。', MF.hasRole('author', 'admin') ? [' ', link('新建第一个项目', '/projects/new')] : '请联系项目负责人将你加入项目。'));

    c.appendChild(h('div', { class: 'row', style: { margin: '8px 0 12px' } }, h('h2', { style: { margin: 0 } }, '方法'), h('span', { class: 'spacer' }),
      link('查看全部方法 →', '/methods')));
    var showM = methods.slice(0, 12);
    c.appendChild(showM.length ? h('div', { class: 'grid' }, showM.map(methodCard)) :
      h('div', { class: 'card empty' }, '还没有可见的方法。' + (projects.length ? '可在项目页中“新增方法”。' : '')));
  });

  /* ---------------------------------------------------------------- project list */
  MF.route('/projects', async function (params, c) {
    MF.setCrumbs([{ label: '项目' }]);
    var q = h('input', { class: 'input', style: { maxWidth: '280px' }, placeholder: '搜索编号、名称、产品、适应症', type: 'search' });
    var st = sel([['', '全部状态']].concat(PROJECT_STATUS_OPTS), '');
    var count = h('span', { class: 'muted small' });
    var holder = h('div');
    var seq = 0, anyEver = false;
    async function load() {
      var my = ++seq;
      var rows;
      try { rows = await MF.api('GET', '/api/projects' + MF.qs({ q: q.value.trim(), status: st.value })); } catch (e) { fail(e); return; }
      if (my !== seq) return;
      if (rows.length) anyEver = true;
      count.textContent = '共 ' + rows.length + ' 个项目';
      MF.clear(holder);
      if (!rows.length) { holder.appendChild(empty(q.value.trim() || st.value ? '没有符合条件的项目' : '还没有项目')); return; }
      holder.appendChild(h('div', { class: 'table-wrap' }, h('table', { class: 'table' },
        th(['编号', '名称', '产品', '适应症 / 阶段', '负责人', '方法', '进度', '状态', '计划完成', '提示']),
        h('tbody', null, rows.map(function (p) {
          return h('tr', { class: 'row-link', onclick: function (e) { if (e.target.tagName !== 'A') MF.navigate('/pr/' + p.id); } },
            h('td', { class: 'mono nowrap' }, str(p.code)),
            h('td', null, h('a', { href: '#/pr/' + p.id, class: 'strong' }, nt(str(p.name)) || '（未命名项目）')),
            h('td', null, dash(p.product)),
            h('td', null, [str(p.indication), str(p.indication) && str(p.phase) ? ' / ' : '', str(p.phase)].join('') || '—'),
            h('td', { class: 'nowrap' }, dash(p.owner_name)),
            h('td', { class: 'num' }, String(Number(p.method_count) || 0)),
            h('td', { style: { minWidth: '110px' } }, progressCell(p.progress)),
            h('td', null, MF.projectStatusBadge(p.status, p.status_label)),
            h('td', { class: 'nowrap' }, MF.fmt.date(p.planned_end)),
            h('td', null, riskBadges(p)));
        })))));
    }
    var reload = debounce(load, 250);
    q.addEventListener('input', reload);
    st.addEventListener('change', load);
    c.appendChild(h('div', { class: 'page-head' }, h('h1', null, '项目'), h('span', { class: 'spacer' }),
      MF.hasRole('author', 'admin') ? h('a', { class: 'btn btn-primary', href: '#/projects/new' }, '＋ 新建项目') : null));
    c.appendChild(h('div', { class: 'toolbar' }, q, st, count));
    c.appendChild(h('div', { class: 'card', style: { padding: '4px 8px' } }, holder));
    await load();
  });

  /* ---------------------------------------------------------------- new project */
  MF.route('/projects/new', async function (params, c) {
    MF.setCrumbs([{ label: '项目', href: '/projects' }, { label: '新建项目' }]);
    c.appendChild(h('div', { class: 'page-head' }, h('div', null, h('h1', null, '新建项目'),
      h('p', null, '项目是产品 / 管线层面的容器，下面可以包含多个分析方法。方法在项目创建后再新增。'))));
    if (!requireLoginRole(c, ['author', 'admin'], '仅“开发人员”或管理员可以新建项目。')) return;
    var me = MF.state.user || {};
    var all = await MF.api('GET', '/api/users');
    var users = (all || []).filter(function (u) { return u.active && u.id !== me.id; });

    var name = h('input', { class: 'input', maxlength: 200, placeholder: '例如：XX-CAR-T 分析方法包' });
    var product = h('input', { class: 'input', placeholder: '产品，例如：CD19 CAR-T 细胞制剂' });
    var indication = h('input', { class: 'input', placeholder: '适应症，例如：复发 / 难治性 B 细胞淋巴瘤' });
    var phase = h('select', { class: 'select' }, PHASE_OPTS.map(function (x) { return h('option', { value: x }, x || '（未指定）'); }));
    var desc = h('textarea', { class: 'textarea', rows: 3, placeholder: '项目背景与范围（可选）' });
    var start = h('input', { class: 'input', type: 'date', value: todayStr() });
    var end = h('input', { class: 'input', type: 'date' });
    var team = teamEditor(users, {});
    var errBox = h('div', { class: 'callout callout-err', hidden: true, role: 'alert' });
    var submit = h('button', { class: 'btn btn-primary', type: 'submit' }, '创建项目');
    var hasReviewer = users.some(function (u) { return u.roles.indexOf('reviewer') >= 0; });
    var hasApprover = users.some(function (u) { return u.roles.indexOf('approver') >= 0; });

    var form = h('form', { novalidate: true, onsubmit: async function (ev) {
      ev.preventDefault();
      errBox.hidden = true;
      if (!name.value.trim()) { errBox.textContent = '请填写项目名称'; errBox.hidden = false; name.focus(); return; }
      if (start.value && end.value && end.value < start.value) { errBox.textContent = '计划结束日期不能早于开始日期'; errBox.hidden = false; return; }
      submit.disabled = true;
      try {
        var body = { name: name.value.trim(), product: product.value.trim(), indication: indication.value.trim(), phase: phase.value, description: desc.value.trim(), members: team.get() };
        if (start.value) body.planned_start = start.value;
        if (end.value) body.planned_end = end.value;
        var r = await MF.api('POST', '/api/projects', body);
        MF.dirtyGuard.set(false);
        MF.toast('项目已创建', 'ok');
        MF.navigate('/pr/' + r.id);
      } catch (e) {
        submit.disabled = false;
        if (e.status === 401) return;
        errBox.textContent = e.message || '创建失败'; errBox.hidden = false;
      }
    } },
      h('div', { class: 'card' }, h('h3', null, '1. 项目信息'),
        h('div', { class: 'form-grid' },
          h('div', { class: 'span2' }, MF.field('项目名称', name, { required: true })),
          MF.field('产品', product), MF.field('适应症', indication),
          MF.field('研发阶段', phase), h('div'),
          MF.field('计划开始日期', start), MF.field('计划结束日期', end),
          h('div', { class: 'span2' }, MF.field('说明', desc)))),
      h('div', { class: 'card' }, h('h3', null, '2. 项目团队'),
        h('div', { class: 'callout' }, '您（创建人）自动成为“项目负责人”。方法团队只能从项目团队中选择，所以请把将来要参与方法开发、复核、批准的人先加进来；项目成员可新增方法，只读成员仅可查看。'),
        !hasReviewer || !hasApprover ? h('div', { class: 'callout callout-warn' },
          (!hasReviewer ? '系统中暂无其他具备“复核人”角色的用户。' : '') + (!hasApprover ? '系统中暂无其他具备“批准人”角色的用户。' : '') +
          (MF.hasRole('admin') ? '请先到“管理”中创建用户或授予角色，再回来加入项目团队（也可以创建项目后再调整）。' : '请联系管理员创建或授权，之后项目负责人可在项目页调整团队。')) : null,
        team.el,
        h('p', { class: 'hint' }, '“项目负责人”须具备“开发人员”或管理员角色。创建后，项目负责人可随时在项目页调整团队；仍在某个方法团队中的人不能被移出项目。')),
      errBox,
      h('div', { class: 'row' }, submit, h('a', { class: 'btn', href: '#/projects' }, '取消')));
    form.addEventListener('input', function () { MF.dirtyGuard.set(true); });
    form.addEventListener('change', function () { MF.dirtyGuard.set(true); });
    c.appendChild(form);
  });

  /* ---------------------------------------------------------------- audit table (shared) */
  var ACTION_LABELS = {
    'login': '登录', 'login.fail': '登录失败', 'logout': '退出登录', 'user.create': '创建用户', 'user.update': '更新用户', 'user.password_change': '修改密码',
    'user.password_reset': '重置密码', 'user.password_check_fail': '原密码校验失败', 'signature.auth_fail': '签名认证失败',
    'project.create': '创建项目', 'project.update': '修改项目', 'project.members': '调整项目团队',
    'method.create': '创建方法', 'method.clone': '克隆方法', 'method.update': '修改方法', 'method.members': '调整方法团队', 'method.lifecycle': '变更生命周期',
    'stage.save': '保存阶段', 'stage.submit': '提交复核', 'stage.complete': '阶段完成', 'stage.withdraw': '撤回提交', 'stage.reject': '退回',
    'stage.sign': '电子签名', 'stage.approved': '阶段通过', 'stage.reopen': '重新打开', 'stage.recertify': '重新确认', 'experiment.create': '创建实验', 'experiment.update': '更新实验',
    'experiment.status': '实验状态变更', 'experiment.delete': '删除实验', 'attachment.add': '上传附件', 'attachment.delete': '删除附件', 'kb.create': '新增知识',
    'kb.deactivate': '停用知识', 'kb.lesson': '沉淀经验', 'kb.sync': '同步内置知识库', 'document.generate': '生成文档', 'backup.manual': '手动备份',
    'schema.migrate': '数据库结构迁移', 'settings.update': '修改文档设置', 'admin.settings': '修改文档设置'
  };
  MF.actionLabel = function (a) { return ACTION_LABELS[a] || ''; };

  function auditTable(rows, opts) {
    opts = opts || {};
    var filter = h('input', { class: 'input', type: 'search', style: { maxWidth: '260px' }, placeholder: '筛选用户、操作、对象、方法、原因' });
    var holder = h('div');
    function target(r) {
      if (r.method_id) return link(str(r.method_code) || ('方法#' + r.method_id), '/m/' + r.method_id, 'mono nowrap');
      if (r.project_id) return link('项目#' + r.project_id, '/pr/' + r.project_id, 'nowrap');
      return '—';
    }
    function draw() {
      var kw = filter.value.trim().toLowerCase();
      var list = rows.filter(function (r) {
        if (!kw) return true;
        var hay = [r.username, r.action, ACTION_LABELS[r.action], r.entity_type, r.entity_id, r.reason, r.method_code].map(str).join(' ').toLowerCase();
        return hay.indexOf(kw) >= 0;
      });
      MF.clear(holder);
      if (!list.length) { holder.appendChild(empty(rows.length ? '没有符合条件的记录' : '暂无审计记录')); return; }
      holder.appendChild(h('div', { class: 'table-wrap' }, h('table', { class: 'table' },
        th(['#', '时间', '用户', '操作', '对象', '方法 / 项目', '原因', '详情']),
        h('tbody', null, list.map(function (r) {
          var det = r.details && typeof r.details === 'object' ? r.details : {};
          var hasDet = Object.keys(det).length > 0;
          var detRow = null;
          var tr = h('tr', null,
            h('td', { class: 'mono muted' }, str(r.id)),
            h('td', { class: 'nowrap' }, MF.fmt.datetime(r.ts)),
            h('td', null, str(r.username) || '—'),
            h('td', null, ACTION_LABELS[r.action] ? [ACTION_LABELS[r.action], h('div', { class: 'small muted mono' }, str(r.action))] : h('span', { class: 'mono' }, str(r.action))),
            h('td', { class: 'small' }, r.entity_type ? str(r.entity_type) + (r.entity_id !== null && r.entity_id !== undefined ? ' #' + str(r.entity_id) : '') : '—'),
            h('td', null, target(r)),
            h('td', { class: 'small' }, str(r.reason) || '—'),
            h('td', null, hasDet ? h('button', { class: 'btn btn-sm', type: 'button', onclick: function () {
              if (detRow) { detRow.remove(); detRow = null; return; }
              detRow = h('tr', null, h('td', { colspan: 8 }, h('pre', { class: 'details-pre' }, JSON.stringify(det, null, 2)),
                h('div', { class: 'small muted mono', style: { marginTop: '4px', wordBreak: 'break-all' } }, '哈希：' + str(r.hash))));
              tr.parentNode.insertBefore(detRow, tr.nextSibling);
            } }, '详情') : h('span', { class: 'muted' }, '—')));
          return tr;
        })))));
    }
    filter.addEventListener('input', draw);
    draw();
    return { toolbar: h('div', { class: 'toolbar' }, h('h3', { style: { margin: 0 } }, opts.title || '审计追踪'), h('span', { class: 'muted small' }, '（最近 ' + rows.length + ' 条）'), h('span', { class: 'spacer' }), filter),
      body: h('div', { class: 'card', style: { padding: '4px 8px' } }, holder) };
  }

  /* ---------------------------------------------------------------- project page */
  MF.route('/pr/:pid', async function (params, c) {
    var pid = params.pid;
    var res = await Promise.all([MF.api('GET', '/api/projects/' + encodeURIComponent(pid)), MF.api('GET', '/api/projects/' + encodeURIComponent(pid) + '/methods')]);
    var p = res[0], methods = res[1] || [];
    var perm = p.permissions || {};
    MF.setCrumbs([{ label: '项目', href: '/projects' }, { label: str(p.code) }, { label: str(p.name) }]);
    var tab = 'overview';
    var tabBar = h('div', { class: 'tabs', role: 'tablist' });
    var content = h('div');
    var auditLoaded = null;

    async function patch(body, okMsg) {
      try { await MF.api('PATCH', '/api/projects/' + p.id, body); MF.toast(okMsg || '已保存', 'ok'); MF.reload(); return true; } catch (e) { fail(e); return false; }
    }

    function editInfo() {
      var name = h('input', { class: 'input', maxlength: 200, value: str(p.name) });
      var product = h('input', { class: 'input', value: str(p.product) });
      var indication = h('input', { class: 'input', value: str(p.indication) });
      var phase = h('select', { class: 'select' }, PHASE_OPTS.concat(PHASE_OPTS.indexOf(str(p.phase)) < 0 && str(p.phase) ? [str(p.phase)] : []).map(function (x) { return h('option', { value: x }, x || '（未指定）'); }));
      phase.value = str(p.phase);
      var desc = h('textarea', { class: 'textarea', rows: 3 }); desc.value = str(p.description);
      var start = h('input', { class: 'input', type: 'date', value: str(p.planned_start) });
      var end = h('input', { class: 'input', type: 'date', value: str(p.planned_end) });
      return MF.modal({
        title: '编辑项目信息', width: 620,
        body: h('div', null,
          h('div', { class: 'form-grid' },
            h('div', { class: 'span2' }, MF.field('项目名称', name, { required: true })),
            MF.field('产品', product, { hint: '项目下任一方法的任一阶段批准后，产品不可再修改。' }), MF.field('适应症', indication),
            MF.field('研发阶段', phase), h('div'),
            MF.field('计划开始日期', start), MF.field('计划结束日期', end),
            h('div', { class: 'span2' }, MF.field('说明', desc)))),
        buttons: [{ label: '取消', value: null }, {
          label: '保存', kind: 'primary', value: true,
          onClick: function (ctl) {
            if (!name.value.trim()) { ctl.error('项目名称不能为空'); return false; }
            if (start.value && end.value && end.value < start.value) { ctl.error('计划结束日期不能早于开始日期'); return false; }
            var body = {};
            [['name', name.value.trim(), p.name], ['product', product.value.trim(), p.product], ['indication', indication.value.trim(), p.indication],
              ['phase', phase.value, p.phase], ['description', desc.value.trim(), p.description]].forEach(function (x) { if (x[1] !== str(x[2])) body[x[0]] = x[1]; });
            if (start.value !== str(p.planned_start) && start.value) body.planned_start = start.value;
            if (end.value !== str(p.planned_end) && end.value) body.planned_end = end.value;
            if (!Object.keys(body).length) { ctl.error('没有修改任何内容'); return false; }
            return MF.api('PATCH', '/api/projects/' + p.id, body);
          }
        }]
      }).then(function (ok) { if (ok) { MF.toast('项目信息已保存', 'ok'); MF.reload(); } });
    }

    async function editTeam() {
      var all;
      try { all = await MF.api('GET', '/api/users'); } catch (e) { fail(e); return; }
      var cur = {};
      var byId = {};
      (p.members || []).forEach(function (m) { cur[m.user_id] = m.role; });
      all.forEach(function (u) { byId[u.id] = u; });
      var users = all.filter(function (u) { return u.active || cur[u.id]; });
      var te = teamEditor(users, cur);
      return MF.modal({
        title: '编辑项目团队', width: 720,
        body: h('div', null,
          h('div', { class: 'callout' }, '团队为整体替换：未选择“不加入”的用户即为项目成员。至少保留一名项目负责人；仍在某个方法团队里的人不能被移出项目（请先在对应方法中调整方法团队）。'),
          te.el),
        buttons: [{ label: '取消', value: null }, {
          label: '保存团队', kind: 'primary', value: true,
          onClick: function (ctl) {
            var members = te.get();
            if (!members.some(function (m) { return m.role === 'owner'; })) { ctl.error('至少需要一名项目负责人'); return false; }
            return MF.api('PUT', '/api/projects/' + p.id + '/members', { members: members });
          }
        }]
      }).then(function (ok) { if (ok) { MF.toast('项目团队已更新', 'ok'); MF.reload(); } });
    }

    async function changeStatus(to, label) {
      if (to === 'active') {
        var r = await reasonDialog({ title: '恢复项目为进行中', meaning: '将项目恢复为“进行中”会写入审计记录，须说明原因并输入当前账号密码重新认证。', reasonLabel: '恢复原因', password: true });
        if (!r) return;
        await patch({ status: 'active', reason: r.reason, password: r.password }, '项目已恢复为进行中');
        return;
      }
      var msg = to === 'paused' ? '暂停后，项目下所有方法暂不可修改（可随时恢复）。确定暂停该项目？'
        : to === 'completed' ? '标记完成要求项目下没有“进行中”的方法。确定将项目标记为完成？'
        : '归档后项目及其方法均不可修改。确定归档该项目？';
      if (!(await MF.confirm(msg, { okLabel: label, danger: to === 'archived' }))) return;
      await patch({ status: to }, '项目状态已更新');
    }

    var headBtns = [];
    if (perm.can_edit) headBtns.push(h('button', { class: 'btn', type: 'button', onclick: editInfo }, '编辑信息'));
    var statusBtns = [];
    if (perm.can_edit) {
      if (p.status === 'active') statusBtns.push(['paused', '暂停'], ['completed', '标记完成'], ['archived', '归档']);
      else if (p.status === 'paused') statusBtns.push(['active', '恢复进行'], ['completed', '标记完成'], ['archived', '归档']);
      else if (p.status === 'completed') statusBtns.push(['active', '重新打开'], ['archived', '归档']);
      else if (p.status === 'archived') statusBtns.push(['active', '恢复进行']);
    }
    statusBtns.forEach(function (s) { headBtns.push(h('button', { class: 'btn' + (s[0] === 'archived' ? '' : ''), type: 'button', onclick: function () { changeStatus(s[0], s[1]); } }, s[1])); });

    c.appendChild(h('div', { class: 'page-head' },
      h('div', null, h('div', { class: 'small muted mono' }, str(p.code)), h('h1', null, nt(str(p.name)) || '（未命名项目）')),
      MF.projectStatusBadge(p.status, p.status_label),
      h('span', { class: 'spacer' }), headBtns));
    if (p.status !== 'active') c.appendChild(h('div', { class: 'callout callout-warn' }, '项目当前为“' + (str(p.status_label) || '非进行中') + '”状态：项目及其下方法的内容均不可修改' + (perm.can_edit ? '，可通过上方按钮恢复。' : '。')));
    if (p.overdue && p.overdue.length) c.appendChild(h('div', { class: 'callout callout-warn' }, '含逾期阶段的方法：' + p.overdue.join('、')));
    if (p.stale && p.stale.length) c.appendChild(h('div', { class: 'callout callout-warn' }, '含已失效（需重新提交复核）阶段的方法：' + p.stale.join('、')));

    function overview(box) {
      box.appendChild(h('div', { class: 'card' }, h('h3', null, '项目信息'),
        h('dl', { class: 'kv' },
          h('dt', null, '产品'), h('dd', null, dash(p.product)),
          h('dt', null, '适应症'), h('dd', null, dash(p.indication)),
          h('dt', null, '研发阶段'), h('dd', null, dash(p.phase)),
          h('dt', null, '计划周期'), h('dd', null, MF.fmt.date(p.planned_start) + ' ～ ' + MF.fmt.date(p.planned_end)),
          h('dt', null, '项目负责人'), h('dd', null, dash(p.owner_name)),
          h('dt', null, '我的项目角色'), h('dd', null, (p.my_roles || []).length ? (p.my_roles || []).map(function (r) { return MF.roleLabel(r, 'project'); }).join('、') : (MF.hasRole('admin') ? '管理员（非项目成员）' : '—')),
          h('dt', null, '方法数量 / 进度'), h('dd', null, h('div', { class: 'row' }, String(Number(p.method_count) || 0) + ' 个', h('div', { style: { minWidth: '160px', flex: 1, maxWidth: '260px' } }, progressCell(p.progress)))),
          h('dt', null, '说明'), h('dd', { style: { whiteSpace: 'pre-wrap' } }, dash(p.description)),
          h('dt', null, '创建 / 更新'), h('dd', null, MF.fmt.datetime(p.created_at) + ' / ' + MF.fmt.datetime(p.updated_at)))));

      var members = p.members || [];
      box.appendChild(cardWith('项目团队', perm.can_manage_members ? h('button', { class: 'btn btn-sm', type: 'button', onclick: editTeam, disabled: p.status !== 'active', title: p.status !== 'active' ? '项目非进行中，不能调整团队' : null }, '编辑团队') : null,
        members.length ? h('div', { class: 'table-wrap' }, h('table', { class: 'table' }, th(['姓名', '账号', '项目角色', '状态']),
          h('tbody', null, members.map(function (m) {
            return h('tr', { class: m.active === false ? 'row-warn' : '' },
              h('td', null, dash(m.display_name || m.username)), h('td', { class: 'mono small' }, dash(m.username)),
              h('td', null, MF.badge(m.role_label || MF.roleLabel(m.role, 'project'), m.role === 'owner' ? 'info' : 'muted')),
              h('td', null, m.active === false ? MF.badge('已停用', 'muted') : MF.badge('在用', 'ok')));
          })))) : empty('暂无成员')));

      var canAdd = perm.can_create_method;
      var addBtn = canAdd ? h('a', { class: 'btn btn-primary btn-sm' + (p.status !== 'active' ? ' disabled' : ''), href: p.status === 'active' ? '#/methods/new?project=' + p.id : null,
        title: p.status !== 'active' ? '项目非进行中，不能新增方法' : null, 'aria-disabled': p.status !== 'active' ? 'true' : null }, '＋ 新增方法') : null;
      box.appendChild(cardWith('方法清单（' + methods.length + '）', addBtn,
        methods.length ? methodsTable(methods, {}) : empty(canAdd ? '该项目下还没有方法，点击“新增方法”开始。' : '该项目下还没有方法。')));
    }

    async function audit(box) {
      if (!auditLoaded) auditLoaded = MF.api('GET', '/api/projects/' + encodeURIComponent(pid) + '/audit?limit=300');
      var rows;
      box.appendChild(MF.loading());
      try { rows = await auditLoaded; } catch (e) { auditLoaded = null; MF.clear(box); box.appendChild(MF.errorBox(e, function () { show('audit'); })); return; }
      MF.clear(box);
      var t = auditTable(rows, { title: '项目审计追踪（含全部方法）' });
      box.appendChild(t.toolbar); box.appendChild(t.body);
    }

    var tabs = [{ key: 'overview', label: '概览', render: overview }, { key: 'audit', label: '审计', render: audit }];
    function show(key) {
      tab = key;
      MF.clear(tabBar);
      tabs.forEach(function (t) {
        tabBar.appendChild(h('button', { class: 'tab' + (t.key === tab ? ' tab-active' : ''), type: 'button', role: 'tab', 'aria-selected': t.key === tab ? 'true' : 'false', onclick: function () { if (t.key !== tab) show(t.key); } }, t.label));
      });
      MF.clear(content);
      var box = h('div'); content.appendChild(box);
      tabs.filter(function (x) { return x.key === key; })[0].render(box);
    }
    c.appendChild(tabBar);
    c.appendChild(content);
    show('overview');
  });

  /* ---------------------------------------------------------------- methods list */
  MF.route('/methods', async function (params, c) {
    MF.setCrumbs([{ label: '方法' }]);
    var res = await Promise.all([MF.api('GET', '/api/projects'), MF.api('GET', '/api/templates').then(null, function () { return []; })]);
    var projects = res[0] || [], templates = res[1] || [];
    var pre = MF.query();
    var q = h('input', { class: 'input', style: { maxWidth: '260px' }, placeholder: '搜索编号、名称、被测属性、基质、项目', type: 'search' });
    var st = sel([['', '全部状态']].concat(METHOD_STATUS_OPTS), '');
    var pj = sel([['', '全部项目']].concat(projects.map(function (p) { return [String(p.id), str(p.code) + ' ' + str(p.name)]; })), pre.project || '');
    var tc = sel([['', '全部技术']].concat(templates.map(function (t) { return [t.key, str(t.label)]; })), '');
    var lc = sel([['', '全部生命周期']].concat(LIFECYCLE_OPTS), '');
    var count = h('span', { class: 'muted small' });
    var holder = h('div');
    var seq = 0;
    async function load() {
      var my = ++seq;
      var rows;
      try { rows = await MF.api('GET', '/api/methods' + MF.qs({ q: q.value.trim(), status: st.value, project_id: pj.value, technique: tc.value, lifecycle: lc.value })); } catch (e) { fail(e); return; }
      if (my !== seq) return;
      count.textContent = '共 ' + rows.length + ' 个方法';
      MF.clear(holder);
      if (!rows.length) { holder.appendChild(empty(q.value.trim() || st.value || pj.value || tc.value || lc.value ? '没有符合条件的方法' : '还没有可见的方法')); return; }
      holder.appendChild(methodsTable(rows, { showProject: true }));
    }
    q.addEventListener('input', debounce(load, 250));
    [st, pj, tc, lc].forEach(function (s) { s.addEventListener('change', load); });
    c.appendChild(h('div', { class: 'page-head' }, h('div', null, h('h1', null, '方法'), h('p', null, '你可见的全部分析方法。方法归属于项目，在项目页或此处新增。')), h('span', { class: 'spacer' }),
      MF.hasRole('author', 'admin') ? h('a', { class: 'btn btn-primary', href: '#/methods/new' + (pj.value ? '?project=' + encodeURIComponent(pj.value) : '') }, '＋ 新增方法') : null));
    c.appendChild(h('div', { class: 'toolbar' }, q, st, pj, tc, lc, count));
    c.appendChild(h('div', { class: 'card', style: { padding: '4px 8px' } }, holder));
    await load();
  });

  /* ---------------------------------------------------------------- new method */
  MF.route('/methods/new', async function (params, c) {
    var pre = MF.query();
    MF.setCrumbs([{ label: '方法', href: '/methods' }, { label: '新增方法' }]);
    c.appendChild(h('div', { class: 'page-head' }, h('div', null, h('h1', null, '新增方法'),
      h('p', null, '在项目下按模板创建一个分析方法。创建即启动标准流程的第 1 步，之后严格按 9 步推进。'))));
    if (!requireLoginRole(c, ['author', 'admin'], '仅“开发人员”或管理员可以新增方法。')) return;
    if (MF.guide && MF.guide.order) {
      var gate = { atp: 'G1', tech: 'G2', plan: 'GP', explore: 'G3', control: 'G4', report: 'G5' };
      c.appendChild(h('div', { class: 'card' }, h('h3', null, '标准流程：9 步，按顺序推进'),
        h('div', { class: 'row', style: { gap: '6px', flexWrap: 'wrap' } }, MF.guide.order.map(function (k, i) {
          var g = MF.guide.stages[k];
          return h('span', { class: 'badge ' + (i === 0 ? 'badge-info' : 'badge-muted'), style: { padding: '4px 10px' } }, (i === 0 ? '▶ ' : '') + g.n + ' ' + g.name + (gate[k] ? ' 🔒' + gate[k] : ''));
        })),
        h('p', { class: 'small muted', style: { margin: '8px 0 0' } }, '后一步需要前一步通过（或完成）后才开放填写；带 🔒 的是评审门，需他人复核（部分还需 QA 批准）。创建后你将从第 1 步开始。')));
    }
    var me = MF.state.user || {};
    var res = await Promise.all([MF.api('GET', '/api/templates'), MF.api('GET', '/api/projects'), MF.api('GET', '/api/users')]);
    var templates = res[0] || [];
    var projects = (res[1] || []).filter(function (p) {
      return p.status === 'active' && ((p.my_roles || []).indexOf('owner') >= 0 || (p.my_roles || []).indexOf('member') >= 0 || MF.hasRole('admin'));
    });
    var userMap = {};
    (res[2] || []).forEach(function (u) { userMap[u.id] = u; });
    if (!projects.length) {
      c.appendChild(h('div', { class: 'card empty' }, h('p', null, '没有可以新增方法的项目。需要是进行中项目的“项目负责人”或“项目成员”（只读成员不可新增）。'),
        h('a', { class: 'btn btn-primary', href: '#/projects/new' }, '新建项目')));
      return;
    }

    var selTpl = templates.some(function (t) { return t.key === 'generic'; }) ? 'generic' : (templates[0] ? templates[0].key : '');
    var tplCards = [];
    var tplInfo = h('div');
    function drawTplInfo() {
      MF.clear(tplInfo);
      var t = templates.filter(function (x) { return x.key === selTpl; })[0];
      if (!t) return;
      var st = t.stats || {};
      var chips = [['FMEA 风险条目', st.fmea], ['计划实验', st.experiments], ['SST 项', st.sst], ['ATP 判据行', st.atp_rows]].filter(function (x) { return x[1] !== undefined && x[1] !== null; });
      tplInfo.appendChild(h('div', { class: 'callout' },
        h('div', { class: 'row', style: { gap: '8px' } }, h('strong', null, str(t.label)), MF.badge('模板 v' + str(t.version), 'info'),
          chips.map(function (x) { return MF.badge(x[0] + ' ' + x[1], 'muted'); })),
        h('div', { class: 'small', style: { marginTop: '4px' } }, str(t.desc)),
        (t.changelog || []).length ? h('details', { style: { marginTop: '6px' } }, h('summary', { class: 'small' }, '版本更新记录（' + t.changelog.length + '）'),
          t.changelog.map(function (cl) {
            return h('div', { class: 'small', style: { marginTop: '6px' } }, h('strong', null, 'v' + str(cl.version)), ' ', h('span', { class: 'muted' }, str(cl.date) + (cl.scope ? ' · ' + str(cl.scope) : '')),
              h('ul', { style: { margin: '2px 0 0', paddingLeft: '20px' } }, (cl.changes || []).map(function (x) { return h('li', null, str(x)); })));
          })) : null));
    }
    var tplBox = h('div', { class: 'tpl-grid' }, templates.map(function (t) {
      var st = t.stats || {};
      var card = h('label', { class: 'tpl-card' + (t.key === selTpl ? ' selected' : '') },
        h('input', { type: 'radio', name: 'tpl', value: t.key, checked: t.key === selTpl }),
        h('div', { class: 't' }, str(t.label), ' ', h('span', { class: 'badge badge-muted' }, 'v' + str(t.version))),
        h('div', { class: 'small muted' }, str(t.desc)),
        h('div', { class: 'small', style: { marginTop: '6px' } }, 'FMEA ' + (Number(st.fmea) || 0) + ' · 实验 ' + (Number(st.experiments) || 0) + ' · SST ' + (Number(st.sst) || 0) + ' · ATP ' + (Number(st.atp_rows) || 0)));
      card.querySelector('input').addEventListener('change', function () {
        selTpl = t.key;
        tplCards.forEach(function (x) { x.classList.toggle('selected', x === card); });
        drawTplInfo();
      });
      tplCards.push(card);
      return card;
    }));

    var projSel = h('select', { class: 'select' }, projects.map(function (p) { return h('option', { value: String(p.id) }, str(p.code) + '　' + str(p.name)); }));
    if (pre.project && projects.some(function (p) { return String(p.id) === String(pre.project); })) projSel.value = String(pre.project);
    var projNote = h('div');
    var name = h('input', { class: 'input', maxlength: 200, placeholder: '例如：CD19/CD22 双靶点 CAR 流式检测法' });
    var analyte = h('input', { class: 'input', placeholder: '被测属性，例如：CAR 阳性率' });
    var matrix = h('input', { class: 'input', placeholder: '样品基质，例如：PBMC / 终产品细胞悬液' });
    var use = h('input', { class: 'input', list: 'use-list', placeholder: '预期用途，例如：放行检测 / 过程控制 / 稳定性研究' });
    var useList = h('datalist', { id: 'use-list' }, ['放行检测', '过程控制', '稳定性研究', '表征 / 鉴别', '可比性研究'].map(function (x) { return h('option', { value: x }); }));
    var phase = h('select', { class: 'select' }, PHASE_OPTS.map(function (x) { return h('option', { value: x }, x || '（未指定）'); }));
    var ver = h('input', { class: 'input', value: 'V0.1' });
    var start = h('input', { class: 'input', type: 'date', value: todayStr() });

    var teamBox = h('div');
    var warnBox = h('div');
    var pickers = {};
    var projDetail = null;
    function refresh() {
      var vals = {};
      Object.keys(pickers).forEach(function (k) { vals[k] = pickers[k].values(); });
      Object.keys(pickers).forEach(function (k) {
        var taken = [];
        Object.keys(vals).forEach(function (o) { if (o !== k) taken = taken.concat(vals[o]); });
        pickers[k].lock(taken);
      });
      MF.clear(warnBox);
      if (!pickers.reviewer) return;
      if (!vals.reviewer.length) warnBox.appendChild(h('div', { class: 'callout callout-warn' }, '尚未选择复核人：需要复核的阶段（如 G1 ATP 复核）将无人可以签署。可稍后在方法页补充，但建议现在指定。'));
      if (!vals.approver.length) warnBox.appendChild(h('div', { class: 'callout callout-warn' }, '尚未选择批准人（QA）：开发方案批准（GP）、控制策略（G4）、进入验证（G5）需要批准人签署。'));
    }
    function candHint(role, label, count, globalLabel) {
      if (count) return '候选：本项目成员中具备“' + globalLabel + '”系统角色的用户。';
      return h('span', { class: 'err-text' }, '本项目成员中没有具备“' + globalLabel + '”系统角色的用户。请项目负责人先把' + label + '加入项目团队（' + (projDetail ? '项目页 → 编辑团队' : '项目页') + '）' +
        (MF.hasRole('admin') ? '；也可在“管理”中授予相应系统角色。' : '，或联系管理员授予系统角色。'));
    }
    async function loadProject() {
      MF.clear(teamBox); MF.clear(projNote); MF.clear(warnBox);
      pickers = {};
      teamBox.appendChild(MF.loading('加载项目成员……'));
      var d;
      try { d = await MF.api('GET', '/api/projects/' + encodeURIComponent(projSel.value)); } catch (e) { MF.clear(teamBox); teamBox.appendChild(MF.errorBox(e)); return; }
      projDetail = d;
      MF.clear(teamBox);
      var perm = d.permissions || {};
      if (perm.can_create_method === false) projNote.appendChild(h('div', { class: 'callout callout-err' }, '你在该项目中没有新增方法的权限（需要项目负责人或项目成员）。'));
      var cands = (d.members || []).filter(function (m) { return m.active !== false && m.user_id !== me.id; }).map(function (m) {
        var u = userMap[m.user_id] || {};
        return { id: m.user_id, username: m.username || u.username, display_name: m.display_name || u.display_name, roles: u.roles || [] };
      });
      function has(role) { return function (u) { return (u.roles || []).indexOf(role) >= 0; }; }
      function mk(role, filter) { pickers[role] = userPicker(cands.filter(filter), refresh); return pickers[role]; }
      var pRev = mk('reviewer', has('reviewer')), pApp = mk('approver', has('approver')),
        pAut = mk('author', function (u) { return has('author')(u) || has('admin')(u); }), pVie = mk('viewer', function () { return true; });
      teamBox.appendChild(h('div', { class: 'callout' }, '您（创建人）自动成为“方法负责人”和“开发人员”。候选人只来自项目团队，且按系统角色过滤。' +
        '规则：复核人 / 批准人不能同时担任开发人员（编辑内容者）；复核人与批准人必须是不同的人，因此同一用户只能选择一个角色；您本人不会出现在候选列表中。'));
      teamBox.appendChild(h('div', { class: 'form-grid' },
        MF.field('复核人（可多选）', pRev.el, { hint: candHint('reviewer', '复核人', pRev.count, '复核人') }),
        MF.field('批准人 / QA（可多选）', pApp.el, { hint: candHint('approver', '批准人', pApp.count, '批准人') }),
        MF.field('其他开发人员（可编辑）', pAut.el, { hint: '需具备“开发人员”系统角色；可与您共同编辑内容，因此不能同时担任复核人 / 批准人。' }),
        MF.field('只读成员', pVie.el, { hint: '项目成员中的任何人；仅可查看方法，不能编辑或签署。' })));
      refresh();
    }
    projSel.addEventListener('change', loadProject);

    var errBox = h('div', { class: 'callout callout-err', hidden: true, role: 'alert' });
    var s1Obj = h('textarea', { class: 'textarea', rows: 3, placeholder: '例：建立流式细胞术方法测定 CAR-T 产品的 CAR+ 比例，用于放行检测；满足 ATP 判据即视为开发完成。' });
    var s1Scope = h('textarea', { class: 'textarea', rows: 2, placeholder: '例：适用于冻存与新鲜 PBMC 制剂；不含效力测定与载体拷贝数。' });
    var s1Phase = h('select', { class: 'select' }, ['', '临床前/研究', 'I 期 IND', 'II 期', '确证性研究前', 'BLA/上市申请', '上市后变更'].map(function (x) { return h('option', { value: x }, x || '（请选择）'); }));
    var s1Region = h('select', { class: 'select' }, ['', '中国 NMPA', '美国 FDA', '欧盟 EMA', '多区域'].map(function (x) { return h('option', { value: x }, x || '（请选择）'); }));
    var submit = h('button', { class: 'btn btn-primary', type: 'submit' }, '创建方法并开始第 1 步');
    var form = h('form', { novalidate: true, onsubmit: async function (ev) {
      ev.preventDefault();
      errBox.hidden = true;
      if (!name.value.trim()) { errBox.textContent = '请填写方法名称'; errBox.hidden = false; name.focus(); return; }
      if (!selTpl) { errBox.textContent = '请选择模板'; errBox.hidden = false; return; }
      var members = [];
      [['reviewer'], ['approver'], ['author'], ['viewer']].forEach(function (x) {
        var pk = pickers[x[0]];
        if (pk) pk.values().forEach(function (uid) { members.push({ user_id: uid, role: x[0] }); });
      });
      if (!s1Obj.value.trim()) { errBox.textContent = '请填写第 1 步的“目的与成功标准”——这是标准流程的起点'; errBox.hidden = false; s1Obj.focus(); return; }
      submit.disabled = true;
      try {
        var r = await MF.api('POST', '/api/projects/' + encodeURIComponent(projSel.value) + '/methods', {
          name: name.value.trim(), template_key: selTpl, analyte: analyte.value.trim(), matrix: matrix.value.trim(), intended_use: use.value.trim(),
          phase: phase.value, method_version: ver.value.trim() || 'V0.1', planned_start: start.value || todayStr(), members: members
        });
        MF.dirtyGuard.set(false);
        // 把创建向导里填写的“第 1 步”核心内容写入立项阶段，随后直接进入第 1 步继续完成
        var seeded = true;
        try {
          var st = await MF.api('GET', '/api/methods/' + r.id + '/stages/charter');
          var secs = { objective: s1Obj.value.trim() };
          if (s1Scope.value.trim()) secs.scope = s1Scope.value.trim();
          var ctxv = {};
          if (s1Phase.value) ctxv.phase = s1Phase.value;
          if (s1Region.value) ctxv.region = s1Region.value;
          if (Object.keys(ctxv).length) secs.context = ctxv;
          await MF.api('PUT', '/api/methods/' + r.id + '/stages/charter', { version: st.version, sections: secs });
        } catch (e2) { seeded = false; }
        MF.toast(seeded ? '方法已创建，已写入第 1 步的核心内容，请继续完成第 1 步' : '方法已创建，请进入第 1 步填写立项内容', seeded ? 'ok' : 'warn');
        MF.navigate('/m/' + r.id + '/stage/charter');
      } catch (e) {
        submit.disabled = false;
        if (e.status === 401) return;
        errBox.textContent = e.message || '创建失败'; errBox.hidden = false;
      }
    } },
      h('div', { class: 'card' }, h('h3', null, '1. 所属项目'), MF.field('项目', projSel, { required: true, hint: '仅列出你作为负责人或成员的“进行中”项目。' }), projNote),
      h('div', { class: 'card' }, h('h3', null, '2. 选择技术模板'),
        h('p', { class: 'hint' }, '模板决定阶段、检查清单、风险库、计划实验与受控文件结构的初始内容；创建后不可更换。'), tplBox, h('div', { style: { marginTop: '10px' } }, tplInfo)),
      h('div', { class: 'card' }, h('h3', null, '3. 基本信息'),
        h('div', { class: 'form-grid' },
          h('div', { class: 'span2' }, MF.field('方法名称', name, { required: true })),
          MF.field('被测属性（分析物）', analyte), MF.field('样品基质', matrix),
          MF.field('预期用途', use), MF.field('研发阶段', phase),
          MF.field('方法版本', ver, { hint: '例如 V0.1（开发中）。' }), MF.field('计划开始日期', start, { hint: '各阶段计划日期将据此顺延排布。' })), useList),
      h('div', { class: 'card' }, h('h3', null, '4. 方法团队'), teamBox, warnBox),
      h('div', { class: 'card' }, h('h3', null, '5. 第 1 步「立项与背景」核心内容'),
        h('p', { class: 'hint' }, '创建方法就是启动标准流程的第 1 步：先写清“目的与成功标准”。这些内容会直接写入第 1 步，创建后你会进入第 1 步继续完成其余部分（职责、术语、参考文件、背景等）。'),
        MF.field('目的与成功标准', s1Obj, { required: true, hint: '一句话：用什么方法、测什么、用于什么、达到什么指标算开发完成。' }),
        MF.field('适用范围与不在范围', s1Scope, { hint: '范围内做什么；明确不在范围内的内容，例如不含效力测定。' }),
        h('div', { class: 'form-grid' }, MF.field('产品阶段', s1Phase, { hint: '决定后续验证强度。' }), MF.field('目标区域', s1Region))),
      errBox,
      h('div', { class: 'row' }, submit, h('a', { class: 'btn', href: '#/methods' }, '取消')));
    form.addEventListener('input', function () { MF.dirtyGuard.set(true); });
    form.addEventListener('change', function () { MF.dirtyGuard.set(true); });
    c.appendChild(form);
    drawTplInfo();
    await loadProject();
    MF.dirtyGuard.set(false);
  });

  /* ---------------------------------------------------------------- knowledge base */
  var KB_KINDS = { rule: ['规则 / 原则', 'info'], pitfall: ['常见陷阱', 'warn'], howto: ['操作指引', 'ok'], reference: ['法规 / 参考', 'muted'], lesson: ['经验教训', 'info'] };

  MF.route('/kb', async function (params, c) {
    MF.setCrumbs([{ label: '知识库' }]);
    var templates = [];
    try { templates = await MF.api('GET', '/api/templates'); } catch (e) { if (e.status === 401) return; }
    var techName = { all: '通用' };
    templates.forEach(function (t) { techName[t.key] = t.label; });

    var q = h('input', { class: 'input', type: 'search', style: { maxWidth: '280px' }, placeholder: '搜索标题、内容、标签、来源' });
    var kind = h('select', { class: 'select', style: { width: 'auto' } }, [h('option', { value: '' }, '全部类型')].concat(Object.keys(KB_KINDS).map(function (k) { return h('option', { value: k }, KB_KINDS[k][0]); })));
    var tech = h('select', { class: 'select', style: { width: 'auto' } }, [h('option', { value: '' }, '全部技术')].concat(templates.map(function (t) { return h('option', { value: t.key }, t.label); })));
    var count = h('span', { class: 'muted small' });
    var holder = h('div');
    var seq = 0;

    async function load() {
      var my = ++seq;
      var items;
      try { items = await MF.api('GET', '/api/kb' + MF.qs({ q: q.value.trim(), kind: kind.value, technique: tech.value })); } catch (e) { fail(e); return; }
      if (my !== seq) return;
      count.textContent = '共 ' + items.length + ' 条';
      MF.clear(holder);
      if (!items.length) { holder.appendChild(h('div', { class: 'card empty' }, '没有符合条件的知识条目')); return; }
      holder.appendChild(h('div', { class: 'grid', style: { gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))' } }, items.map(kbCard)));
    }
    function kbCard(it) {
      var k = KB_KINDS[it.kind] || [str(it.kind) || '其他', 'muted'];
      var body = str(it.body);
      var long = body.length > 200;
      var bodyEl = h('div', { class: 'kb-body' }, long ? body.slice(0, 200) + '……' : body);
      var toggle = long ? h('button', { class: 'btn btn-sm btn-ghost', type: 'button' }, '展开') : null;
      if (toggle) {
        var open = false;
        toggle.addEventListener('click', function () { open = !open; bodyEl.textContent = open ? body : body.slice(0, 200) + '……'; toggle.textContent = open ? '收起' : '展开'; });
      }
      var techs = (it.techniques || []).map(function (t) { return techName[t] || t; });
      var stages = (it.stages || []).map(function (s) { return STAGE_TITLES[s] || s; });
      return h('div', { class: 'card' },
        h('div', { class: 'row', style: { marginBottom: '6px' } }, MF.badge(k[0], k[1]), it.builtin ? MF.badge('内置', 'muted') : null, h('span', { class: 'spacer' }),
          it.origin_method_id ? h('a', { class: 'small', href: '#/m/' + it.origin_method_id }, '来源方法 →') : null,
          MF.hasRole('admin', 'approver') ? h('button', { class: 'btn btn-sm btn-ghost', type: 'button', title: '停用后不再显示', onclick: async function () {
            if (!(await MF.confirm('确定停用知识条目“' + str(it.title) + '”？停用后将不再对所有用户显示。', { danger: true, okLabel: '停用' }))) return;
            try { await MF.api('DELETE', '/api/kb/' + it.id); MF.toast('已停用', 'ok'); load(); } catch (e) { fail(e); }
          } }, '停用') : null),
        h('h3', { style: { marginBottom: '6px' } }, str(it.title)),
        bodyEl, toggle,
        h('div', { class: 'row', style: { gap: '4px', marginTop: '8px' } }, (it.tags || []).map(function (t) { return MF.badge('#' + str(t), 'muted'); })),
        h('div', { class: 'small muted', style: { marginTop: '8px' } },
          (it.source ? '来源：' + str(it.source) + '　' : ''), '适用技术：' + (techs.length ? techs.join('、') : '通用'), (stages.length ? '　适用阶段：' + stages.join('、') : '')));
    }

    function addDialog() {
      var kSel = h('select', { class: 'select' }, ['lesson', 'rule', 'pitfall', 'howto', 'reference'].map(function (k) { return h('option', { value: k }, KB_KINDS[k][0]); }));
      var title = h('input', { class: 'input', maxlength: 200, placeholder: '一句话概括这条经验' });
      var body = h('textarea', { class: 'textarea', rows: 6, placeholder: '背景、做法、结论与注意事项；写清楚“在什么情况下、做了什么、结果如何”。' });
      var tags = h('input', { class: 'input', placeholder: '多个标签用逗号分隔，例如：流式, 背景, 抗体' });
      var source = h('input', { class: 'input', placeholder: '例如：方法 AM-2026-001 / 文献 / 法规指南相应章节' });
      var techBoxes = [{ key: 'all', label: '通用（所有技术）' }].concat(templates.map(function (t) { return { key: t.key, label: t.label }; })).map(function (t) {
        var cb = h('input', { type: 'checkbox', checked: t.key === 'all' });
        return { key: t.key, cb: cb, el: h('label', { class: 'check' }, cb, t.label) };
      });
      var stageBoxes = Object.keys(STAGE_TITLES).map(function (k) {
        var cb = h('input', { type: 'checkbox' });
        return { key: k, cb: cb, el: h('label', { class: 'check' }, cb, STAGE_TITLES[k]) };
      });
      var bodyNode = h('div', null,
        h('div', { class: 'form-grid' }, MF.field('类型', kSel), MF.field('来源', source)),
        MF.field('标题', title, { required: true }), MF.field('内容', body, { required: true }), MF.field('标签', tags),
        MF.field('适用技术', h('div', { class: 'row', style: { gap: '4px 14px' } }, techBoxes.map(function (t) { return t.el; }))),
        MF.field('适用阶段', h('div', { class: 'row', style: { gap: '4px 14px' } }, stageBoxes.map(function (t) { return t.el; })), { hint: '不选表示适用于所有阶段。' }));
      return MF.modal({
        title: '新增经验', body: bodyNode, width: 640,
        buttons: [{ label: '取消', value: null }, {
          label: '保存', kind: 'primary', value: true,
          onClick: function (ctl) {
            if (!title.value.trim() || !body.value.trim()) { ctl.error('标题和内容不能为空'); return false; }
            var techs = techBoxes.filter(function (t) { return t.cb.checked; }).map(function (t) { return t.key; });
            if (techs.indexOf('all') >= 0 || !techs.length) techs = ['all'];
            return MF.api('POST', '/api/kb', {
              kind: kSel.value, title: title.value.trim(), body: body.value.trim(), source: source.value.trim(),
              tags: tags.value.split(/[,，、;；]+/).map(function (x) { return x.trim(); }).filter(Boolean),
              techniques: techs, stages: stageBoxes.filter(function (s) { return s.cb.checked; }).map(function (s) { return s.key; })
            });
          }
        }]
      }).then(function (ok) { if (ok) { MF.toast('已新增经验', 'ok'); load(); } });
    }

    async function syncKb(btn) {
      if (!(await MF.confirm('将按标题补充系统内置知识库中缺失的条目；用户创建、编辑或已停用的条目不会被覆盖或恢复。可重复执行。继续？', { okLabel: '开始同步' }))) return;
      btn.disabled = true;
      try {
        var r = await MF.api('POST', '/api/admin/kb-sync', {});
        MF.toast('同步完成：新增 ' + (Number(r.added) || 0) + ' 条，已有 ' + (Number(r.existing) || 0) + ' 条，共 ' + (Number(r.total) || 0) + ' 条', 'ok');
        load();
      } catch (e) { fail(e); }
      btn.disabled = false;
    }

    var syncBtn = MF.hasRole('admin') ? h('button', { class: 'btn', type: 'button', title: '补充程序升级后新增的内置条目', onclick: function () { syncKb(syncBtn); } }, '同步内置知识库') : null;
    q.addEventListener('input', debounce(load, 250));
    kind.addEventListener('change', load);
    tech.addEventListener('change', load);
    c.appendChild(h('div', { class: 'page-head' }, h('div', null, h('h1', null, '知识库'), h('p', null, '方法开发的规则、常见陷阱、操作指引与项目沉淀的经验教训。')), h('span', { class: 'spacer' }),
      syncBtn,
      h('a', { class: 'btn', href: '#/kb/links' }, '资源链接（法规 / 官网 / 文献）'),
      MF.hasRole('author', 'admin') ? h('button', { class: 'btn btn-primary', type: 'button', onclick: addDialog }, '＋ 新增经验') : null));
    c.appendChild(h('div', { class: 'toolbar' }, q, kind, tech, count));
    c.appendChild(holder);
    await load();
  });

  /* ---------------------------------------------------------------- admin */
  MF.route('/admin', async function (params, c) {
    MF.setCrumbs([{ label: '管理' }]);
    if (!requireLoginRole(c, ['admin', 'approver'], '仅管理员可以访问管理页面。')) return;
    var isAdmin = MF.hasRole('admin');
    var tabs = [];
    if (isAdmin) tabs.push({ key: 'users', label: '用户管理', render: renderUsers }, { key: 'backup', label: '数据备份', render: renderBackup });
    tabs.push({ key: 'audit', label: '审计追踪', render: renderAudit });
    tabs.push({ key: 'auditreview', label: '审计追踪审核', render: function (cont) { cont.appendChild(h('div', { class: 'card' }, h('p', null, '定期审核审计追踪并签署记录（含哈希链与签名完整性校验）。'), h('a', { class: 'btn btn-primary', href: '#/audit-review' }, '打开审计追踪审核'))); } });
    if (isAdmin) tabs.push({ key: 'settings', label: '文档设置', render: renderSettings });
    var cur = tabs[0].key;
    var tabBar = h('div', { class: 'tabs', role: 'tablist' });
    var content = h('div');
    function show(key) {
      cur = key;
      MF.clear(tabBar);
      tabs.forEach(function (t) {
        tabBar.appendChild(h('button', { class: 'tab' + (t.key === cur ? ' tab-active' : ''), type: 'button', role: 'tab', 'aria-selected': t.key === cur ? 'true' : 'false', onclick: function () { if (t.key !== cur) show(t.key); } }, t.label));
      });
      MF.clear(content);
      var t = tabs.filter(function (x) { return x.key === key; })[0];
      var box = h('div'); content.appendChild(box);
      Promise.resolve(t.render(box)).then(null, function (e) { if (e && e.status === 401) return; MF.clear(box); box.appendChild(MF.errorBox(e, function () { show(key); })); });
    }
    c.appendChild(h('div', { class: 'page-head' }, h('div', null, h('h1', null, '管理'), h('p', null, '用户与角色、数据备份、审计追踪与链校验、受控文件设置。'))));
    c.appendChild(tabBar);
    c.appendChild(content);
    show(cur);
  });

  /* ---- users ---- */
  async function renderUsers(box) {
    var minLen = (MF.state.app && MF.state.app.min_password_length) || 10;
    var users = await MF.api('GET', '/api/users');
    var me = MF.state.user || {};

    function roleChecks(selected) {
      var cbs = ALL_ROLES.map(function (r) {
        var cb = h('input', { type: 'checkbox', checked: selected.indexOf(r) >= 0, value: r });
        return { r: r, cb: cb, el: h('label', { class: 'check', style: { alignItems: 'flex-start', display: 'flex' }, title: ROLE_HINT[r] }, cb, h('span', null, MF.roleLabel(r), h('span', { class: 'small muted' }, '　' + ROLE_HINT[r]))) };
      });
      return { el: h('div', { class: 'col', style: { gap: '4px' } }, cbs.map(function (x) { return x.el; })), get: function () { return cbs.filter(function (x) { return x.cb.checked; }).map(function (x) { return x.r; }); } };
    }
    function pwRuleOk(pw) { return pw.length >= minLen && /[A-Za-z]/.test(pw) && /\d/.test(pw); }

    function createDialog() {
      var un = h('input', { class: 'input', autocomplete: 'off' });
      var dn = h('input', { class: 'input', autocomplete: 'off' });
      var pw = h('input', { class: 'input', type: 'text', autocomplete: 'off' });
      var roles = roleChecks(['author']);
      return MF.modal({
        title: '新建用户', width: 520,
        body: h('div', null, MF.field('用户名', un, { required: true, hint: '用于登录，创建后不可修改。' }), MF.field('姓名', dn, { required: true, hint: '显示在签名和审计记录中，请使用真实姓名。' }),
          MF.field('初始密码', pw, { required: true, hint: '至少 ' + minLen + ' 位，须同时包含字母和数字。用户首次登录后必须修改。' }), MF.field('角色', roles.el)),
        buttons: [{ label: '取消', value: null }, {
          label: '创建', kind: 'primary', value: true,
          onClick: function (ctl) {
            if (!un.value.trim() || !dn.value.trim()) { ctl.error('请填写用户名和姓名'); return false; }
            if (!pwRuleOk(pw.value)) { ctl.error('初始密码至少 ' + minLen + ' 位，且须同时包含字母和数字'); return false; }
            if (!roles.get().length) { ctl.error('请至少选择一个角色'); return false; }
            return MF.api('POST', '/api/users', { username: un.value.trim(), display_name: dn.value.trim(), password: pw.value, roles: roles.get() });
          }
        }]
      }).then(function (ok) { if (ok) { MF.toast('用户已创建', 'ok'); draw(); } });
    }
    function editDialog(u) {
      var dn = h('input', { class: 'input', value: str(u.display_name) });
      var roles = roleChecks(u.roles || []);
      var act = h('input', { type: 'checkbox', checked: !!u.active, disabled: u.id === me.id });
      return MF.modal({
        title: '编辑用户：' + str(u.username), width: 520,
        body: h('div', null, MF.field('姓名', dn), MF.field('角色', roles.el, u.id === me.id ? { hint: '不能移除自己的管理员角色。' } : null),
          h('label', { class: 'check' }, act, '账号启用', u.id === me.id ? h('span', { class: 'small muted' }, '（不能停用自己）') : h('span', { class: 'small muted' }, '（停用后立即退出登录且无法登录）'))),
        buttons: [{ label: '取消', value: null }, {
          label: '保存', kind: 'primary', value: true,
          onClick: function (ctl) {
            if (!dn.value.trim()) { ctl.error('姓名不能为空'); return false; }
            if (!roles.get().length) { ctl.error('请至少选择一个角色'); return false; }
            return MF.api('PATCH', '/api/users/' + u.id, { display_name: dn.value.trim(), roles: roles.get(), active: act.checked });
          }
        }]
      }).then(function (ok) { if (ok) { MF.toast('已保存', 'ok'); draw(); } });
    }
    function resetDialog(u) {
      var pw = h('input', { class: 'input', type: 'text', autocomplete: 'off' });
      return MF.modal({
        title: '重置密码：' + str(u.display_name || u.username), width: 460,
        body: h('div', null, h('div', { class: 'callout callout-warn' }, '重置后该用户的现有会话会被注销，并须在下次登录时修改密码。请通过安全渠道将新密码告知本人。'),
          MF.field('新的临时密码', pw, { required: true, hint: '至少 ' + minLen + ' 位，须同时包含字母和数字。' })),
        buttons: [{ label: '取消', value: null }, {
          label: '重置密码', kind: 'danger', value: true,
          onClick: function (ctl) {
            if (!pwRuleOk(pw.value)) { ctl.error('密码至少 ' + minLen + ' 位，且须同时包含字母和数字'); return false; }
            return MF.api('PATCH', '/api/users/' + u.id, { reset_password: pw.value });
          }
        }]
      }).then(function (ok) { if (ok) MF.toast('密码已重置', 'ok'); });
    }
    async function toggleActive(u) {
      var to = !u.active;
      if (!(await MF.confirm((to ? '确定重新启用用户“' : '确定停用用户“') + str(u.display_name || u.username) + '”？', { danger: !to }))) return;
      try { await MF.api('PATCH', '/api/users/' + u.id, { active: to }); MF.toast(to ? '已启用' : '已停用', 'ok'); draw(); } catch (e) { fail(e); }
    }

    async function draw() {
      try { users = await MF.api('GET', '/api/users'); } catch (e) { fail(e); return; }
      MF.clear(box);
      box.appendChild(h('div', { class: 'toolbar' }, h('span', { class: 'muted' }, '共 ' + users.length + ' 个用户'), h('span', { class: 'spacer' }),
        h('button', { class: 'btn btn-primary', type: 'button', onclick: createDialog }, '＋ 新建用户')));
      box.appendChild(h('div', { class: 'card', style: { padding: '4px 8px' } }, h('div', { class: 'table-wrap' }, h('table', { class: 'table' },
        th(['用户名', '姓名', '角色', '状态', '操作']),
        h('tbody', null, users.map(function (u) {
          return h('tr', { class: u.active ? '' : 'row-warn' },
            h('td', { class: 'mono' }, str(u.username)),
            h('td', null, str(u.display_name), u.id === me.id ? h('span', { class: 'small muted' }, '（我）') : null),
            h('td', null, roleBadges(u.roles)),
            h('td', null, u.active ? MF.badge('启用', 'ok') : MF.badge('已停用', 'muted')),
            h('td', null, h('div', { class: 'row', style: { gap: '6px' } },
              h('button', { class: 'btn btn-sm', type: 'button', onclick: function () { editDialog(u); } }, '编辑'),
              h('button', { class: 'btn btn-sm', type: 'button', onclick: function () { resetDialog(u); } }, '重置密码'),
              u.id === me.id ? null : h('button', { class: 'btn btn-sm', type: 'button', onclick: function () { toggleActive(u); } }, u.active ? '停用' : '启用'))));
        }))))));
      box.appendChild(h('p', { class: 'hint' }, '提示：方法内的“复核人 / 批准人”由方法团队角色决定，且成员必须先加入所属项目；此处的用户角色决定可被指定为哪类成员以及系统级权限。新建或重置密码的用户首次登录时须先修改密码。'));
    }
    await draw();
  }

  /* ---- backups ---- */
  async function renderBackup(box) {
    var holder = h('div');
    async function draw() {
      var list = await MF.api('GET', '/api/admin/backups');
      MF.clear(holder);
      holder.appendChild(list.length ? h('div', { class: 'table-wrap' }, h('table', { class: 'table' },
        th(['备份文件', '大小', '时间']),
        h('tbody', null, list.map(function (b) {
          return h('tr', null, h('td', { class: 'mono' }, str(b.name)), h('td', { class: 'nowrap' }, MF.fmt.size(b.size)), h('td', { class: 'nowrap' }, MF.fmt.datetime(b.mtime)));
        })))) : empty('暂无备份'));
    }
    var btn = h('button', { class: 'btn btn-primary', type: 'button', onclick: async function () {
      btn.disabled = true;
      try { var r = await MF.api('POST', '/api/admin/backup', {}); MF.toast('备份完成：' + str(r.name), 'ok'); await draw(); } catch (e) { fail(e); }
      btn.disabled = false;
    } }, '立即备份');
    box.appendChild(h('div', { class: 'callout' }, '系统在启动时及此后每 24 小时自动备份一次数据库，并按保留份数自动清理旧备份。备份文件只包含数据库；附件文件保存在数据目录的 uploads 文件夹，生成的文档保存在数据目录的 docs 文件夹，请一并纳入您的备份策略。'));
    box.appendChild(h('div', { class: 'toolbar' }, btn));
    box.appendChild(h('div', { class: 'card', style: { padding: '4px 8px' } }, holder));
    await draw();
  }

  /* ---- audit + verification ---- */
  var ANCHOR_LABEL = { ok: ['一致', 'ok'], missing: ['锚点文件缺失', 'err'], tampered: ['锚点被篡改', 'err'], shorter: ['记录数少于锚点（疑似删除）', 'err'], mismatch: ['与锚点不一致', 'err'], not_checked: ['未启用', 'muted'] };

  async function renderAudit(box) {
    var result = h('div');
    function checkRow(label, ok, okText, badText, extra) {
      return h('tr', null, h('td', { class: 'nowrap' }, label), h('td', null, ok === null || ok === undefined ? MF.badge('未检查', 'muted') : ok ? MF.badge(okText || '正常', 'ok') : MF.badge(badText || '异常', 'err')), h('td', { class: 'small muted' }, extra || ''));
    }
    function showResult(r) {
      MF.clear(result);
      var sigOk = r.signatures_ok !== false;
      var bad = r.bad_signatures || [];
      var allOk = !!r.ok && sigOk;
      if (allOk) result.appendChild(h('div', { class: 'callout callout-ok' }, h('strong', null, '校验通过：'), '已校验 ' + (Number(r.count) || 0) + ' 条审计记录，哈希链完整，已签署阶段的电子签名与内容一致。'));
      else if (r.chain_ok === false) result.appendChild(h('div', { class: 'callout callout-err' }, h('strong', null, '审计链校验失败：'),
        (r.key_missing ? '审计密钥缺失，无法校验。' : '自记录 #' + str(r.first_bad_id) + ' 起哈希链不一致。') + '（此前已校验通过 ' + (Number(r.count) || 0) + ' 条）请立即联系管理员 / QA 并保留现场，从备份核对。'));
      else result.appendChild(h('div', { class: 'callout callout-err' }, h('strong', null, '校验发现问题：'), '请查看下方各项结果，并联系管理员 / QA 保留现场、从备份核对。'));
      var anc = ANCHOR_LABEL[r.anchor_status] || [str(r.anchor_status) || '未知', 'muted'];
      result.appendChild(h('div', { class: 'table-wrap' }, h('table', { class: 'table' }, th(['检查项', '结果', '说明']),
        h('tbody', null,
          checkRow('审计哈希链', r.chain_ok, '完整', '不一致', '已校验 ' + (Number(r.count) || 0) + ' 条记录'),
          h('tr', null, h('td', { class: 'nowrap' }, '链头锚点'), h('td', null, MF.badge(anc[0], anc[1])), h('td', { class: 'small muted' }, '防止整体回滚或截断审计记录')),
          checkRow('防篡改触发器', r.triggers_ok, '在位', '缺失', '数据库层禁止修改 / 删除审计记录'),
          checkRow('电子签名完整性', r.signatures_ok, '全部完好', bad.length + ' 处异常', '已签署阶段的签名与当时内容哈希是否一致')))));
      if (bad.length) {
        result.appendChild(h('h4', { style: { margin: '14px 0 6px' } }, '签名完整性异常（' + bad.length + '）'));
        result.appendChild(h('div', { class: 'table-wrap' }, h('table', { class: 'table' }, th(['方法', '项目', '阶段', '修订', '问题']),
          h('tbody', null, bad.map(function (b) {
            return h('tr', { class: 'row-bad' },
              h('td', null, b.method_id ? [link(str(b.method) || ('方法#' + b.method_id), '/m/' + b.method_id, 'mono nowrap'), h('div', { class: 'small muted' }, str(b.method_name))] : '—'),
              h('td', null, b.project_id ? link(str(b.project) || ('项目#' + b.project_id), '/pr/' + b.project_id, 'mono nowrap') : '—'),
              h('td', null, dash(b.stage_title || b.stage)),
              h('td', null, b.revision === null || b.revision === undefined ? '—' : 'R' + str(b.revision)),
              h('td', { class: 'small' }, (b.problems || []).length ? h('ul', { style: { margin: 0, paddingLeft: '18px' } }, b.problems.map(function (x) { return h('li', null, str(x)); })) : '—'));
          })))));
      }
    }
    var verifyBtn = h('button', { class: 'btn', type: 'button', onclick: async function () {
      verifyBtn.disabled = true;
      MF.clear(result);
      result.appendChild(h('span', { class: 'muted' }, '校验中……'));
      try { showResult(await MF.api('GET', '/api/audit/verify')); } catch (e) { MF.clear(result); fail(e); }
      verifyBtn.disabled = false;
    } }, '校验审计链与签名');
    box.appendChild(h('div', { class: 'card' }, h('h3', null, '完整性校验'),
      h('p', { class: 'hint' }, '审计记录只追加，并以带密钥的哈希链相连；校验会从第一条起重新计算全部哈希，核对链头锚点与防篡改触发器，并逐一核对已签署阶段的电子签名。发现任何修改、删除或重排即报错。建议按风险定期执行并留存结果。'),
      h('div', { class: 'row' }, verifyBtn), h('div', { style: { marginTop: '10px' } }, result)));
    var holder = h('div', null, MF.loading());
    box.appendChild(holder);
    var rows = await MF.api('GET', '/api/audit?limit=300');
    MF.clear(holder);
    var t = auditTable(rows, { title: '全局审计追踪' });
    holder.appendChild(t.toolbar); holder.appendChild(t.body);
  }

  /* ---- document settings ---- */
  async function renderSettings(box) {
    var settings = null, caps = null, settingsMissing = false;
    try { settings = await MF.api('GET', '/api/admin/settings'); } catch (e) { if (e.status === 404 || e.status === 405) settingsMissing = true; else throw e; }
    caps = await MF.capabilities(true);

    var capBox = h('div');
    function drawCaps() {
      MF.clear(capBox);
      if (!caps.known) { capBox.appendChild(h('div', { class: 'callout callout-warn' }, '当前服务端未提供系统能力查询，无法判断 PDF 导出是否可用。Word（.docx）导出不受影响。')); return; }
      capBox.appendChild(caps.pdf
        ? h('div', { class: 'callout callout-ok' }, h('strong', null, 'PDF 导出：可用。'), caps.pdf_note ? ' ' + caps.pdf_note : '')
        : h('div', { class: 'callout callout-warn' }, h('strong', null, 'PDF 导出：不可用。'), ' ', caps.pdf_note || '未找到 LibreOffice（soffice）。请安装 LibreOffice，或在下方填写 soffice 可执行文件路径。', ' Word（.docx）导出不受影响。'));
    }
    drawCaps();
    box.appendChild(h('div', { class: 'card' }, h('h3', null, 'PDF 导出能力'), capBox,
      h('button', { class: 'btn btn-sm', type: 'button', onclick: async function () { caps = await MF.capabilities(true); drawCaps(); MF.toast('已重新检测', 'ok'); } }, '重新检测')));

    if (settingsMissing) {
      box.appendChild(h('div', { class: 'callout callout-warn' }, '当前服务端尚未提供“文档设置”接口（/api/admin/settings），暂时无法在此修改；升级后端后刷新页面即可。'));
      return;
    }
    settings = settings || {};
    var company = h('input', { class: 'input', maxlength: 100, value: str(settings.company_name), placeholder: '例如：XX 生物制药有限公司' });
    var footer = h('input', { class: 'input', maxlength: 200, value: str(settings.footer_text), placeholder: '例如：打印件未经控制，仅供参考' });
    var prefix = h('input', { class: 'input', maxlength: 40, value: str(settings.doc_prefix), placeholder: '例如：QC-AMD' });
    var soffice = h('input', { class: 'input', value: str(settings.soffice_path), placeholder: '留空则自动查找，例如 C:\\Program Files\\LibreOffice\\program\\soffice.exe' });
    var errBox = h('div', { class: 'callout callout-err', hidden: true, role: 'alert' });
    var save = h('button', { class: 'btn btn-primary', type: 'submit' }, '保存设置');
    box.appendChild(h('form', { class: 'card', novalidate: true, onsubmit: async function (ev) {
      ev.preventDefault();
      errBox.hidden = true;
      save.disabled = true;
      try {
        var r = await MF.api('PUT', '/api/admin/settings', { company_name: company.value.trim(), footer_text: footer.value.trim(), doc_prefix: prefix.value.trim(), soffice_path: soffice.value.trim() });
        MF.toast('文档设置已保存', 'ok');
        caps = await MF.capabilities(true); drawCaps();
        if (r && typeof r === 'object' && r.company_name !== undefined) { company.value = str(r.company_name); footer.value = str(r.footer_text); prefix.value = str(r.doc_prefix); soffice.value = str(r.soffice_path); }
      } catch (e) {
        if (e.status !== 401) { errBox.textContent = e.message || '保存失败'; errBox.hidden = false; }
      }
      save.disabled = false;
    } },
      h('h3', null, '受控文件设置'),
      h('p', { class: 'hint' }, '用于导出的 Word / PDF 受控文件的页眉页脚与编号。修改会写入审计记录，对之后生成的文档生效。'),
      h('div', { class: 'form-grid' },
        MF.field('公司名称', company, { hint: '显示在文件页眉。' }),
        MF.field('文件编号前缀', prefix, { hint: '用于文件编号，文件编号形如“方法编号-PLAN-Vn”。' }),
        h('div', { class: 'span2' }, MF.field('页脚文字', footer, { hint: '显示在页脚，例如“打印件未经控制”。' })),
        h('div', { class: 'span2' }, MF.field('LibreOffice（soffice）路径', soffice, { hint: '用于 Word 转 PDF。留空时依次查找 PATH 与默认安装目录。' }))),
      errBox, save));
  }
})();
