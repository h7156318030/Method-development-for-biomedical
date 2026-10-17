# MethodFlow User Manual (V0.4)

[English](user-manual_en.md) | [中文](用户手册_中文.md)

MethodFlow manages the whole development of an analytical method. A **project** (a product or pipeline container) is kept separate from a **method** (one specific analytical method). Each method advances through nine stages. At the review gates, a reviewer or approver must sign, re-entering the password, and the signature is bound to the content that was signed. Every operation goes into a tamper-evident audit trail. At the end you can generate the *Analytical Method Development Plan* and the *Development Report* as Word and PDF files, ready for review.

> **Read section 17, "Limitations and compliance statement", before use.** MethodFlow is not a validated GxP system. For regulated use, the company's QA must assess it under a CSV / GAMP 5 process and add IQ/OQ/PQ, SOPs, account management, backup and disaster recovery, and an assessment of compliance with electronic-signature rules. The numbers in the templates are examples. Regulatory clauses marked "to be verified" must be checked one by one.

Related documents: `docs\V0.2需求与设计_项目方法分离与审批级文档.md` (V0.2 design), `docs\前端契约.md` (v2 interface description), `docs\URS_需求与测试追溯.md` (requirements and test traceability), `docs\自动化测试报告.md` (latest test report), `docs\调研与设计依据.md`, `docs\后端加固清单.md`.

---

## 1. What problems it solves

- **Projects and methods are separate.** A project (for example "XX-CAR-T analytical method package") can hold several methods (for example "CD19/CD22 dual-target flow cytometry assay" or "residual DNA qPCR assay"), each going through the full development process.
- **Nine stages and six review gates.** From the analytical target profile (ATP) to approval for validation, organised along the lines of ICH Q14 and Q2(R2). At each gate someone must review or approve. The signature requires the password to be entered again and is bound to the data content at the time of signing.
- **Separation of duties.** A person who edited a stage cannot review or approve the same content. Reviewers and approvers are different people.
- **Audit trail.** Every save, submission, signature, reopening and document generation is recorded. The records are linked by a hash chain so that tampering can be detected. Attachments carry a SHA-256 hash.
- **Approval-grade documents.** Documents are produced from templates: a cover, revision history, table of contents, signature page, header and footer, as Word, and converted to PDF. Content that is not yet approved is automatically marked "draft".
- **Seven method-type templates.** Flow cytometry, chromatography (HPLC/CE/GC), bioassay (relative potency), cell-based function/potency, qPCR/ddPCR, immunochemical and binding methods (ELISA/SPR), and a generic type. Each template pre-fills terminology, reference documents, equipment and reagents, method conditions, FMEA (12 items), experiments (11 to 13), system suitability (SST) and checklists.
- **Knowledge base.** Experience, pitfalls and review findings are stored in the knowledge base and suggested to new methods by technique and stage.
- Data is kept on the local machine and **backed up automatically at start-up and every 24 hours**.

## 2. Quick start

**Environment:** Windows, Python 3.9 or newer (set the environment variable `METHODFLOW_PYTHON` to the path of python.exe if needed). To produce PDF you also need LibreOffice (see section 7). Without it you still get Word files, just no PDF.

1. Double-click `start.bat` (or run `python run.py` from a command prompt).
   - It looks for `METHODFLOW_PYTHON` (if set), then `py -3`, then `python`.
   - If required packages are missing, it asks whether to run `pip install -r requirements.txt` (this needs internet access or an internal mirror).
   - After the server starts, the browser opens automatically at `http://127.0.0.1:8780/`.
2. **First visit: there are no default accounts or passwords.** The page shows a setup screen where you create the first administrator: a username (3–32 characters: letters, digits, `_.-`), a display name, and a password of **at least 10 characters containing both letters and digits**. If `setup_token` is set in `config.json` during deployment, the setup screen asks for the same token, otherwise creation is refused. This prevents someone else from setting up the system first (see 11.3). The first account has the four global roles at once: administrator, developer, reviewer and approver. You are logged in immediately after creating it.
3. After logging in, go to **Administration → User management** to create accounts for colleagues and assign global roles. New accounts must change their password at their first login. **Create several accounts:** the gates require that the reviewer and approver are not the editors of the content, so one person cannot pass a gate alone. **Keep at least two administrator accounts.**
4. To stop: close the black `start.bat` window (or press Ctrl+C). The system is unavailable while stopped; the data is not affected.

Command-line options (anything after `start.bat` is passed to `run.py`):

```
python run.py                     # uses config.json / defaults (127.0.0.1:8780, data in .\data)
python run.py --port 8790         # another port
python run.py --data D:\mf_data   # another data folder
python run.py --no-browser        # do not open the browser automatically
python run.py --host 0.0.0.0      # reachable from the LAN; read section 12 first
```

Order of precedence: command-line options > environment variables (`METHODFLOW_DATA`, `METHODFLOW_HOST`, `METHODFLOW_PORT`) > `config.json` > built-in defaults.

## 3. Core concepts

### 3.1 Project (number `PRJ-year-sequence`)

A container at product or pipeline level: name, product, indication, development phase, start and end dates, status (in progress / on hold / completed / archived), project owner and project team. A project holds zero or more methods.

**Project team roles** (each person has one):

| Role | Permissions |
|---|---|
| Project owner | Edits project information and status, manages the project team, adds methods, adjusts the teams of its methods |
| Project member | May add methods (also needs the global "developer" or "administrator" role) and may view all methods in the project |
| Viewer (read-only) | May only view the project and its methods |

- Creating a project needs the global role "developer" or "administrator". The creator becomes the project owner.
- Setting a project to "completed" requires that it has no methods in progress. Changing a non-"in progress" project back to "in progress" needs a reason and the password.
- While a project is on hold or archived, its methods cannot be changed (they can still be read and documents generated).
- Once any stage of any method in the project is approved, the project's "product" field is frozen.

### 3.2 Method (number `AM-year-sequence`)

One specific analytical method: name, project, technique (template), measured attribute, sample matrix, intended use, method version (for example V0.1), lifecycle, development status (in progress / completed / archived / cancelled), method owner and method team. The nine-stage process, experiments, attachments, reviews, audit records and documents all belong to the method. Numbers are issued globally in year order, independent of the project.

**Method team roles** (one person may hold several, subject to the restrictions below):

| Role | Permissions |
|---|---|
| Method owner | Edits content; changes method information and status; manages the method team; reopens approved stages; changes the lifecycle |
| Author (developer) | Edits stage content, records and edits experiments, uploads attachments, submits and withdraws, records lessons learned |
| Reviewer | Signs reviews (subject to separation of duties) |
| Approver (QA) | Signs approvals; reopens approved stages; changes the lifecycle |
| Viewer (read-only) | May only view |

**Who can see a method:** the members of its team, plus any member of its project, plus administrators. **Who can edit or sign:** only the method team roles count; project roles have no effect on editing or signing. **Members of a method team must already be members of its project** (administrators excepted), and the method roles must match the global roles: owner and author need the global "developer" or "administrator" role; reviewer and approver need the corresponding global roles.

**Lifecycle** (a field of the method): development → validation → transfer → routine use → retired. Version 0.2 provides a complete workflow for the development stage only. The other lifecycle stages are recorded manually: the method owner or an approver uses "Change lifecycle" on the method page, enters a reason and the password, and the change is written to the audit trail (`method.lifecycle`). Workflow templates for validation, transfer and so on are planned for later versions.

**Cloning:** a method can be cloned into the same project or into another project (the permissions on the target project are the same as for adding a method). Cloning copies the measured attribute, matrix, intended use and the content of each chapter, and resets the checklist to not done. **It does not copy signatures, the team (only the creator is kept), experiments or results.**

### 3.3 Nine stages and review gates

| # | Stage (key) | Review gate | Who signs | Prerequisite stages |
|---|---|---|---|---|
| 1 | Charter and background (charter) | None (submitting completes it) | — | — |
| 2 | Analytical target profile, ATP (atp) | **G1 ATP review** | Reviewer | 1 |
| 3 | Technique selection and reagent strategy (tech) | **G2 technique and reagent review** | Reviewer | 2 |
| 4 | Risk assessment, FMEA (risk) | None (submitting completes it) | — | 2 |
| 5 | Development plan and experiment design (plan) | **GP development plan approval** | Reviewer → approver | 3, 4; also covers 1–4 |
| 6 | Feasibility and optimisation experiments (explore) | **G3 feasibility review** | Reviewer | 5 |
| 7 | Robustness, stability and parameter ranges, DoE (robust) | None | — | 6 |
| 8 | Reference materials and control strategy (control) | **G4 control strategy review** | Reviewer → approver | 7; covers 7 |
| 9 | Pre-validation and development report (report) | **G5 approval to enter validation** | Reviewer → approver | 8; covers 6, 7, 8 |

- A stage cannot be submitted while its prerequisite stage has not passed or has become stale.
- "Covers" means that the signature also binds the content hash of the covered stages. If a covered stage has not passed or is stale, the gate cannot be submitted.
- Stage states: not started → in progress → awaiting review → passed (stages with a gate) / completed (stages without one). If a reviewer returns a stage it becomes "returned", and it is submitted again after the changes.
- Before submission the system checks: missing required content, prerequisite stages not passed, experiments not closed, no eligible reviewer or approver, high-risk FMEA items without controls, checklist items that need evidence but have no explanation, and so on. Any of these blocks submission, and the page lists them one by one. Missing numerical criteria only produce a warning.

### 3.4 Separation of duties and contributors

- **Contributors** are the people who saved content for a stage, submitted it, edited its experiments, or uploaded or deleted attachments on its experiments. **A contributor can never review or approve that stage**, even if they have since been removed from the developer role.
- The two-step gates (GP, G4, G5) require the **reviewer first, then the approver**, and the reviewer and approver cannot be the same person. The same person cannot be both (owner or developer) and (reviewer or approver).
- If the method team has no eligible reviewer or approver at submission time, the system refuses the submission and tells you what is missing.
- While a stage is awaiting review, reviewers and approvers cannot be added or removed.

### 3.5 Electronic signatures

Reviews and approvals (accepting or returning), as well as "reopen", "change lifecycle", and "move a method or project back to in progress", all require the **current password to be entered again**. A signature record stores: the name, the time (UTC), the role, the meaning of the signature (for example "Review: I have checked the content of this stage and confirm that it is complete, accurate and meets the plan"), the comment, and **the revision number and the SHA-256 hash of the content at the time of signing**.

- When a stage is submitted, its content is snapshotted. A signing request must carry the **revision number and hash** the reviewer saw. The server compares them with the current values and refuses the signature if they differ ("The content has been updated; refresh and review again").
- The hash covers the stage content, its experiments and attachments, and the basic information of the method and project. If someone changes these in the database afterwards, the signature's integrity check fails, and the failure appears on the method page, in documents, and in the administration checks.
- A wrong password during signing is recorded in the audit trail and counts towards the lock-out limit.

### 3.6 Locking, reopening and "stale"

- Once a stage has passed it is **locked**: its content, experiments and attachments cannot be changed. After the plan is approved, the title, purpose, design and acceptance criteria of the experiments in the plan cannot be changed or deleted.
- To change a locked stage you must **reopen** it (enter a reason and the password; done by the method owner or an approver). The stage returns to "in progress", its revision number goes up by one, every **passed** stage that depends on it is marked **stale**, and any stage **awaiting review** is returned. A stale stage does not count as passed, so downstream stages and gates cannot be submitted, and documents generated then are drafts.
- After the upstream stage passes again, use **recertify** on the stale stage: even if the content has not changed, it must be reviewed and signed again.
- Returning, withdrawing and reopening all create new revisions. Signatures on earlier revisions stay in the history.
- If several people edit the same stage at once, the later save receives a "version conflict" message: refresh and make the changes again.

### 3.7 Example-value warnings

Criteria and acceptance criteria in the templates carry the marker "(example value, to be confirmed against the ATP)". **Before the development plan (plan) and report (report) stages are submitted, a warning appears if the stage data, or the acceptance criteria of experiments that are not cancelled, still contain this marker** (the count is shown). This is a warning and does not block submission. Confirm the values against the ATP and remove the marker, otherwise an example value would be approved as a criterion.

## 4. Typical process (one new method from start to finish)

1. **Prepare accounts** (administrator): Administration → User management. Create developers, at least one reviewer and at least one approver (QA).
2. **Create a project:** menu "Projects" → "New project". Enter the name, product, indication, development phase and dates, and add the **project team** (owner, members, viewers). The number `PRJ-year-sequence` is assigned automatically.
3. **Add the team:** the reviewer and approver of a method must already be project members, so add them on the project page under "Team" first.
4. **Create a method from a template:** on the project page click "Add method" (or Methods → New method and choose the project). Choose the **method-type template** (you can see its changelog and how much pre-filled content it has), enter the method name, measured attribute, sample matrix, intended use, method version and planned start, and choose the **method team** from the project members: author, reviewer, approver. The creator automatically becomes the method owner and an author. The system creates nine stages and pre-fills the ATP criteria, the technique scoring matrix, FMEA, draft experiments and SST, and example text for each chapter.
5. **Fill in each stage:** each section of a stage page shows its chapter number in the plan or report. Writing points and examples are under "Help / placeholder hints". Complete the checklist item by item. Missing required fields are listed under "Checks before submission".
6. **Charter and background** → submit → there is no gate, so it is completed directly.
7. **ATP** → submit → the reviewer approves or returns it on the page, entering the password to sign (G1). Criteria are best expressed as statistical intervals; a criterion without numbers gets a hint.
8. **Technique selection:** complete the scoring matrix and the reagent strategy → G2 review. **Risk assessment (FMEA):** enter S/O/D (1–10). Failure modes with RPN ≥ 120 or S ≥ 8 **must** have a control measure (the thresholds are configurable) → submitting completes the stage.
9. **Development plan:** on the "Experiments" page, register all planned experiments. Each must have a **design** and **acceptance criteria**. Fill in the statistical plan and so on → GP: the reviewer signs first, then the approver. **Experiments added after the plan is submitted or approved must also have a design and acceptance criteria** (otherwise they cannot be added). Such experiments are marked "added after plan" and listed separately in the document.
10. **Carry out experiments:** an experiment can be set to "in progress" only **after the plan is approved**. Enter a **conclusion** before marking it "completed". Cancelling requires a reason. Results tables, deviations and raw-data attachments are kept with the experiment.
11. **Feasibility → robustness → control strategy:** before each stage is submitted, all of its experiments must be completed (with a conclusion) or cancelled (with an explanation). Pass G3 and G4 in turn.
12. **Report stage:** summarise the results against the ATP and the validation strategy, record lessons learned → G5 approval to enter validation.
13. **Generate documents:** on the method's "Documents" page, generate the plan and report as Word and PDF (see section 8). You can do this at any time. Before everything is approved the output is a "draft"; after approval it is an "approved version".
14. The method owner sets the method status to "completed" (all stages must have passed or be completed, with no stale stages), and changes the lifecycle to "validation" etc. as needed. The project owner sets the project to "completed" after all its methods are finished. Lessons learned can be added to the knowledge base.

If something upstream has to change midway, use **reopen** (see 3.6) and handle the affected stages as prompted.

## 5. The seven method-type templates

Template version `1.1`. Each template has a changelog and a count of its pre-filled content.

| key | Name | FMEA seeds | Experiment seeds | SST seeds |
|---|---|---|---|---|
| `flow` | Flow cytometry (CAR-T expression / phenotype): spillover, FMO, event counts, hold times, Fc receptors, WRM and other experience | 12 | 12 | 8 |
| `hplc` | Chromatography (HPLC/CE/GC: assay, purity, impurities): chromatographic conditions, system suitability, forced degradation, peak purity, integration rules | 12 | 12 | 6 |
| `bioassay` | Bioassay (relative potency: 4PL / parallel line, protein products): reference standard, relative potency, PAR | 12 | 11 | 6 |
| `cell_based` | Cell-based function / potency (reporter gene, killing, cytokine release) | 12 | 13 | 6 |
| `qpcr` | qPCR / ddPCR (VCN, residual DNA, vector copies): standard curve and efficiency, NTC, inhibition control, LOD/LOQ | 12 | 13 | 6 |
| `elisa` | Immunochemical and binding methods (ELISA, SPR, MSD): coating, blocking, curve fitting, parallelism, hook effect | 12 | 13 | 6 |
| `generic` | Generic analytical method | 12 | 13 | 4 |

Each template pre-fills a glossary, reference documents (with document number and version columns), key reagents and equipment, an initial method-conditions table, ATP criteria rows, a technique scoring matrix, checklists (with cited clauses), FMEA, experiments (with example designs and acceptance criteria), and SST. **All values are examples and must be confirmed against the ATP. Where a cited clause is marked "to be verified", the user must check the original text clause by clause.** The template content is copied into a method when the method is created, so changing a template later does not affect existing methods.

## 6. Documents: drafts, approved versions and integrity

On the method's **Documents** page you can generate:

| Type | Contents | Document number |
|---|---|---|
| *Analytical Method Development Plan* | Charter, ATP, technique selection, risk assessment, development plan (15 chapters, stable chapter numbers) | `[prefix]AM-2026-001-PLAN-V1` |
| *Analytical Method Development Report* | The plan plus summary and conclusions, summary of experimental results, robustness / DoE and PAR/MODR, control strategy, draft method description (convertible to an SOP), deviation list, open issues and validation recommendations | `[prefix]AM-2026-001-RPT-V1` |

Layout: cover (title, method name and number, project, version, status, names and dates of author, reviewer and approver), revision history, table of contents, controlled header (company name, document title, document number, version, status), footer (page X of Y, footer text, generation time), chapters for each stage (table headers repeat), Gantt chart and FMEA figure, signature page (gates, roles, names, meanings, dates, revision number, first 12 characters of the data hash, signature integrity), and appendices (checklists, summary of experimental results, attachment list with the first 12 characters of each SHA-256, references). Empty required sections appear as "[to be completed]" highlighted in drafts.

**Three states** (decided when the document is generated; shown on the cover, in the header and in the history list):

| State | Meaning |
|---|---|
| **Approved version** | All stages in the document have passed or are completed, none is stale, and signatures are intact |
| **Draft (contains unreviewed content)** | Some stage has not passed or is stale. The document is marked "DRAFT — not for use as an approved document" and lists the stages that have not passed. Do not use it as an approved document |
| **Integrity check failed** | The content of a signed stage no longer matches the hash at signing. Investigate with the administrator or QA first. Do not use the document |

- Each generation gets a new version number V1, V2, … (counted separately for each type) and is recorded in the audit trail. One generation produces both `.docx` and `.pdf` with the same name and different extensions.
- Files are saved in `data\documents\<method number>\`, with names such as `AM-2026-001_方案_V1_20261014093000.docx`.
- At most 6 generations per method per minute (`docs_per_minute`). If the method data changes during generation, you are asked to retry.
- The files have **no digital signature and no write protection**. Controlled release must follow your company's document-control procedure.

### 6.1 Document settings (Administration → Document settings, administrators only)

| Item | Effect |
|---|---|
| Company name | Shown in the header; empty by default |
| Footer text | Default "Uncontrolled when printed" |
| Document number prefix (`doc_prefix`) | Added in front of document numbers. Only letters, digits and `. _ / -`, up to 20 characters. For example `QC-` gives `QC-AM-2026-001-PLAN-V1` |
| soffice path | Location of LibreOffice's `soffice.exe`; empty = search automatically |

Saving takes effect immediately for documents generated afterwards, and is written to the audit trail (`settings.update`).

## 7. PDF output (LibreOffice)

PDF is produced by converting the Word file with LibreOffice (`soffice --headless --convert-to pdf`):

1. Install LibreOffice (<https://www.libreoffice.org>). The program looks for `soffice` in this order: the "soffice path" set on the Administration page → `soffice_path` in `config.json` → the system PATH → default installation locations such as `C:\Program Files\LibreOffice\program\soffice.exe`. If it is installed elsewhere, enter the path under "Administration → Document settings".
2. The conversion needs a Chinese font on the system (Windows includes one).
3. **Generating one document (with PDF) takes about 20–60 seconds**, and the first start of LibreOffice is slower. The button shows "Generating, about 20–60 seconds…"; do not click it again. A conversion longer than `pdf_timeout_sec` (default 120 seconds) is abandoned, and only the Word file is kept.
4. If LibreOffice is not installed, the conversion fails or times out, or `pdf_enabled=false` is set, only the Word file is produced. The page gives the reason. This is not treated as an error.
5. To make the static table-of-contents page numbers in the PDF correct, the conversion runs twice (the bookmarks of the first PDF are read with `pypdf`). `pypdf` is listed in `requirements.txt`.

## 8. Steps to generate the plan and the report

1. Open the method and go to the **Documents** page. Two cards (plan and report) show the state of the stages they contain, and say whether the output is a draft or an approved version, and whether example-value warnings remain.
2. Click "Generate plan" or "Generate report" and wait for it to finish. Then "Download Word" and "Download PDF" appear.
3. The history groups files by generation batch and shows the version, state, time, the person who generated it, the SHA-256 of each file and the current signature integrity.

## 9. Where the data is

By default everything is in `data\` (change it with `--data` or the `METHODFLOW_DATA` variable):

| Path | Content |
|---|---|
| `data\methodflow.db` (and `-wal`, `-shm`) | The database: users, projects, methods, stages, signatures, experiments, audit trail, knowledge base … |
| `data\uploads\<method id>\` | Uploaded attachments (file names start with the first 16 characters of the content hash) |
| `data\documents\<method number>\` | Generated Word and PDF files |
| `data\backups\` | Database backups (`methodflow_time_label.db`, `files_time.zip`, `prerestore_*.db`, `premigrate_*.db`) |
| `data\.audit_key` | **Key of the audit hash chain. It is not in the database and is not backed up automatically. It must be kept together with the database backups.** If it is lost, the audit chain cannot be verified, cannot be extended, and cannot be rebuilt |
| `data\audit_head.json` | Audit-chain "anchor" (the position of the chain head), used to detect a rollback of the whole chain or deletion of its end |

**Do not copy `methodflow.db` directly while the program is running**, because data in the WAL file may be missed. Use the backup function.

## 10. Backup and restore

- **Automatic backups:** one at program start (label `startup`, keeps `backup_keep_startup` copies, default 10), then every 24 hours while the program keeps running (label `daily`). Manual and automatic backups share `backup_keep` (default 30 per label group).
- **Manual backup:** Administration → Data backup → "Back up now", or double-click `backup.bat` (it can run while the server is running; the backup is checked for integrity and audit chain straight away). `python tools\backup.py --files` also packs `uploads` and `documents` into `files_time.zip` (these are not cleaned up automatically).
- **Keep copies of these files separately** (`backup.py` handles only the database and the zip, and **does not copy `.audit_key`**): `data\.audit_key`, `data\audit_head.json`, and copy `data\backups` regularly to another disk or network location. A backup on the same disk does not protect against disk failure.
- **Restore** (close MethodFlow first):

  ```
  python tools\restore.py                       # list available backups
  python tools\restore.py methodflow_20261014_093000_manual.db
  ```

  The script: ① refuses if the server is still running (if you started with `--port`, give the same `--port` when restoring); ② checks the backup (it opens, passes the integrity check, has a valid structure version and a valid audit chain; if `.audit_key` is missing it says so clearly). If the check fails, it refuses and changes nothing; ③ saves the current database as `data\backups\prerestore_time.db` so it can be rolled back; ④ replaces the database; ⑤ checks again. `uploads` and `documents` **are not changed**. After restoring, start the program, click "Check audit chain and signatures" on the administration page, and spot-check attachments with "Check integrity".
- **Audit anchor:** `python tools\audit_anchor.py` shows the state of the chain, the anchor and the triggers. After restoring an old backup, or if the anchor is lost, the audit check reports "anchor missing or changed". When the chain itself passes its check, `python tools\audit_anchor.py --reset --yes` rebuilds the anchor from the current chain head (this action is itself written to the audit trail). If `.audit_key` is lost it cannot be rebuilt; it must be taken from a backup.
- Restore drills, retention periods, off-site copies and recovery time objectives are set by company procedures.

## 11. Administrator tools and config.json

### 11.1 Forgotten administrator password: `tools\reset_admin.py`

Close MethodFlow first, then:

```
python tools\reset_admin.py                    # if there is only one administrator it is chosen automatically; with several, the list is shown and --username is required
python tools\reset_admin.py --username admin
python tools\reset_admin.py --data D:\mf_data --port 8790   # if the data folder or port is not the default
```

It generates a random temporary password (shown on screen once), enables and unlocks the account, clears all its sessions, requires a password change at the next login, and writes `user.password_reset_offline` to the audit trail (including the operating-system account and host name). It refuses to run while the server is running.

### 11.2 Old database: `tools\migrate_v1_to_v2.py`

Databases from V0.1 and earlier ("project = method", structure version 1 or 2) cannot be started directly; the program says so. Close the program, then:

```
python tools\migrate_v1_to_v2.py              # converts .\data (--data for another folder, --yes to skip confirmation)
```

Each old project becomes one method, and a project with the same name is created automatically as its container. The old number `MD-…` is kept in the method as `meta.legacy_code`. Signatures and the audit trail are kept as they were and remain verifiable. The conversion is done in a new file and checked, and only replaces the database on success. The original database is kept as `data\backups\premigrate_time.db` (together with copies of the key and the anchor).

### 11.3 config.json

Create a `config.json` in the program folder. **Write only the keys you want to change**; it must be valid JSON, and **changes take effect after a restart**.

```json
{
  "host": "127.0.0.1",
  "port": 8780,
  "idle_minutes": 30,
  "rpn_threshold": 100
}
```

All keys and their defaults (from `app\config.py`):

| Key | Default | Meaning |
|---|---|---|
| `host` | `127.0.0.1` | Listening address. The default allows only this computer; `0.0.0.0` means all network interfaces (see section 12) |
| `port` | `8780` | Listening port |
| `session_hours` | `12` | Absolute session lifetime in hours; afterwards you must log in again |
| `idle_minutes` | `60` | Idle time-out in minutes |
| `max_failed_logins` | `5` | Number of consecutive wrong passwords before the account is locked (login and electronic-signature passwords both count) |
| `lock_minutes` | `15` | Lock duration in minutes |
| `login_rate_max` | `10` | For each "user name + source IP", more failed logins per minute than this return HTTP 429 |
| `backup_keep` | `30` | Number of manual, daily and other backups kept in each group; older ones are deleted |
| `backup_keep_startup` | `10` | Number of start-up backups kept separately |
| `enforce_stage_order` | `true` | Standard process: a stage opens for editing only after its prerequisite stage has passed. Set `false` to remove the order restriction |
| `strict_completeness` | `false` | `false`: only when the **core content** is missing (for example ATP intended use, measured attribute and criteria, the FMEA table, the development-stage plan of the plan) is submission blocked; other required fields that are empty only give a "not yet filled in" warning (shown to reviewers, written to the audit trail, and marked red as [to be completed] in documents). `true`: every required field must be completed before submission |
| `rpn_threshold` | `120` | FMEA: failure modes with RPN (S×O×D) at or above this value must have a control measure |
| `severity_threshold` | `8` | FMEA: failure modes with severity S at or above this value must have a control measure regardless of RPN |
| `min_password_length` | `10` | Minimum password length (letters and digits are also required) |
| `max_upload_mb` | `200` | Size limit of one attachment in MB; above it, HTTP 413 |
| `max_json_mb` | `20` | Request-body limit in MB for all interfaces except uploads; above it, HTTP 413 |
| `docs_per_minute` | `6` | Maximum number of document generations per method per minute (Word + PDF count as one); above it, HTTP 429 |
| `setup_token` | `""` | If not empty, the first setup (creating the first administrator) must supply the same setup token. **Strongly recommended for a first deployment on a LAN**; it can stay set after setup |
| `allowed_hosts` | `null` | Accepted Host header names, for example `["mf.corp.example"]`. `null` = automatic (when listening on this computer only 127.0.0.1 and localhost are accepted; when listening on another address there is no restriction) |
| `cookie_secure` | `null` | Whether the session cookie carries `Secure`. `null` = automatic (true when the listening address is not this computer) |
| `soffice_path` | `""` | Location of LibreOffice's soffice. A value set on the "Document settings" page takes precedence; empty = search automatically |
| `pdf_enabled` | `true` | `false` = never call LibreOffice; output Word only |
| `pdf_timeout_sec` | `120` | Timeout in seconds for one PDF conversion |

The environment variables `METHODFLOW_DATA` (data folder), `METHODFLOW_HOST` and `METHODFLOW_PORT` take precedence over `config.json`, and command-line options take precedence over both. Changing a threshold affects only later submission checks; existing signatures are not affected.

## 12. Use on a laboratory network

By default only this computer can reach the system (`127.0.0.1`). For several users there are two options:

- **Recommended:** keep the service listening on this computer, and use an **HTTPS reverse proxy** (Caddy, nginx, IIS with ARR, etc.) to offer `https://…` to users. The proxy forwards to `http://127.0.0.1:8780`. The firewall allows only the proxy port. In `config.json` set `"allowed_hosts": ["your-domain"]` (the proxy must pass the original Host header), and set `setup_token`. Access over HTTPS makes the `Secure` cookie meaningful, so `cookie_secure` should stay `true` (when listening on this computer behind an HTTPS proxy, set it to `true` manually).
- **Direct access:** set `"host": "0.0.0.0"` in `config.json` (or `python run.py --host 0.0.0.0`), allow port 8780 through the Windows firewall, and colleagues browse to `http://server-IP:8780/`. **Note: when listening on a non-local address, `cookie_secure` becomes true automatically, and the browser does not send a `Secure` cookie over ordinary HTTP, so login "succeeds" and then immediately logs out. Over plain HTTP you must also set `"cookie_secure": false`.**

**Warning:** over plain HTTP, passwords and sessions travel unencrypted on the network. Use this only on a trusted internal network with a firewall, and never expose it to the internet. The server clock is the time source for all signatures and audit records, so keep it synchronised with a time server. MethodFlow is a single-machine SQLite program: if many users are online at the same time, assess performance first. Run one instance per server. The server computer must stay switched on and running `start.bat`.

## 13. Knowledge base and extensions

### 13.1 Knowledge base

- Day to day: on the **Knowledge base** page click "+ New entry" (developers and administrators). Choose the type (rule / pitfall / how-to / reference / lesson learned), enter the title, content, tags, and the technique and stage it applies to. On a method's "Knowledge" page you can "Record experience" directly, which links the entry to that method and stage. Administrators and approvers can deactivate entries (nothing is physically deleted, and the change is audited).
- **Synchronise built-in knowledge:** built-in entries come from `app\kb_seed.py` (version 0.2 added writing points, common review findings, checklist clauses and so on). At each start the program adds any missing built-in entries, matched by title. After an upgrade, administrators can also click "Synchronise built-in knowledge" on the knowledge base page. Synchronisation only adds what is missing; it **never overwrites or restores** entries that users created, edited or deactivated. It can be repeated safely and is recorded as `kb.sync`.

### 13.2 Adding a method type (technique template)

In `app\templates_data.py`, edit the `TECHNIQUES` dictionary: copy the `"generic"` or `"hplc"` entry and add it under a new key (letters and digits only). The skeleton below lists only the keys; follow the format of the existing entries:

```python
TECHNIQUES["mykey"] = {
    "label": "name shown in the interface",
    "desc": "one or two sentences on the scope",
    "changelog": [...],       # update record of this template
    "matrix": {"options": ["candidate technique A", "candidate technique B"],
               "criteria": [("ability to meet the ATP", 5), ("throughput", 2)]},          # (criterion, weight)
    "atp_rows": [...],        # ATP criteria rows
    "extra_checklist": {"atp": [ck("my1", "checklist item text", "guidance", "source", True)],
                        "tech": [...], "plan": [...], "robust": [...], "control": [...]},
    "fmea": [...], "experiments": [...], "sst": [...],
    "ph": {...},              # placeholder hints for each section
    "seeds": {...},           # pre-filled rows: terminology, reference documents, reagents and equipment, method conditions, etc.
}
```

The safest approach is to copy an existing entry and rewrite it, rather than writing the structure from memory. Note:

- The checklist item `key` must be unique within a template.
- **Template content is copied into a method when the method is created**, so changing a template affects only methods created **afterwards**.
- After editing, update `TEMPLATE_VERSION` and the template's changelog, restart the server, and the new type appears under "New method".
- Run `python tools\run_tests_report.py` to regress (`tests\test_templates.py` and `tests\test_projects.py` check the structure and pre-filled content of each template; add the new key to those tests if needed).
- If you cannot confirm the original text of a cited clause, write "see the relevant chapter of xx guidance (clause to be verified)". Do not invent clause numbers.
- Changing a template is a change: record it under your change-control procedure.

The stages themselves (the nine stages, the gates and the checklist items) are defined in `common_stages()` in the same file. Changing them affects every new method, so be careful.

## 14. Upgrading

1. Close the program first, make a backup and copy it to a safe place (`backup.bat`, with `--files` to pack attachments and documents; keep `.audit_key` and `audit_head.json` as well).
2. Overwrite the program files with the new version (`app\`, `tools\`, `run.py` and so on). **Do not overwrite `data\` or `config.json`.**
3. If `requirements.txt` has changed: `python -m pip install -r requirements.txt`.
4. Run `python tools\run_tests_report.py` to regress, and start the program after it passes.
5. The database has a structure version number. If the database is newer than the program, the program refuses to start. For the V0.1 database see 11.2.

## 15. Frequently asked questions

| Symptom | What to do |
|---|---|
| Double-clicking `start.bat` says Python cannot be found | Install Python 3.9+ and tick "Add python.exe to PATH", or make sure Python is on the PATH (or set the environment variable `METHODFLOW_PYTHON`) |
| A required package is missing | Answer Y when `start.bat` asks, or run `python -m pip install -r requirements.txt` |
| "Port 8780 is already in use" | A MethodFlow may already be running (open the address directly), or another program uses the port: `python run.py --port 8790` |
| The browser did not open automatically | Open the address shown in the window manually (default `http://127.0.0.1:8780/`) |
| The database is an old version | See 11.2. Convert it with `tools\migrate_v1_to_v2.py`, after making a backup |
| A colleague cannot open the system | The default listens on this computer only. See section 12, and check the firewall, the IP address and `allowed_hosts` |
| Over HTTP on the LAN, login works then drops at once | When listening on a non-local address the cookie carries `Secure` by default. Over plain HTTP set `"cookie_secure": false`; better still, use an HTTPS reverse proxy |
| "Host name not allowed" (HTTP 400) | When listening on this computer only 127.0.0.1 and localhost are accepted. When using a domain name or a reverse proxy, add the domain to `allowed_hosts` |
| The setup page asks for a "setup token" | `config.json` has `setup_token` set; enter the same value |
| The account is locked | Wait `lock_minutes` minutes, or ask an administrator to reset the password (the user must change it at the next login) |
| The administrator forgot the password | Another administrator resets it. If there is no other administrator, use `tools\reset_admin.py` (11.1) |
| "Submission blocked" | The page lists the reasons: missing required content, prerequisite stage not passed, experiments not closed, no eligible reviewer or approver, high-risk FMEA item without a control, … |
| "Experiment lacks design or acceptance criteria" / adding an experiment is refused | After the development plan is submitted or approved, a new experiment must have both a design and acceptance criteria. The plan review also checks all experiments that are not cancelled |
| Signing says "The content has been updated; refresh and review again" | The stage content changed after you opened the page. Refresh, review again, then sign |
| "Version conflict" | Someone else has updated it. Refresh and make the changes again |
| The "Generate" button keeps spinning | Generation with PDF takes 20–60 seconds. If it passes `pdf_timeout_sec`, PDF is abandoned and only Word is kept. If still no response, check for a leftover `soffice` process |
| Only a Word file, no PDF | LibreOffice is not installed, the path is wrong, `pdf_enabled=false`, or the conversion failed. The page gives the reason; see section 7 |
| The document state is "draft" | A stage has not passed or is stale. Look at the stages listed on the Documents page; handle stale stages with "Recertify" |
| The document state is "integrity check failed" | Signed content no longer matches the signature. Treat it as a data-integrity event: stop using the document and ask QA to investigate |
| "File missing, restore from backup" | An attachment or document file is not in `data\uploads` or `data\documents`. Restore it from `files_*.zip` or an off-site copy into its original place |
| Attachment "integrity check" fails | The file on disk differs from its hash at upload. Investigate under your company procedure |
| Audit chain check fails | Records in the database were changed or damaged. Keep the evidence, restore from a backup and inform QA |
| Audit check reports "anchor missing or changed" | Common after restoring an old backup or copying the database. If the chain check passes, rebuild with `tools\audit_anchor.py --reset --yes` |
| The audit key is reported missing | `data\.audit_key` is lost. It must be taken from a backup; it cannot be regenerated |
| Chinese fonts look wrong in Word | Documents specify Microsoft YaHei / SimSun. If the target computer lacks a font, Word substitutes one. Chart fonts come from the Chinese fonts installed on the computer |

## 16. Automated tests

```
cd /d <program folder>
python -m unittest discover -s tests         # runs all tests, about 10 minutes (163 tests)
python tools\run_tests_report.py             # runs all tests and rewrites docs\自动化测试报告.md
```

The tests run in temporary data folders and never touch the real `data\`. The PDF tests in `tests\test_docgen.py` are skipped on a computer without LibreOffice. The report `docs\自动化测试报告.md` contains the date, dependency versions, the result of each test (with its URS number), the requirements not covered, and SHA-256 fingerprints of the tested files. Run it again after changing the program or a template. The `URSnn` numbers in test names refer to the requirement numbers in `docs\URS_需求与测试追溯.md`.

## 17. Limitations and compliance statement

- **MethodFlow is not a validated GxP system. For regulated use, the company's QA must assess it under a CSV / GAMP 5 process and add IQ/OQ/PQ, SOPs, account management, backup and disaster recovery, and an assessment of compliance with electronic-signature rules.**
- **The numbers in the templates (criteria, sample sizes, limits, times and so on) are examples and must be confirmed against the ATP and product knowledge of the method.** The system only warns about markers that still say "example value, to be confirmed against ATP". It does not judge whether a number is reasonable.
- **Regulatory and pharmacopoeial references marked "clause to be verified" in the templates and the knowledge base have not been checked against the original text.** Check the current version before use. Scientific content must be reviewed by experts in your organisation.
- Local accounts only: no SSO or Active Directory, no multi-factor authentication. Password expiry is available but optional. The default is HTTP, with no TLS.
- Time comes from the server clock. It is not synchronised with a time server and does not protect against clock changes.
- SQLite is single-machine and single-node, with no high availability. Backups are on the same disk by default, so arrange off-site backups yourself and keep `.audit_key` separately.
- The audit hash chain (keyed) and the anchor can only **detect** tampering with the database. Someone who has both the database and `.audit_key` can recalculate the whole chain.
- The electronic signature is a password re-authentication bound to the revision and content hash. It is not a digital certificate. Team roles are assigned by the method owner; the program checks that they match the global roles, but the suitability of accounts and roles still depends on your management procedures.
- Word and PDF documents have no digital signature and no write protection. PDF depends on LibreOffice conversion, so the layout may differ slightly from Word.
- Lifecycle stages such as validation, transfer and routine use are recorded as status only in V0.2, with no workflow templates.
- The automated tests are developer regression tests. The user interface has no automated tests. They are not IQ/OQ/PQ.
- The complete list of open gaps is in `docs\URS_需求与测试追溯.md`.

## 18. Folder layout

```
MethodFlow\                       program folder (paths below are relative)
├─ start.bat              double-click to start (finds Python, checks packages, opens the browser)
├─ backup.bat             double-click to back up the database
├─ run.py                 start-up script (--host/--port/--data/--no-browser)
├─ requirements.txt       dependencies and versions (includes pypdf)
├─ config.json            optional settings (create it yourself, see 11.3)
├─ README.md / README.zh-CN.md   overview (English / Chinese)
├─ docs\user-manual_en.md        this manual (English)
├─ docs\用户手册_中文.md          user manual (Chinese)
├─ LICENSE / NOTICE       licence and copyright notice
├─ CONTRIBUTING.md / SECURITY.md / SUPPORT.md / CODE_OF_CONDUCT.md / CHANGELOG.md / ROADMAP.md
├─ app\                   the program
│  ├─ main.py             web interface (FastAPI)
│  ├─ config.py           settings and data paths
│  ├─ auth.py             accounts, passwords, sessions, re-authentication for signatures
│  ├─ workflow.py         business rules: projects, methods, stages, review gates, experiments, attachments, backups
│  ├─ records.py          reagent and instrument registry, run records, deviations
│  ├─ compliance.py       audit-trail review, inspection pack, comments and @mentions, search, revisions
│  ├─ stats.py            statistics (t, chi-square, ANOVA, regression, LOD/LOQ, TOST, etc.)
│  ├─ validate.py         input validation
│  ├─ notifier.py         e-mail and webhook notifications
│  ├─ audit.py            audit trail and hash chain
│  ├─ db.py               SQLite structure and access
│  ├─ docgen.py           Word / PDF generation and document settings
│  ├─ i18n_doc.py         English export of document fixed text
│  ├─ templates_data.py   nine stages and seven method-type templates
│  ├─ kb_seed.py          built-in knowledge base
│  ├─ kb_links.py         built-in resource links
│  └─ static\             front-end pages (HTML/JS/CSS, works offline)
├─ tools\
│  ├─ backup.py           backup (called by backup.bat)
│  ├─ restore.py          restore from a backup
│  ├─ reset_admin.py      offline administrator password reset
│  ├─ audit_anchor.py     show or rebuild the audit anchor
│  ├─ migrate_v1_to_v2.py conversion of an old database
│  ├─ run_tests_report.py run the automated tests and write the report
│  ├─ i18n_missing.py     list interface strings without translation
│  └─ i18n_add_extra.py   merge "Chinese<TAB>English" translations into i18n_extra_en.js
├─ tests\                 automated tests (file names match the URS numbers in docs\URS_需求与测试追溯.md)
├─ docs\
│  ├─ user-manual_en.md / 用户手册_中文.md
│  ├─ URS_需求与测试追溯.md
│  ├─ V0.2需求与设计_项目方法分离与审批级文档.md
│  ├─ 前端契约.md          interface and front-end module description
│  ├─ 后端加固清单.md
│  ├─ 调研与设计依据.md
│  ├─ 自动化测试报告.md     generated by tools\run_tests_report.py
│  └─ CSV验证模板\         starting templates for IQ/OQ/PQ, risk assessment and SOP key points
├─ .github\               GitHub workflows (tests, CodeQL), issue and PR templates, dependency updates
└─ data\                  created at run time: database, uploads, documents, backups, .audit_key, audit_head.json (not in the repository)
```

---

## What's new in V0.3 (2026-10-15)

- **Ordered workflow:** creating a method starts stage 1 (fill in the core content in the wizard). A later stage opens only after the earlier one passes. Each stage page has a beginner guide, the method page has a "what to do next" card, and the left-hand "Beginner guide" explains the whole process.
- **Progressive completion:** only missing core content blocks submission; other items only warn. (Setting `strict_completeness=true` requires every required item.)
- **Confirmation:** pre-filled template content (FMEA, ATP criteria, RACI, glossary and so on) must be confirmed section by section before it counts as completed. Content with "example value" or "XX" placeholders cannot be confirmed. Example criteria of experiments must be checked before the plan is submitted (the experiments page has "Confirm example values"). Documents containing unconfirmed content are labelled "pending confirmation".
- **Review support:** reviewers can compare with the previous revision; in-app notifications (bell at the top right); the dashboard lists the next steps that can be started.
- **Experiments and plan:** start or cancel experiments in batches; reschedule the plan; "mark all checklist items as done".
- **Knowledge-base resource links:** on the knowledge base page, "Resource links": regulations, agencies, pharmacopoeias, literature, tools. Add, edit or deactivate; administrators can "Check links".
- **Interface language:** switch between "中文 / EN" at the bottom right. Template text, knowledge-base entries and generated documents were still Chinese in this version.
- **Database structure v4:** an old v3 database is upgraded in place at first start, after an automatic backup to `data/backups/premigrate_v3_*.db`.
- The English overview is `README.md`; open work is in `ROADMAP.md`.

---

## What's new in V0.4 (2026-10-15, database structure v5)

Suitable for a single computer or a laboratory LAN. It is not a validated GxP system. `docs/CSV验证模板/` gives starting points for validation (risk assessment, IQ/OQ/PQ checklists, SOP key points).

- **Automatic result verdicts, statistics calculator and CSV import:** result rows get "pass / fail / to be evaluated" automatically against their criteria (≥, ≤, ranges, ±). A manual verdict that differs is flagged before submission. On the experiment page, the "Statistics calculator" does descriptive statistics, accuracy, precision (ANOVA), linearity, LOD/LOQ, equivalence (TOST) and count CV, and can write the results to the results table in one step. "Import CSV" appends result rows.
- **Registry (top menu "Registry"):** reagents and materials, instruments and equipment, with lot numbers, expiry dates and calibration due dates. Expired or out-of-calibration items are flagged automatically on run records.
- **Run records (experiment page):** date, analyst, materials and instruments used, result status. A second person must verify them.
- **Deviations (method page "Deviations"):** open "major" or "critical" deviations block the submission of their stage. Closing is an electronic signature. The person who opened a deviation cannot close it, and major or critical ones need an approver.
- **Audit-trail review (Administration → Audit-trail review):** records who reviewed which period of the audit trail, and at the same time verifies the hash chain and all signatures. Reminders when overdue (`audit_review_days`, default 90 days).
- **Inspection pack (method page "Inspection pack"):** one zip file with the content, experiments, runs, deviations, signature manifest, audit trail, attachments with their hashes, and generated documents.
- **Comments and @mentions** (💬 on each section of a stage page), **global search** (search box at the top), and **revisions of approved methods** (the earlier version is kept and the change is described).
- **Password expiry and history** (`password_max_days`, `password_history`), and an optional **change reason** (`require_change_reason`, written to the audit trail).
- **Documents:** generated in the background with progress. The "Document language" option can be "English": the cover, table headers, chapter titles and signature page are in English, while template body text and what users wrote stay as they are.
- **E-mail and webhook notifications:** set `smtp_*` or `webhook_url` in `config.json` (WeCom, DingTalk, Feishu and others via `webhook_kind`). Users set their address under "Set my e-mail" in the top-right menu.
- **Database structure v5:** an old v3 or v4 database is upgraded in place at first start, after a backup to `data/backups/premigrate_v*_*.db`.
- Open-source files: `LICENSE`, `NOTICE`, `CONTRIBUTING.md`, `SECURITY.md`, `.github/workflows/test.yml`.
- Left for the community: complete validation, transfer and routine-monitoring modules; a web template editor; importing legacy methods; CTD generation; 4PL and parallelism; SSO, PostgreSQL and Docker; training matrix; English translation of the template body text.
