# MethodFlow

[English](README.md) | [中文](README.zh-CN.md)

[![tests](https://github.com/h7156318030/Method-development-for-biomedical/actions/workflows/test.yml/badge.svg)](https://github.com/h7156318030/Method-development-for-biomedical/actions/workflows/test.yml)
[![license](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

**MethodFlow manages analytical method development from start to approval.** Projects group related methods. Each method goes through a nine-stage workflow with review gates, electronic signatures, a tamper-evident audit trail, and Word/PDF documents that are ready for review.

It is written for laboratories in biomedical and pharmaceutical development (for example cell and gene therapy QC) and runs on one computer or on a laboratory LAN. The interface is available in Chinese and English.

> **Not a validated GxP system.** MethodFlow is an auxiliary tool. Regulated use requires your own computerised-system validation (CSV / GAMP 5): risk assessment, IQ/OQ/PQ, SOPs, account management, backup and disaster recovery. The numerical criteria in the templates are **examples** and must be confirmed against your own ATP. Regulatory references marked "to be verified" must be checked against the current source. See [Limitations](#limitations).

Languages: the interface follows the browser language and can be switched at the bottom right ("中文 / EN"). Built-in templates and the knowledge base are in Chinese for now. The user manual is available in both languages: [English](docs/user-manual_en.md) and [中文](docs/用户手册_中文.md).

---

## Contents

- [What it does](#what-it-does)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [The workflow](#the-workflow)
- [Roles and separation of duties](#roles-and-separation-of-duties)
- [Electronic signatures and the audit trail](#electronic-signatures-and-the-audit-trail)
- [Documents (Word and PDF)](#documents-word-and-pdf)
- [Configuration](#configuration)
- [Data, backup and restore](#data-backup-and-restore)
- [Use on a laboratory network](#use-on-a-laboratory-network)
- [Tests](#tests)
- [Project layout](#project-layout)
- [Documentation](#documentation)
- [Contributing, security and license](#contributing-security-and-license)
- [Limitations](#limitations)

## What it does

- **Projects and methods.** A project (a product or pipeline container) holds several analytical methods. Each method has its own team and its own nine-stage development record.
- **Nine stages and six review gates.** From charter and analytical target profile (ATP) through technique selection, risk assessment (FMEA), development plan, feasibility experiments, robustness (DoE) and control strategy, to the development report and approval for validation. Gates require a reviewer and, for the plan, the control strategy and the report, an approver (QA).
- **Separation of duties.** Anyone who edited a stage cannot review or approve it. A reviewer and an approver must be different people.
- **Electronic signatures.** Signing requires the password to be entered again. Each signature stores the name, time (UTC), meaning, comment, revision number and a SHA-256 hash of the signed content.
- **Audit trail.** Saves, submissions, signatures, reopenings, document generation and more are recorded in a hash chain (HMAC). Changes made directly in the database are detected.
- **Experiments and results.** Experiments with design and acceptance criteria; result rows judged automatically against their criteria (≥, ≤, ranges, ±); a statistics calculator (descriptive statistics, accuracy, precision with ANOVA variance components, linearity, LOD/LOQ, paired TOST equivalence, count CV); CSV import.
- **Registry and run records.** Reagents, reference materials, instruments and equipment with lot numbers, expiry and calibration dates; run records that a second person verifies; alerts for expired items.
- **Deviations.** Open major or critical deviations block the submission of their stage; closing a deviation needs an electronic signature by someone other than the person who opened it.
- **Audit-trail review and inspection pack.** Periodic audit-trail review with hash-chain and signature checks (reminders are configurable); a one-click zip with the complete record for inspectors.
- **Templates.** Seven method types, including flow cytometry, chromatography, bioassays, cell-based potency, qPCR/ddPCR, immunochemical and binding assays, and a generic type. Each template pre-fills terminology, reference documents, FMEA, experiments, system suitability and checklists. Pre-filled content must be confirmed before it counts as completed.
- **Knowledge base.** Rules, pitfalls, how-tos and a library of resource links (regulations, pharmacopoeias, guidance documents), with a link checker.
- **Collaboration.** Comments on each section with @mentions, in-app notifications, optional e-mail and webhook notifications (WeCom, DingTalk, Feishu), global search, revisions of approved methods, and a change-reason option.
- **Security basics.** Password policy (length, letters and digits, optional expiry and history), account lockout after repeated failures, login rate limit, session timeouts, CSRF protection.

## Requirements

- Python 3.9 or newer. The versions in `requirements.txt` are verified on Python 3.9 (Windows).
- Windows is the primary target (launchers are `.bat` files). The Python code itself does not depend on Windows.
- Optional: [LibreOffice](https://www.libreoffice.org/) for PDF output. Without it you still get Word documents.

## Quick start

### Windows

1. Install Python 3.9+ and tick *Add python.exe to PATH*.
2. Double-click `start.bat`. It finds Python, offers to install the requirements, starts the server and opens the browser at <http://127.0.0.1:8780/>.
3. On the first visit there are **no default accounts**. Create the first administrator (username, display name, password of at least 10 characters with letters and digits). That account gets all four global roles.
4. Go to **Administration → User management**, create the other users and assign roles. New users must change their password at first sign-in.

If Python is not on the PATH, set the environment variable `METHODFLOW_PYTHON` to the full path of `python.exe` before running `start.bat`.

### Command line (any platform)

```bash
python -m pip install -r requirements.txt
python run.py                       # http://127.0.0.1:8780/
python run.py --port 8790           # another port
python run.py --data /path/to/data  # another data folder
python run.py --no-browser          # do not open a browser
```

Settings are read in this order (highest first): command-line options, environment variables (`METHODFLOW_DATA`, `METHODFLOW_HOST`, `METHODFLOW_PORT`), `config.json`, built-in defaults.

Stop the server with Ctrl+C. Data is not affected.

## The workflow

| # | Stage | Review gate | Who signs |
|---|---|---|---|
| 1 | Charter and background | none (submitting completes it) | — |
| 2 | Analytical target profile (ATP) | G1 | reviewer |
| 3 | Technique selection and reagent strategy | G2 | reviewer |
| 4 | Risk assessment (FMEA) | none | — |
| 5 | Development plan and experiment design | GP | reviewer, then approver |
| 6 | Feasibility and optimisation experiments | G3 | reviewer |
| 7 | Robustness, stability and parameter ranges (DoE) | none | — |
| 8 | Reference materials and control strategy | G4 | reviewer, then approver |
| 9 | Pre-validation and development report | G5 | reviewer, then approver |

- A stage opens only when its prerequisite stages have passed (configurable with `enforce_stage_order`).
- A stage that has been reopened makes the stages that depend on it stale. They must be recertified before the gates that cover them can be signed.
- After the plan is approved, new experiments must include a design and acceptance criteria.
- The submission check lists everything that blocks a submission, for example missing core content, unfinished experiments, high-risk FMEA items without controls, or no eligible reviewer.
- Criteria that still carry the "example value" marker produce a warning before the plan or the report is submitted. Confirm them against the ATP and remove the marker.

A step-by-step walkthrough is in the user manual, [English](docs/user-manual_en.md) (section 4) or [中文](docs/用户手册_中文.md). The app also has a *Beginner guide* in the left menu.

## Roles and separation of duties

**Global roles** (on the account): administrator, author (may create projects and methods), reviewer, approver (QA).

**Project roles**: owner, member, viewer.

**Method roles**: owner, author, reviewer, approver (QA), viewer. A person can hold more than one method role, with the restrictions described in the manual. Members of a method's team must already belong to the project. Project roles do not grant editing or signing rights on a method.

Contributors to a stage (anyone who saved, submitted, or edited its experiments or attachments) can never review or approve that stage.

## Electronic signatures and the audit trail

- Reviewing, approving, reopening, changing the lifecycle, and moving a method or project back to "in progress" all require the password to be re-entered.
- The server checks the revision number and the content hash shown to the signer. If the content changed in the meantime, the signature is refused.
- The audit trail records every change. Its hash chain is keyed with `data/.audit_key`. The administrator page can verify the chain and all signatures at any time.
- The electronic signature is a password re-authentication bound to the revision and content hash. It is **not** a digital certificate.

## Documents (Word and PDF)

On the **Documents** tab of a method, generate the **Development Plan** or the **Development Report**:

- A Word file (`.docx`) always; a PDF (`.pdf`) when LibreOffice is available. Generation takes about 20–60 seconds.
- The cover, controlled header and footer, revision history, table of contents, chapters, signature page and appendices follow the method's template.
- Each generation is classified as **approved** (all stages passed, no stale stages, signatures intact), **draft** (some stages not passed or stale), or **integrity check failed** (a signed content no longer matches its signature). Drafts are marked as not for use as approved documents.
- Document files are stored under `data/documents/<method code>/`.
- English export: choose *English* as the document language. Fixed text (cover, headers, chapter titles, signature page) is translated; template body text and what users wrote stay as entered.
- The files have no digital signature or write protection. Controlled release should follow your document-management procedure.

PDF generation uses LibreOffice. The program looks for `soffice` in this order: the setting in *Administration → Document settings*, `soffice_path` in `config.json`, the PATH, then the default installation folders.

## Configuration

Create `config.json` in the program folder if you need to change a setting. Write only the keys you change, as valid JSON. Restart the server after editing it.

| Key | Default | Meaning |
|---|---|---|
| `host` | `127.0.0.1` | Listening address. `0.0.0.0` makes the server reachable from the network |
| `port` | `8780` | Listening port |
| `session_hours` | `12` | Absolute session lifetime |
| `idle_minutes` | `60` | Idle time-out |
| `max_failed_logins` | `5` | Failed password attempts before the account is locked |
| `lock_minutes` | `15` | Lock duration |
| `enforce_stage_order` | `true` | Stages open in order |
| `strict_completeness` | `false` | `true` makes every required field block submission |
| `rpn_threshold` | `120` | FMEA: RPN at or above this needs a control |
| `severity_threshold` | `8` | FMEA: severity at or above this needs a control |
| `min_password_length` | `10` | Minimum password length (letters and digits are also required) |
| `password_max_days` | `0` | Password expiry in days (0 = never) |
| `password_history` | `5` | A new password must differ from the last N passwords |
| `audit_review_days` | `90` | Reminder interval for audit-trail reviews (0 = none) |
| `require_change_reason` | `false` | Require a written reason for changes to returned or reopened stages |
| `setup_token` | `""` | If set, the first administrator can be created only with this token. Recommended on a network |
| `allowed_hosts` | `null` | Accepted host names, for example `["lab.example.org"]` |
| `cookie_secure` | `null` | Send the session cookie with `Secure` (automatic when listening on a network address) |
| `soffice_path` | `""` | Path to LibreOffice's `soffice` |
| `pdf_enabled` | `true` | `false` produces Word files only |
| `smtp_host`, `smtp_port`, `smtp_user`, `smtp_password`, `smtp_from`, `smtp_tls` | — | E-mail notifications |
| `webhook_url`, `webhook_kind` | `""`, `generic` | Webhook notifications (`generic`, `wecom`, `feishu`, `dingtalk`) |
| `public_url` | `""` | Base address used in notification links |

The full list with explanations is in the user manual ([English](docs/user-manual_en.md), section 11.3; [中文](docs/用户手册_中文.md), section 11.3). **`config.json` may contain SMTP and webhook secrets. Never commit it.**

## Data, backup and restore

By default the data is in `data/` inside the program folder:

| Path | Content |
|---|---|
| `data/methodflow.db` | The SQLite database (users, projects, methods, signatures, experiments, audit trail, knowledge base) |
| `data/uploads/` | Attachments, with SHA-256 checks |
| `data/documents/` | Generated Word and PDF files |
| `data/backups/` | Database backups, created automatically at start-up and every 24 hours, and on demand |
| `data/.audit_key` | Key of the audit hash chain. **Keep it with the backups. Without it the audit chain cannot be verified or extended.** |
| `data/audit_head.json` | Audit-chain anchor |

- Back up with `backup.bat` (or `python tools/backup.py`), also with `--files` to include attachments and documents.
- Copy `data/.audit_key`, `data/audit_head.json` and the backup folder to a second location. Backups on the same disk do not protect against disk failure.
- Restore with `python tools/restore.py` (stop the server first). Restore checks the backup, keeps the current database as a `prerestore_*.db` copy, and does not touch uploads or documents.
- Do not copy `methodflow.db` while the server is running; use the backup tool.
- Forgotten administrator password (stop the server first):

  ```bash
  python tools/reset_admin.py --username admin
  ```

  This prints a one-time temporary password, which must be changed at the next login, and writes an audit record.

## Use on a laboratory network

By default only the local computer can reach MethodFlow. For several users:

- **Recommended:** keep the server on `127.0.0.1` and put an **HTTPS reverse proxy** (for example Caddy or nginx) in front of it. Set `allowed_hosts` to the proxy's host name and set `setup_token`.
- **Direct access over plain HTTP:** set `"host": "0.0.0.0"` and `"cookie_secure": false`, open the port in the firewall, and browse to `http://<server-ip>:8780/`. Plain HTTP sends passwords and sessions unencrypted: use it only on a trusted network.

The server clock is the time source for signatures and the audit trail. Keep it synchronised. Run one server per database.

## Tests

```bash
python -X utf8 -m unittest discover -s tests    # about 10 minutes, 163 tests
python tools/run_tests_report.py                # runs the tests and rewrites docs/自动化测试报告.md
```

Each test module uses its own temporary data folder. PDF tests are skipped when LibreOffice is not installed. Test names carry the requirement numbers (`test_URS<n>_…`) of [`docs/URS_需求与测试追溯.md`](docs/URS_需求与测试追溯.md). These are developer regression tests, not IQ/OQ/PQ.

## Project layout

```
app/           FastAPI back end (main, workflow, records, compliance, stats, docgen, db, auth, audit, …)
app/static/    Single-page front end in plain JavaScript (no build step, no CDN; works offline)
tests/         Automated tests, named after the requirements
tools/         Backup, restore, admin reset, audit anchor, migration, test report, translation helpers
docs/          User manuals (English and Chinese), requirements and traceability, design notes, validation templates
run.py         Start-up script
start.bat      Windows launcher
backup.bat     Windows backup launcher
```

## Documentation

| Document | Language |
|---|---|
| [`README.md`](README.md) (this file) | English |
| [`README.zh-CN.md`](README.zh-CN.md) | 中文概览 |
| [`docs/user-manual_en.md`](docs/user-manual_en.md) | English, complete user manual |
| [`docs/用户手册_中文.md`](docs/用户手册_中文.md) | 中文，完整用户手册 |
| [`docs/URS_需求与测试追溯.md`](docs/URS_需求与测试追溯.md) | Chinese (English summary at the top), requirements and test traceability |
| [`docs/V0.2需求与设计_项目方法分离与审批级文档.md`](docs/V0.2需求与设计_项目方法分离与审批级文档.md) | Chinese (English summary at the top), design notes |
| [`docs/前端契约.md`](docs/前端契约.md) | Chinese (English summary at the top), front-end and API contract |
| [`docs/后端加固清单.md`](docs/后端加固清单.md) | Chinese (English summary at the top), back-end hardening list |
| [`docs/调研与设计依据.md`](docs/调研与设计依据.md) | Chinese (English summary at the top), research and design basis |
| [`docs/CSV验证模板/`](docs/CSV验证模板/README.md) | English README; IQ/OQ/PQ, risk assessment and SOP starting points |
| [`CHANGELOG.md`](CHANGELOG.md) | English, release history |
| [`ROADMAP.md`](ROADMAP.md) | English, open work |

## Contributing, security and license

- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md). Help wanted: [ROADMAP.md](ROADMAP.md).
- Questions and bug reports: [SUPPORT.md](SUPPORT.md). Please remove real data and passwords from reports.
- Security problems: report privately through GitHub's **Report a vulnerability** option. See [SECURITY.md](SECURITY.md).
- Code of conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
- Licensed under the [Apache License 2.0](LICENSE). See [NOTICE](NOTICE).

## Limitations

- Not a validated GxP system. The automated tests are developer regression tests, not IQ/OQ/PQ.
- Example values in the templates are not validated criteria. The program warns about them but does not judge whether a number is reasonable.
- Regulatory and pharmacopoeial references in the templates and the knowledge base are not all checked against the current text. Those marked "to be verified" must be checked before use.
- Local accounts only: no SSO, no multi-factor authentication. Built-in HTTP only (use HTTPS in front on a network).
- Time comes from the server clock. There is no time-server check and no protection against clock changes.
- Single-node SQLite database: no high availability.
- The audit chain detects changes in the database. Someone who holds both the database and `.audit_key` can rebuild the chain.
- Word and PDF documents are not digitally signed or write-protected. PDF layout depends on LibreOffice.
- Lifecycle stages beyond development (validation, transfer, routine monitoring) are only recorded as status, without workflow templates. See [ROADMAP.md](ROADMAP.md).
