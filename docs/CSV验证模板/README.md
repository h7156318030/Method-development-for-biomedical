# MethodFlow computerised-system validation (CSV): starting templates

> These files are **starting points**, not a completed validation. MethodFlow is not a validated GxP system.
> Before you use it in a regulated laboratory, your organisation must carry out its own risk assessment, IQ/OQ/PQ, and an SOP, and have them approved by Quality.
> The automated tests (`tests/`, mapped to requirements in `docs/URS_需求与测试追溯.md`) can support OQ evidence, but they do not replace execution records.

The reference document in Chinese is [README_CSV验证模板.md](README_CSV验证模板.md), which contains the same tables in full.

## 1. Risk assessment (example, adapt to your site)

| Function | Impact on data integrity or patient safety | Probability | Detectability | Risk level | Controls |
|---|---|---|---|---|---|
| Electronic signature and stage locking | High | Low | High (audit trail) | Medium | OQ tests for the signature requirements; periodic audit-trail review |
| Audit trail (hash chain) | High | Low | High | Medium | Periodic review (URS-154); back up `data/` with `.audit_key` |
| Automatic verdict on result rows | Medium | Medium | Medium (manual review) | Medium | Manual verdicts that differ are flagged; second-person review |
| Statistics calculator | Medium | Medium | Medium | Medium | Check a set of examples against an independent, qualified tool |
| Document export | Medium | Low | High (human review) | Low | Human review before formal issue |
| Backup and restore | High | Low | Medium | Medium | Periodic restore drill |

## 2. IQ (installation qualification)

| Item | Requirement | Result | Performed by / date |
|---|---|---|---|
| Operating system and version | Recorded | | |
| Python version | 3.9 or newer | | |
| `pip install -r requirements.txt` | No errors; versions as in the file | | |
| Permissions on the data folder | Writable only by authorised staff | | |
| Start the server and open the login page | Succeeds | | |
| Create the administrator; no default password | Compliant | | |
| `backup.bat` | Creates a backup that can be restored | | |

## 3. OQ (operational qualification)

Run the automated tests with `python -X utf8 -m unittest discover -s tests`, keep the output, and check the behaviour the tests do not cover (English interface, document appearance, browser compatibility) by hand, with screenshots.

| ID | Scenario | Expected | Actual | Pass |
|---|---|---|---|---|
| OQ-1 | Repeated wrong passwords lock the account | Locked; recorded in the audit trail | | |
| OQ-2 | Submit, sign and approve a stage | Stage locked; signature bound to the content hash | | |
| OQ-3 | The person who edited a stage tries to review it | Refused | | |
| OQ-4 | Change content of a signed stage | Refused; reopen the stage first | | |
| OQ-5 | Change a database record directly | Hash-chain or signature check fails | | |
| OQ-6 | Close a major deviation | Second person's electronic signature required | | |
| OQ-7 | Use an expired reagent or an instrument past calibration | Warning on the run record | | |
| OQ-8 | Export Word and PDF (Chinese and English) | Content matches the system; drafts are marked | | |

## 4. PQ (performance qualification)

Enter a completed, anonymised historical method end to end in real use. The users confirm that the workflow works, that the criteria are judged correctly, and that the document meets the internal review requirements. Record any deviations and how they were handled.

## 5. Key points for an SOP

1. Purpose and scope: electronic management of method-development records.
2. Roles: administrator, approver, reviewer, author; separation-of-duties rules.
3. Accounts: creation, deactivation, password expiry, leavers.
4. Routine use: create projects and methods, submit and sign stages, handle deviations, reopen approved methods.
5. Data integrity: audit-trail review frequency (default every 90 days), backup and restore drills, inspection pack.
6. Change control: back up before an upgrade; after an upgrade, run the automated tests and record the result.
7. Known limitations: see the README and `ROADMAP.md`.
