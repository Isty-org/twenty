# Isty Twenty production

Production: https://twenty.isty.ist. Deployment directory: `/opt/isty-twenty`.

The application, worker, PostgreSQL and Redis use the `isty-twenty` Compose project and dedicated volumes. PostgreSQL and Redis have no published ports. The app is available on host loopback port 13020 and through the existing Caddy network `root_walldenet`. Caddy configuration was backed up before appending the Twenty route and reloaded without restarting its container.

## Deploy from GitHub

Open Actions → **Manual production deploy** → **Run workflow** on `main`.

`source_ref` selects the source branch, commit or release tag. It defaults to the stable release `twenty/v2.45.0`. To deploy your code changes, select `main` or the desired commit. With `build_image` enabled, the production Dockerfile builds on `[self-hosted, linux, x64, isty-ci]`, publishes `ghcr.io/isty-org/twenty:sha-<commit>`, and deploys its immutable digest. With `build_image` disabled, the workflow deploys the pinned official `twentycrm/twenty:v2.45.0` image. Pushing to `main` runs configuration checks only.

The workflow uses an isolated BuildKit builder with sequential build steps and a 6 GiB memory limit. There is no matrix. Only one production deploy or migration can run at a time. Credentials are saved under `$RUNNER_TEMP` and removed even on failure. No shared Docker pruning is performed.

The repository secrets `DEPLOY_SSH_KEY` and `DEPLOY_KNOWN_HOSTS`, variable `DEPLOY_HOST`, and `production` environment are configured. The server accepts this deploy key only through `/opt/isty-twenty/dispatch.sh`; forwarding and interactive shells are disabled. Temporary GHCR credentials on the server are isolated and removed.

## Migrations and backups

The official entrypoint initializes and upgrades the database when deploying a new image. To rerun the existing version's upgrade explicitly, use **Manual production migrations**, entering the exact currently deployed image. The script refuses migrations against another image.

Before every deploy or manual migration, a database dump, storage archive, Compose file and `.env` are saved under `/opt/isty-twenty/backups/<UTC timestamp>`. Deployment refuses to proceed with less than 4 GiB free disk. Backups contain secrets: keep them private and copy them off this server according to your backup policy. Backups are retained; monitor disk usage.

A failed deployment is reported by Actions. Restore is manual because automatically downgrading an image after a database migration can corrupt data. Restore the matching database dump and storage archive together with the backed-up `.env` and Compose file. Restore only the `isty-twenty` project; never remove other services or volumes.

## Workspace and boards

The workspace `Isty CRM` has shared navigation entries **Доска задач** (table) and **Канбан** (kanban grouped by status). Both show title, status, assignee and due date. The kanban includes TODO, IN_PROGRESS and DONE columns even when empty. `ensure_boards.py` verifies these entries after deployment and creates missing board fields and groups without duplicating boards.

Administrator credentials are stored only on the production server in `/opt/isty-twenty/admin.json`, mode 600. Do not commit this file. Change the bootstrap password after first login and update this file if automated board verification should continue using the account. The workspace ID is in `/opt/isty-twenty/workspace-id`.

## Upstream workflows

The original upstream workflows are archived in `.github/upstream-workflows/`; they are not executed by GitHub. They include Twenty-owned infrastructure dispatches, website previews, translations, release automation and extensive unrelated package checks. The fork keeps all upstream source and tests. Production images use the upstream production Docker target, which excludes development source and compiled server integration tests.

The build appends a production stage that also removes compiled unit test files (`*.spec.js`, `*.test.js` and their source maps) from server output; this leaves upstream test source available for development while keeping it out of the deployed fork image.

Active workflows are deployment configuration checks, manual production build/deploy, manual production migrations and the manual runner availability check. External pull requests do not execute on the persistent organization runners; internal pull requests run deployment checks.
