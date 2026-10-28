# Security checklist

The security goals for the proof of concept, how we plan to meet each one, and which task does it. Written in SCRUM-60. The security pass before the demo (SCRUM-85) walks this list and marks each row as met or deferred.

## Read this first

- **These are goals, not requirements.** This page is our plan for keeping the proof of concept safe. If a goal turns out to cost too much for the proof of concept, SCRUM-85 lists it as deferred, with the reason, instead of blocking the demo.
- **We are assuming Azure.** The plan is Azure (Container Apps, PostgreSQL Flexible Server, Blob Storage, Static Web Apps), as in `AGENTS.md` and [`infra/README.md`](../infra/README.md). Hosting is not 100% final yet. If it changes, the "How we plan to do it" column changes, but the goals stay the same.
- **"HIPAA-ready," never "HIPAA compliant."** The proof of concept uses only synthetic or open-source data, never real patient data. It follows practices that would help toward HIPAA later, but it is not certified for anything.

## Goals

**Status:** Done = built and merged. Planned = a task exists but is not done yet. No task = nothing builds it yet (see [Gaps](#gaps)).

| Goal | How we plan to do it | Task | Status | How SCRUM-85 checks it |
| --- | --- | --- | --- | --- |
| **HTTPS only** | Static Web Apps serves HTTPS by default. The API's Container Apps ingress is set to HTTPS only | SCRUM-46, SCRUM-55 | Planned | An `http://` request is refused or redirected to `https://` |
| **AI service is not public** | The AI service's Container Apps ingress is internal only, so only the API can call it | SCRUM-46 | Planned | The AI service has no public URL |
| **Encryption at rest** | Azure encrypts PostgreSQL and Blob Storage on disk by default (Microsoft-managed keys) | SCRUM-46 | Planned | Confirm it in the Portal for both |
| **Database locked down** | PostgreSQL requires TLS, and its firewall only lets our Azure services in | SCRUM-46 | Planned | A connection without TLS fails, and one from an outside address is blocked |
| **Videos are private** | One private container. The storage module creates it without public access and refuses a public one. The storage account also has public access turned off | SCRUM-23 (code), SCRUM-46 (account setting) | Code done, account planned | Opening a video's plain URL without a link fails |
| **Short-lived video links** | Videos are read only through links to one file that expire after 15 minutes or less. Only `backend/app/storage/` makes them | SCRUM-23 | Done | A link stops working after it expires |
| **Raw videos deleted after 30 days** | A lifecycle rule on the storage account | SCRUM-81 | Planned | The rule is active, and a 1-day rule on a test container works |
| **Only signed-in users** | Every route checks the Clerk token | SCRUM-21 | Done | A request without a valid token gets `401` |
| **Right role, right owner** | Roles live in our `User` table. Every route checks the role and ownership: a patient sees only their own data, a therapist only linked patients | SCRUM-21, each route's task, SCRUM-68 | Started | Every route has a passing wrong-role and wrong-owner test |
| **Only our web app can call the API from a browser** | CORS allows only the web app's origins (`CLERK_AUTHORIZED_PARTIES`) | SCRUM-33 | Done | A request from another origin is blocked, and `tests/test_cors.py` passes |
| **Safe uploads** | Size, length, and content-type checks on the server, and random (UUID) file names instead of the user's | SCRUM-82 | Planned | Tests reject oversized, wrong-type, and too-long uploads |
| **No personal data in logs** | Logs carry the session id, never tokens, emails, names, or video links | SCRUM-83 | Planned | Trace one session through the logs and find no personal data |
| **No secrets in the repo** | Secrets live only in GitHub secrets and Container Apps secrets. Deploys log in to Azure with OIDC, so no Azure password is stored | SCRUM-47 | Planned | No secrets in the repo or its history, and the deploy uses OIDC |
| **Secret scanning on** | Turn on GitHub secret scanning and push protection for the repo | No task | No task | Both are on in the repo settings |

## Gaps

- **Secret scanning:** no task turns it on. It is one repo setting, so SCRUM-85 can turn it on when it checks. It is off today. Turning it on is safe: Azurite's public development key is already kept out of the repo for this reason (see [issue #9](https://github.com/PTAssist-UCF/PTAssist/issues/9)).

If the hosting plan changes, update the "How we plan to do it" column and the tasks, and recheck this list for new gaps.
