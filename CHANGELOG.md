# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Requirement identifiers (URS-n) refer to `docs/URS_需求与测试追溯.md`.

## [0.4.0] - 2026-10-15

Database schema version 5 (upgrades in place from 3 and 4; a backup named `premigrate_v*_*.db` is written first).

### Added
- Result rows are judged automatically against their criteria (≥, ≤, ranges, ±); manual verdicts that differ are flagged before submission (URS-150).
- Statistics calculator: descriptive statistics, accuracy, precision (ANOVA variance components), linearity, LOD/LOQ, paired TOST equivalence, count CV; results can be written to the results table (URS-151).
- CSV import of result rows (URS-151).
- Registry of reagents, reference materials and consumables, and of instruments and equipment, with expiry and calibration alerts (URS-152).
- Run records verified by a second person (URS-152).
- Deviations: open major and critical deviations block submission of their step; closing requires an electronic signature by someone other than the person who opened it (URS-153).
- Audit-trail review with hash-chain and signature verification, re-authentication, and overdue reminders (URS-154).
- Inspection pack download (zip) with content, experiments, runs, deviations, signature manifest, audit trail, attachments with hashes, and generated documents (URS-155).
- Comments on each section with @mentions (URS-156); global search that respects project visibility (URS-157).
- Revisions of approved methods, keeping the earlier version (URS-158).
- Password expiry and password history (URS-159); optional change reason (URS-160).
- Background document generation with progress (URS-161); English export of fixed text in Word and PDF documents (URS-161, URS-163).
- E-mail and webhook notifications (WeCom, DingTalk, Feishu or generic JSON) (URS-162).
- Continuous integration (Windows, Python 3.9), CodeQL, Dependabot, issue and pull-request templates, and CSV validation starting templates.

### Changed
- Documents with unconfirmed content are labelled as drafts; the cover discloses unfilled required sections.
- Launchers read an optional `METHODFLOW_PYTHON` path instead of a fixed installation folder.

## [0.3.0] - 2026-10-15

Development version (database schema 3 → 4).

### Added
- Projects separate from methods; methods belong to a project and have their own team (URS-100 to URS-111).
- Ordered workflow: a step opens only after its prerequisites are approved (URS-130).
- Progressive completion: only core content blocks submission (URS-131).
- Confirmation of template pre-filled content; placeholders such as "example value" or "XX" block confirmation (URS-132, URS-133).
- In-app notifications, revision comparison for reviewers, batch experiment start/cancel, plan rescheduling (URS-140 to URS-144).
- Knowledge-base resource links with categories, search and link checking that refuses private addresses (URS-145, URS-146).
- English / Chinese switch for the user interface (UI-i18n).

## [0.2.0] - 2026-10-14

Development version.

### Changed
- Back-end hardening after an independent review: CSRF header, login lockout, safer audit records, input validation with uniform errors, and more (URS-80 to URS-97).

## [0.1.0] - 2026-10-14

First development version: method development workflow with gate reviews, electronic signatures, audit trail and Word export.
