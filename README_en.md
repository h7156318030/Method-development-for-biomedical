# MethodFlow

**A web application for managing analytical method development — workflow, gate reviews with electronic signatures, audit trail, and approval-ready Word/PDF documents.**

> Status: V0.4, development stage only. MethodFlow is an auxiliary tool and is **not** a validated GxP system. Using it in a regulated environment requires your own computerised-system validation (CSV) assessment. See `docs/URS_需求与测试追溯.md` (Chinese) for the requirement/test traceability and the list of known gaps. No warranty.

## What it does

- **Projects and methods.** A project (product / pipeline level) contains analytical methods; each method follows a standard 9-step development process (charter → ATP → technique selection → risk assessment → development plan → experiments → robustness/DoE → control strategy → development report) with 6 review gates (G1, G2, GP, G3, G4, G5).
- **Guided, ordered process.** A step opens only after its prerequisites passed. New users get step-by-step guidance on every step and a "what to do next" card.
- **Review and e-signatures.** Separation of duties (editors can never review/approve their own work), signatures with password re-authentication bound to revision and content hash, locking after approval, reopening with a reason (dependent steps become stale), revision comparison for reviewers.
- **Progressive completion.** Core content blocks submission; other items only warn (and are marked `[To be filled]` in documents). Template pre-fill and example values must be explicitly confirmed — a document that still contains unconfirmed content is never labelled "approved".
- **Approval-ready documents.** Method Development Plan and Report as controlled `.docx` + `.pdf` (cover with signatures, revision history, table of contents, numbered chapters, appendices), driven by the template.
- **Templates.** Seven technique templates (flow cytometry, chromatography, bioassay, qPCR/ddPCR, immunochemical/binding, cell-based potency, generic) with FMEA seeds, experiment seeds, SST seeds and checklists.
- **Knowledge base.** Rules, pitfalls and how-tos (102 items) plus an editable library of resource links (regulations, agencies, pharmacopoeias, literature, tools) with a link health check.
- **Records.** Append-only, hash-chained audit log (HMAC), attachments with SHA-256 verification, in-app notifications, automatic backups.
- **Results and statistics (V0.4).** Result rows are judged automatically against their criteria (≥, ≤, ranges, ±); a statistics calculator (descriptive, accuracy, precision/ANOVA, linearity, LOD/LOQ, TOST equivalence, count CV) and CSV import feed the results table.
- **Registry, run records, deviations (V0.4).** Reagent/material and instrument registry with expiry / calibration alerts; run records verified by a second person; deviations whose closing is an e-signature and whose open major/critical items block step submission.
- **Compliance helpers (V0.4).** Periodic audit-trail review with hash-chain and signature verification, one-click inspection pack (zip), section comments with @mentions, global search, revisions of approved methods, password expiry/history, optional change reasons, e-mail / webhook notifications.
- **Languages.** The user interface can be switched between Chinese and English (button at the bottom right). Documents can be exported in English (cover, headers, chapter titles, signature page); template body text, knowledge-base items and what users wrote stay as written.

## Quick start

Requirements: Python 3.9+, and optionally LibreOffice (for PDF export).

```bash
pip install -r requirements.txt
python run.py            # opens http://127.0.0.1:8780/
```

On Windows you can double-click `start.bat`. On the first visit you create the administrator account (username 3–32 characters of letters, digits, `_ . -`; password at least 10 characters with letters and digits). There is **no default password**. Data lives in `./data` (database, uploads, documents, backups, `.audit_key`) — back up the whole folder.

By default the server listens on `127.0.0.1` only. For LAN use see the (Chinese) `README.md`: put it behind an HTTPS reverse proxy, set `allowed_hosts`, and read the notes on `cookie_secure`.

## Tests

```bash
python -m unittest discover -s tests
```

About 163 tests (about 9 minutes). `python tools/run_tests_report.py` writes `docs/自动化测试报告.md`.

## Repository layout

| Path | Content |
|---|---|
| `app/` | FastAPI backend (`main.py`, `workflow.py`, `docgen.py`, `auth.py`, `audit.py`, `db.py`, `templates_data.py`, ...) and the vanilla-JS single-page app in `app/static/` |
| `tests/` | unit/API tests (names carry requirement ids) |
| `tools/` | backup, restore, admin password reset, audit anchor, schema migration, i18n helpers |
| `docs/` | design notes, requirements/traceability, hardening list, hand-over notes, sample output |

## Contributing / translations

See `CONTRIBUTING.md` (ground rules, areas open for the community) and `SECURITY.md`. `docs/CSV验证模板/` holds starting-point CSV templates (Chinese).


The UI strings are written in Chinese in `app/static/*.js`. English comes from `app/static/i18n_en.js` (complete) and `app/static/i18n_extra_en.js` (hand-maintained; put new strings here). `python tools/i18n_missing.py` lists strings without a translation, and `python tools/i18n_add_extra.py <file>` merges a file of `中文<TAB>English` lines. Translating the template content (`app/templates_data.py`), the knowledge base (`app/kb_seed.py`, `app/kb_links.py`) and the guide pages is open work.

## License

Apache License 2.0 (see `LICENSE`). The built-in knowledge base and templates are published under the same license; regulatory documents themselves are not redistributed (only links).
