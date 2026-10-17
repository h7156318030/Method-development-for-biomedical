/* MethodFlow - 知识库资源链接页（links.js）  route: /kb/links
 * 法规、监管机构、药典与标准、文献、统计工具、培训社区的链接库。链接会变化，所以可以增加、编辑、停用，
 * 管理员可以“检查链接”（服务端请求公网地址，需联网）。 */
(function () {
  'use strict';
  var MF = window.MF, h = MF.h;

  function t(s) { return s; }
  function isEn() { return MF.lang === 'en'; }
  function pick(zh, en) { return isEn() && en ? en : zh; }
  function canEdit() { return MF.hasRole('admin', 'approver'); }
  function canAdd() { return MF.hasRole('admin', 'approver', 'author'); }

  function statusChip(l) {
    if (!l.checked_at) return MF.badge('未检查', 'muted');
    var c = l.status_code;
    if (c && c >= 200 && c < 400) return MF.badge('可访问 ' + c, 'ok');
    if (c === 403 || c === 412 || c === 429 || c === 999) return MF.badge('受限（站点可能正常）' + c, 'warn');
    return MF.badge('可能失效 ' + (c || (l.check_note || '无响应')), 'err');
  }

  function formDialog(cats, link) {
    var f = {
      category: h('select', { class: 'select' }, cats.map(function (c) { return h('option', { value: c.key }, pick(c.label, c.label_en)); })),
      title: h('input', { class: 'input', type: 'text', maxlength: 300 }),
      title_en: h('input', { class: 'input', type: 'text', maxlength: 300 }),
      url: h('input', { class: 'input', type: 'url', placeholder: 'https://', maxlength: 1000 }),
      org: h('input', { class: 'input', type: 'text', maxlength: 120, placeholder: '例如：ICH / FDA / NMPA' }),
      language: h('select', { class: 'select' }, [['', '（未指定）'], ['zh', '中文'], ['en', 'English'], ['ja', '日本語'], ['other', '其他']].map(function (x) { return h('option', { value: x[0] }, x[1]); })),
      description: h('textarea', { class: 'textarea', rows: 2, maxlength: 1000 }),
      description_en: h('textarea', { class: 'textarea', rows: 2, maxlength: 1000 }),
      tags: h('input', { class: 'input', type: 'text', placeholder: '多个标签用逗号分隔，例如：FDA, CAR-T' })
    };
    if (link) {
      f.category.value = link.category; f.title.value = link.title; f.title_en.value = link.title_en; f.url.value = link.url;
      f.org.value = link.org; f.language.value = link.language; f.description.value = link.description; f.description_en.value = link.description_en;
      f.tags.value = (link.tags || []).join(', ');
    }
    var body = h('div', null,
      MF.field('分类', f.category, { required: true }),
      MF.field('标题（中文）', f.title, { required: true }),
      MF.field('标题（英文）', f.title_en, { hint: '英文界面显示；留空则显示中文标题。' }),
      MF.field('网址', f.url, { required: true, hint: '须以 http:// 或 https:// 开头。链接变化时在这里更新即可。' }),
      h('div', { class: 'form-grid' }, MF.field('机构', f.org), MF.field('语言', f.language)),
      MF.field('说明（中文）', f.description),
      MF.field('说明（英文）', f.description_en),
      MF.field('标签', f.tags));
    return MF.modal({
      title: link ? '编辑链接' : '新增链接', body: body, width: 620,
      buttons: [{ label: '取消', value: null }, {
        label: '保存', kind: 'primary', onClick: async function (ctl) {
          var payload = {
            category: f.category.value, title: f.title.value, title_en: f.title_en.value, url: f.url.value, org: f.org.value, language: f.language.value,
            description: f.description.value, description_en: f.description_en.value,
            tags: f.tags.value.split(/[,，]/).map(function (x) { return x.trim(); }).filter(Boolean)
          };
          try {
            if (link) await MF.api('PUT', '/api/kb/links/' + link.id, payload);
            else await MF.api('POST', '/api/kb/links', payload);
            ctl.close(true);
          } catch (e) { ctl.error(e.message || '保存失败'); ctl.setBusy(false); return false; }
        }
      }]
    });
  }

  MF.route('/kb/links', async function (params, c) {
    MF.setCrumbs([{ label: '知识库', href: '/kb' }, { label: '资源链接' }]);
    var cats = await MF.api('GET', '/api/kb/link-categories');
    var state = { q: '', cat: '', all: false };
    var listBox = h('div');
    var info = h('div', { class: 'muted small' });

    var q = h('input', { class: 'input', type: 'search', placeholder: '搜索标题、机构、说明、标签', style: { maxWidth: '320px' } });
    var catSel = h('select', { class: 'select', style: { width: 'auto' } }, [h('option', { value: '' }, '全部分类')].concat(cats.map(function (x) { return h('option', { value: x.key }, pick(x.label, x.label_en)); })));
    var allBox = h('input', { type: 'checkbox' });
    var checkBtn = canEdit() && MF.hasRole('admin') ? h('button', { class: 'btn', type: 'button', onclick: async function () {
      checkBtn.disabled = true; checkBtn.textContent = '正在检查…（需联网，约 10–30 秒）';
      try {
        var r = await MF.api('POST', '/api/admin/kb-links/check', {});
        MF.toast('已检查 ' + r.checked + ' 条：可访问 ' + r.ok + '，异常或受限 ' + r.failed, r.failed ? 'warn' : 'ok');
      } catch (e) { MF.toast(e.message || '检查失败', 'err'); }
      checkBtn.disabled = false; checkBtn.textContent = '检查链接有效性';
      load();
    } }, '检查链接有效性') : null;

    c.appendChild(h('div', { class: 'page-head' }, h('div', null, h('h1', null, '资源链接'),
      h('p', null, '法规、监管机构官网、药典与标准、权威文献与数据库、统计工具和培训资源的入口。网址会随时间变化：可以新增、编辑、停用；管理员可一键检查有效性。')),
      h('div', { class: 'row', style: { gap: '8px' } }, canAdd() ? h('button', { class: 'btn btn-primary', type: 'button', onclick: async function () { if (await formDialog(cats, null)) { MF.toast('已新增链接', 'ok'); load(); } } }, '＋ 新增链接') : null,
        checkBtn)));
    c.appendChild(h('div', { class: 'toolbar', style: { display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap', marginBottom: '8px' } },
      q, catSel, canEdit() ? h('label', { class: 'small' }, allBox, ' 显示已停用') : null, h('span', { class: 'spacer' }), info));
    c.appendChild(listBox);

    var timer = null;
    q.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(function () { state.q = q.value.trim(); load(); }, 250); });
    catSel.addEventListener('change', function () { state.cat = catSel.value; load(); });
    allBox.addEventListener('change', function () { state.all = allBox.checked; load(); });

    function card(l) {
      var title = pick(l.title, l.title_en), desc = pick(l.description, l.description_en);
      var host = '';
      try { host = new URL(l.url).hostname; } catch (e) { host = l.url; }
      return h('div', { class: 'card', style: { marginBottom: '8px', opacity: l.active ? 1 : 0.55 } },
        h('div', { class: 'row', style: { gap: '8px', alignItems: 'center', flexWrap: 'wrap' } },
          h('a', { href: l.url, target: '_blank', rel: 'noopener noreferrer', style: { fontWeight: 600 } }, title || l.url),
          MF.badge(pick(l.category_label, l.category_label_en), 'info'),
          l.org ? MF.badge(l.org, 'muted') : null, l.language ? MF.badge(l.language, 'muted') : null,
          l.active ? null : MF.badge('已停用', 'warn'), h('span', { class: 'spacer' }), statusChip(l)),
        desc ? h('div', { class: 'small', style: { marginTop: '4px' } }, desc) : null,
        h('div', { class: 'small muted', style: { marginTop: '4px', wordBreak: 'break-all' }, 'data-notranslate': '' }, host + (l.checked_at ? '　·　' + MF.fmt.datetime(l.checked_at) : '')),
        h('div', { class: 'row', style: { gap: '6px', marginTop: '6px', flexWrap: 'wrap' } },
          h('a', { class: 'btn btn-sm', href: l.url, target: '_blank', rel: 'noopener noreferrer' }, '打开'),
          h('button', { class: 'btn btn-sm', type: 'button', onclick: function () {
            try { navigator.clipboard.writeText(l.url); MF.toast('网址已复制', 'ok'); } catch (e) { MF.toast(l.url, 'warn'); }
          } }, '复制网址'),
          canEdit() ? h('button', { class: 'btn btn-sm', type: 'button', onclick: async function () { if (await formDialog(cats, l)) { MF.toast('已保存', 'ok'); load(); } } }, '编辑') : null,
          canEdit() ? (l.active
            ? h('button', { class: 'btn btn-sm btn-danger', type: 'button', onclick: async function () {
              if (!(await MF.confirm('停用后不再对用户显示（可在“显示已停用”中恢复）。确定停用“' + title + '”？', { danger: true }))) return;
              await MF.api('DELETE', '/api/kb/links/' + l.id); load();
            } }, '停用')
            : h('button', { class: 'btn btn-sm', type: 'button', onclick: async function () { await MF.api('DELETE', '/api/kb/links/' + l.id + '?restore=1'); load(); } }, '恢复')) : null));
    }

    async function load() {
      MF.clear(listBox);
      listBox.appendChild(MF.loading());
      try {
        var rows = await MF.api('GET', '/api/kb/links?q=' + encodeURIComponent(state.q) + '&category=' + encodeURIComponent(state.cat) + (state.all ? '&all=1' : ''));
        MF.clear(listBox);
        info.textContent = rows.length + ' 条';
        if (!rows.length) { listBox.appendChild(h('div', { class: 'card empty' }, '没有匹配的链接')); return; }
        var last = null;
        rows.forEach(function (l) {
          if (l.category !== last) {
            last = l.category;
            listBox.appendChild(h('h3', { style: { margin: '14px 0 6px' } }, pick(l.category_label, l.category_label_en)));
          }
          listBox.appendChild(card(l));
        });
      } catch (e) { MF.clear(listBox); listBox.appendChild(MF.errorBox(e, load)); }
    }
    load();
  });
})();
