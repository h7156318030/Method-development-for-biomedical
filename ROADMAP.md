# Roadmap and open work

This list is what is **not** built yet. It is a starting point for contributors, not a promise.
Each item lists the reason it matters; the order is a suggestion.

## Evidence and calculation

- **Data import beyond CSV.** Import plate-reader exports, Excel files and qPCR Cq tables; keep the file hash of each import; reusable column mappings.
- **Richer statistics.** 4PL fitting and relative potency, parallelism tests, sample-size planning. Each calculation should store its inputs, the code version and the output.

## Lifecycle

- **Validation, transfer, routine monitoring.** The same stage, review-gate and document engine applied to validation (protocol, execution, report), method transfer (comparability), routine monitoring (system suitability trends, OOS/OOT), periodic review, and retirement.
- **Change control for approved methods.** Impact assessment and change lists beyond the current revision copy (for example established conditions, post-approval change categories).
- **CTD section generation.** Draft sections 3.2.S.4.2 and 3.2.P.5.2 from approved data.

## Compliance and enterprise use

- **Training and qualifications.** Signers must hold a current training record; delegation during absence.
- **Account governance.** Account reviews, forced sign-out policy, SSO (LDAP or OIDC), multiple sites or departments.
- **Retention and archiving.** Retention periods, legal holds, archive export, restore-drill records.
- **Time.** Use of the server clock is recorded in UTC; no time-server synchronisation check yet.
- **Validation kit.** Editable IQ/OQ/PQ forms, risk assessment and SOP drafts (today only starting text in `docs/CSV验证模板/`).

## Daily use and collaboration

- **Editing locks and drafts.** Warn when two people edit the same section; autosave drafts.
- **Reporting.** Overview of overdue items, pending reviews and workload across methods; exports.
- **Importing existing methods.** From Word or Excel method documents, to create records for legacy methods.
- **Template governance.** Web-based template, checklist and knowledge-base editor; template version approval; organisation-specific templates.

## Engineering

- **Deployment.** Docker image and compose file with a reverse-proxy example; PostgreSQL option (SQLite suits a small team on one machine).
- **Full English.** The interface is translated; template body text (about 260 000 characters), the knowledge base, the guide pages and the generated document body are still Chinese. The data model would need "key + text per language".
- **Accessibility and mobile.** Keyboard operation, screen readers, contrast, narrow-screen tables.
- **AI assistance.** Read-only question answering and consistency checks first; suggestions only with explicit confirmation by a person.

## Known limitations today

- Not a validated GxP system; the automated tests are developer regression tests, not IQ/OQ/PQ.
- SQLite, single node: no high availability, limited concurrency.
- The built-in server speaks plain HTTP; use an HTTPS reverse proxy on a network.
- Word table-of-contents page numbers come from LibreOffice layout and may differ in Microsoft Word until the field is updated.
- Documents are not digitally signed or write-protected.
