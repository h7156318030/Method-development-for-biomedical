# Security policy

MethodFlow is a tool for single-machine and laboratory-LAN use. It is **not** a validated GxP computerised system;
using it in a regulated environment requires your own validation (see `docs/CSV验证模板/`).

## Reporting a vulnerability

Please **do not** open a public issue for a security problem.

Use GitHub's private reporting: the **Security** tab of this repository → **Report a vulnerability**.
Describe the problem, the steps to reproduce it, and the version (`0.4.0` or the commit you tested).
Do not include real passwords, real data or real method documents in the report.

The maintainers will acknowledge a report as soon as they can (best effort) and will coordinate a fix and disclosure with you.

## Supported versions

Only the latest release receives security fixes.

## Scope

In scope: the code in this repository (authentication, sessions, authorisation, audit trail, signatures, file handling, document generation).
Out of scope: problems in third-party packages (report them upstream; tell us if MethodFlow uses them unsafely) and problems caused by
deployments that expose the service to the internet without the measures below.

## Deployment notes

- Run MethodFlow on the local machine or the laboratory LAN only. Do not expose its port to the internet.
- Put it behind an HTTPS reverse proxy if it is reached over a network (the built-in server speaks plain HTTP).
- Set a strong administrator password at the first start; set `password_max_days` if your SOP requires expiry.
- Back up the `data/` folder regularly (`backup.bat`). It contains the database, the audit anchor and the audit HMAC key.
- Never commit `data/`, `config.json` (it may hold SMTP or webhook secrets) or any credential file.
