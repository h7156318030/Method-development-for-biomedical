/* MethodFlow boot: decide between first-run setup, login and the app shell. */
(function () {
  'use strict';
  var MF = window.MF;

  function fatal(e) {
    var root = document.getElementById('root');
    MF.clear(root);
    root.appendChild(MF.h('div', { class: 'login-wrap' }, MF.h('div', { class: 'login-card' },
      MF.h('h1', null, 'MethodFlow'),
      MF.errorBox(e, function () { location.reload(); }))));
  }

  function boot() {
    MF.api('GET', '/api/state', undefined, { noAuth: true }).then(function (app) {
      MF.state.app = app;
      if (app && app.needs_setup) { MF.showLogin('setup'); return; }
      return MF.api('GET', '/api/me', undefined, { noAuth: true }).then(function (r) {
        MF.state.user = r.user;
        MF.startApp();
      }, function (e) {
        if (e.status === 401) MF.showLogin(); else throw e;
      });
    }).then(null, fatal);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
