# Contributing to MethodFlow

Thank you for helping. MethodFlow is a small, dependency-light tool for analytical method development;
changes are judged on whether they keep the audit trail, electronic signatures and separation of duties intact.

## Quick start

1. Install Python 3.9 (the version the pinned dependencies are verified on) and the requirements:
   `python -m pip install -r requirements.txt`
2. Run a development server on an empty data folder of your own (never the folder of real data):
   `python run.py --data <empty folder> --no-browser`, then open http://127.0.0.1:8780/ and create the first administrator.
3. Run the automated tests (about 10 minutes; each test module uses its own temporary data folder):
   `python -X utf8 -m unittest discover -s tests`
   A single module: `python -X utf8 -m unittest discover -s tests -p test_v04.py`
4. `python tools/run_tests_report.py` runs the same tests and rewrites `docs/自动化测试报告.md`. Only do that in a PR that changes behaviour.

## Ground rules

- **Requirements and tests.** Every user-visible requirement gets a row in `docs/URS_需求与测试追溯.md` and an automated test named `test_URS<n>_<what it checks>`.
- **Audit, signatures, roles.** Do not weaken audit-trail, e-signature, password or separation-of-duties behaviour without an issue that explains why first.
- **Data and secrets.** Never commit real credentials, real projects, methods, documents, databases, `config.json` or `data/`. Test fixtures and examples must be invented.
- **Chinese and English UI.** Source strings are Chinese. The English text lives in `app/static/i18n_extra_en.js` (`exact` entries, or `pat` regular expressions for sentences with variables).
  - `python tools/i18n_missing.py` lists strings without a translation.
  - `python tools/i18n_add_extra.py <file>` merges a file of `中文<TAB>English` lines.
  - Wrap user-written names (projects, methods, file names) in `data-notranslate` so they are never translated.
- **Documents.** English document export covers fixed text only (cover, headers, chapter titles, signature page). Template body text stays Chinese for now (see `ROADMAP.md`).
- **Style.** Python: 4 spaces, UTF-8. Front end: plain ES2017 JavaScript and CSS, no build step, no CDN dependencies (the app must work offline). `.editorconfig` describes the rest.

## Pull requests

- Keep one topic per PR and fill in the template (URS row, tests, checklist).
- Run the full test suite before asking for review; CI runs it on Windows with Python 3.9.
- Commit messages in the imperative mood, for example `Add audit-trail review export`.

## Where help is most useful

See [ROADMAP.md](ROADMAP.md): validation / transfer / monitoring modules, a template editor, importing existing methods,
CTD section generation, 4PL and parallelism statistics, SSO, PostgreSQL / Docker, training matrix, and English template content.

## Security

Do not report security problems in public issues. Follow [SECURITY.md](SECURITY.md).

## License

By contributing you agree that your contribution is licensed under the Apache License 2.0 (see `LICENSE`).
