# Infrastructure

> **On hold (since Nov 11, 2026).** The sponsor is still deciding where PTAssist will be hosted, so none of the resources below exist yet, and all work is local (Docker Compose). This file is the plan if the sponsor picks Azure. The Azure tasks (SCRUM-46, 47, 55, 67, 74, 81, 84, and 106) wait in the Jira backlog with "ON HOLD" in their titles. See `AGENTS.md`, section 2.

Our Azure resources are created by hand in the Azure Portal. This file is the written record of every setting, so we can rebuild everything in a new subscription (the student credit expires around late February 2027).

**If you change anything in the Portal, update this file in the same PR or right after.**

## Resources

Filled in by SCRUM-46, once the sponsor decides on hosting.

| Resource | Azure service | Name | Key settings |
| --- | --- | --- | --- |
| API | Container Apps | | Public HTTPS, scale to zero. `CLERK_AUTHORIZED_PARTIES` = the Static Web Apps URL (sign-in and browser access) |
| AI service | Container Apps | | Internal ingress only, scale to zero |
| Database | PostgreSQL Flexible Server (B1ms) | | TLS required, firewall on |
| Video storage | Storage account (Blob) | | Private container, 30-day delete rule |
| Frontend | Static Web Apps | | |
| Migrations | Container Apps job | | Runs Alembic on each deploy |
| Promote therapist | Container Apps job | | Manual trigger, API image. Started by hand to make a user a therapist (see Promote a therapist) |

Local development uses Azurite, the Azure Storage emulator, instead of a storage account. Azurite has no lifecycle rules, so the 30-day delete rule exists only in Azure.

**Request time limit:** Container Apps ingress ends any HTTP request after 240 seconds (4 minutes). This is Azure's limit, not one of our settings: Azure's docs say raising it needs premium ingress on a dedicated (paid) workload profile. It matters for the AI service, because the backend waits for `POST /analyze` in one request. So the backend's call timeout must be between 3 and 4 minutes, and a 2-minute clip must be analyzed in 3 minutes or less, counting a cold start (see [Clip limits and timing](../docs/analysis-result.md#clip-limits-and-timing)).

## Deploys

- **Pull requests:** GitHub Actions runs lint, tests, and image builds.
- **Merge to main:** build and push images to GitHub Container Registry, run migrations, deploy new revisions. Login to Azure uses OIDC (no stored passwords).

## Promote a therapist

> **Not tried yet.** These steps were written in SCRUM-65, before the Azure resources existed (SCRUM-46). Whoever first creates the job checks each step against the Portal and the Azure CLI, fixes this section, and fills in the job's row in Resources.

New users are patients. A team member makes someone a therapist with `app/promote_therapist.py` (what it does in each case: `backend/README.md`, Promote a therapist). In Azure it runs as a Container Apps job that is started by hand. The job uses the API's image and runs in the API's Container Apps environment, so it reaches the database the same way the API does. Don't run the script from your computer against the Azure database: the database's firewall only lets our Azure services in.

**Create the job once** (Portal: Container Apps jobs, Create), in the API's Container Apps environment:

| Setting | Value |
| --- | --- |
| Trigger type | Manual |
| Replica timeout | 300 seconds |
| Retry limit | 0. A failed run is not retried: read its logs, then start a new run |
| Parallelism, replica completion count | 1, 1 |
| Image | The API's image from GitHub Container Registry, with the same registry login as the API |
| Command override | `python -m app.promote_therapist` (three values: `python`, `-m`, `app.promote_therapist`) |
| Arguments | None. Each run adds the email (below). A run without one fails and changes nothing |
| CPU, memory | 0.25 cores, 0.5 Gi |
| Secret | `database-url`: the same value as the API's `DATABASE_URL` |
| Environment variable | `DATABASE_URL`, from the secret `database-url`. The script needs no other settings |

**Promote someone.** First they sign in to the web app once. Then, with the Azure CLI (after `az login`), in a folder outside the repo so the file with their email is never committed:

1. Save the job's container settings to a file, and look up the API's current image:

   ```bash
   az containerapp job show -n <job> -g <resource group> --query properties.template -o yaml > promote.yaml
   az containerapp show -n <API app> -g <resource group> --query "properties.template.containers[0].image" -o tsv
   ```

2. Edit `promote.yaml`. Set the container's `image:` to the API's current image (deploys update the API, not this job). Then add the email under the container, indented like `image:`:

   ```yaml
     args:
     - --email
     - someone@example.com
   ```

3. Start one run with these settings, then delete the file. The job's own settings don't change. A run started with other settings replaces all of the job's container settings, which is why the file starts from the job's own (image, command, and the `DATABASE_URL` secret).

   ```bash
   az containerapp job start -n <job> -g <resource group> --yaml promote.yaml
   rm promote.yaml
   ```

4. Check the result. `az containerapp job execution list -n <job> -g <resource group> -o table` lists each run with its status: `Succeeded` means the user has the role now (or already had it). `Failed` means the script stopped with an error; when it refuses (wrong email, or a patient with a therapist or a plan), it changes nothing. To see what it printed, open the job in the Portal, then **Execution history** and the run's console logs. Or run this query in the Container Apps environment's **Logs**, with the run's name from the list (logs can take a few minutes to arrive):

   ```kusto
   ContainerAppConsoleLogs_CL
   | where ContainerGroupName_s startswith "<run name>"
   | project TimeGenerated, Log_s
   ```

   A promotion prints `User <id> is now a therapist.` A refusal prints `Role not changed:` and the reason.

The script prints the user's id, never their email, so the email stays out of the logs. It does stay in that run's settings in the job's execution history.

## Cost

Budget alerts at $5 and $10. Everything scales to zero when idle.
