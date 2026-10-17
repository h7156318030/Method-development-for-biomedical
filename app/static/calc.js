/* MethodFlow - 统计计算器（calc.js）
 * MF.calc.open(onInsert)  打开计算器对话框；onInsert(rows) 把计算结果行 [{metric, value, criterion, verdict}] 写入结果表。
 * 计算在服务端 /api/calc/{name} 完成（app/stats.py，有单元测试）；这里只负责输入解析与展示。 */
(function () {
  'use strict';
  var MF = window.MF, h = MF.h;

  function nums(text) {
    return String(text || '').split(/[\s,;，；]+/).filter(Boolean).map(function (x) { return Number(x); });
  }
  function lines(text) {
    return String(text || '').split(/\r?\n/).map(function (l) { return l.trim(); }).filter(Boolean);
  }
  function bad(a) { return a.some(function (x) { return !isFinite(x); }); }

  var CALCS = [
    { key: 'summary', label: '描述统计（均值 / SD / RSD）', fields: [{ k: 'values', label: '数值（空格、逗号或换行分隔）', type: 'area', rows: 4 }],
      build: function (v) { var a = nums(v.values); if (bad(a)) throw new Error('含有非数字内容'); return { values: a }; } },
    { key: 'accuracy', label: '准确度（回收率 / 相对偏倚及其置信区间）', fields: [{ k: 'pairs', label: '每行一对：标称值 测得值', type: 'area', rows: 6, hint: '例：10 9.6' }],
      build: function (v) { return { pairs: lines(v.pairs).map(function (l) { var p = nums(l); if (p.length !== 2 || bad(p)) throw new Error('每行须是两个数字：' + l); return p; }) }; } },
    { key: 'precision', label: '精密度（重复性与中间精密度，ANOVA 方差分量）', fields: [{ k: 'groups', label: '每行一次运行（或一天/一个分析员）的重复结果', type: 'area', rows: 6, hint: '例：10.1 9.8 10.3' }],
      build: function (v) { return { groups: lines(v.groups).map(function (l) { var p = nums(l); if (!p.length || bad(p)) throw new Error('含有非数字内容：' + l); return p; }) }; } },
    { key: 'linearity', label: '线性（最小二乘回归）', fields: [{ k: 'xy', label: '每行一点：x y', type: 'area', rows: 6, hint: '例：1 2.1' }],
      build: function (v) { var x = [], y = []; lines(v.xy).forEach(function (l) { var p = nums(l); if (p.length !== 2 || bad(p)) throw new Error('每行须是两个数字：' + l); x.push(p[0]); y.push(p[1]); }); return { x: x, y: y }; } },
    { key: 'lod_loq', label: '检测限 / 定量下限（3.3σ/S 与 10σ/S）', fields: [{ k: 'slope', label: '斜率 S', type: 'text' }, { k: 'sigma', label: 'σ（回归残差 SD 或截距 SD；已知时填写）', type: 'text' },
        { k: 'blanks', label: '或：空白重复值（不填 σ 时用其 SD）', type: 'area', rows: 2 }],
      build: function (v) { var o = { slope: Number(v.slope) }; if (!isFinite(o.slope)) throw new Error('请填写斜率'); if (String(v.sigma).trim()) o.sigma = Number(v.sigma); else o.blanks = nums(v.blanks); return o; } },
    { key: 'tost', label: '等效性（配对 TOST：均值差的 90% CI 对比 ±界值）', fields: [{ k: 'pairs', label: '每行一对：参比 受试', type: 'area', rows: 6 }, { k: 'margin', label: '等效界值（±，与数据同单位）', type: 'text' }],
      build: function (v) { var a = [], b = []; lines(v.pairs).forEach(function (l) { var p = nums(l); if (p.length !== 2 || bad(p)) throw new Error('每行须是两个数字：' + l); a.push(p[0]); b.push(p[1]); }); return { reference: a, test: b, margin: Number(v.margin) }; } },
    { key: 'count_cv', label: '事件数与计数 CV（流式等按事件计数的百分比）', fields: [{ k: 'p', label: '目标百分比（%）', type: 'text' }, { k: 'events', label: '已采集事件数（可选）', type: 'text' }, { k: 'target', label: '目标 CV（%，可选）', type: 'text' }],
      build: function (v) { var o = { p_percent: Number(v.p) }; if (String(v.events).trim()) o.events = Number(v.events); if (String(v.target).trim()) o.target_cv = Number(v.target); return o; } }
  ];

  MF.calc = {
    list: CALCS,
    open: function (onInsert) {
      var sel = h('select', { class: 'select' }, CALCS.map(function (c) { return h('option', { value: c.key }, c.label); }));
      var form = h('div'), out = h('div', { style: { marginTop: '10px' } });
      var inputs = {}, last = null;
      function draw() {
        MF.clear(form); MF.clear(out); inputs = {}; last = null;
        var c = CALCS.filter(function (x) { return x.key === sel.value; })[0];
        c.fields.forEach(function (f) {
          var el = f.type === 'area' ? h('textarea', { class: 'textarea', rows: f.rows || 3, style: { fontFamily: 'monospace' } }) : h('input', { class: 'input', type: 'text' });
          inputs[f.k] = el;
          form.appendChild(MF.field(f.label, el, { hint: f.hint }));
        });
      }
      sel.addEventListener('change', draw);
      draw();
      var body = h('div', null, MF.field('计算项', sel), form,
        h('p', { class: 'small muted' }, '结果由程序按常规公式计算（t 分布与卡方分位数、ANOVA 方差分量、OLS 回归等），用于支持而非替代统计分析计划。'), out);
      return MF.modal({
        title: '统计计算器', body: body, width: 680,
        buttons: [{ label: '关闭', value: null }, {
          label: '计算', kind: 'primary', onClick: async function (ctl) {
            var c = CALCS.filter(function (x) { return x.key === sel.value; })[0];
            var v = {};
            Object.keys(inputs).forEach(function (k) { v[k] = inputs[k].value; });
            try {
              var payload = c.build(v);
              var res = await MF.api('POST', '/api/calc/' + c.key, payload);
              last = res; MF.clear(out);
              out.appendChild(h('table', { class: 'table' }, h('thead', null, h('tr', null, ['指标', '值', '说明'].map(function (t) { return h('th', null, t); }))),
                h('tbody', null, res.rows.map(function (r) { return h('tr', null, h('td', null, r.metric), h('td', null, r.value === null ? '—' : String(r.value)), h('td', { class: 'small muted' }, r.note || '')); }))));
              if (onInsert) {
                out.appendChild(h('button', { class: 'btn btn-sm', type: 'button', style: { marginTop: '6px' }, onclick: function () {
                  onInsert(res.rows.map(function (r) { return { metric: r.metric, value: r.value === null ? '' : String(r.value), criterion: '', verdict: '待评估' }; }));
                  MF.toast('已把 ' + res.rows.length + ' 行写入结果表（记得保存）', 'ok');
                } }, '把这些行写入结果表'));
              }
            } catch (e) { ctl.error(e.message || '计算失败'); }
            ctl.setBusy(false);
            return false;
          }
        }]
      });
    }
  };
})();
