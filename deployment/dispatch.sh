#!/usr/bin/env bash
set -euo pipefail
cd /opt/isty-twenty
exec 9>/opt/isty-twenty/deploy.lock
flock -w 5 9 || { echo 'Another Twenty deployment is running'; exit 1; }
read -r operation image extra <<< "${SSH_ORIGINAL_COMMAND:-}"
[[ -z "${extra:-}" ]] || exit 1
[[ "$operation" == deploy || "$operation" == migrate ]] || exit 1
[[ "$image" =~ ^ghcr\.io/isty-org/twenty@sha256:[a-f0-9]{64}$ || "$image" =~ ^twentycrm/twenty:v[0-9]+\.[0-9]+\.[0-9]+$ ]] || exit 1
umask 077
temporary=$(mktemp -d /opt/isty-twenty/.deploy-XXXXXX)
trap 'rm -rf -- "$temporary"' EXIT
read -r registry_token
if [[ "$image" == ghcr.io/* ]]; then
  [[ -n "$registry_token" ]] || exit 1
  printf '%s' "$registry_token" | docker --config "$temporary/docker" login ghcr.io -u Isty-org --password-stdin >/dev/null
fi
unset registry_token
cat > "$temporary/payload.tar.gz"
python3 - "$temporary" <<'PY'
import pathlib, sys, tarfile
directory = pathlib.Path(sys.argv[1])
with tarfile.open(directory / 'payload.tar.gz') as archive:
    members = archive.getmembers()
    allowed = {'compose.yaml', 'ensure_boards.py'}
    if {member.name for member in members} != allowed:
        raise SystemExit('Unexpected deployment files')
    for member in members:
        if not member.isfile() or member.size > 1024 * 1024:
            raise SystemExit('Invalid deployment file')
        (directory / member.name).write_bytes(archive.extractfile(member).read())
PY
export DOCKER_CONFIG="$temporary/docker"
TWENTY_IMAGE="$image" docker compose -f "$temporary/compose.yaml" --env-file /opt/isty-twenty/.env config -q
docker pull "$image" >/dev/null
backup="/opt/isty-twenty/backups/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup"
available=$(df -Pk /opt/isty-twenty | awk 'NR==2 {print $4}')
[[ "$available" -gt 4194304 ]] || { echo 'Less than 4 GiB disk space; refusing deploy'; exit 1; }
docker compose exec -T db pg_dump -U twenty -d twenty -Fc > "$backup/database.dump"
cp .env compose.yaml "$backup/"
docker compose exec -T server tar -czf - -C /app/packages/twenty-server/.local-storage . > "$backup/storage.tar.gz"
[[ -s "$backup/database.dump" && -s "$backup/storage.tar.gz" ]]
if [[ "$operation" == migrate ]]; then
  current=$(docker compose images -q server | head -1)
  expected=$(docker image inspect "$image" --format '{{.Id}}')
  [[ "$current" == "$expected" ]] || { echo 'Migrations must use the currently deployed image'; exit 1; }
  docker compose exec -T server yarn command:prod upgrade
  docker compose exec -T server yarn command:prod cache:flush
else
  install -m 644 "$temporary/compose.yaml" compose.yaml
  install -m 644 "$temporary/ensure_boards.py" ensure_boards.py
  python3 - "$image" <<'PY'
import pathlib, sys
path = pathlib.Path('.env')
lines = [line for line in path.read_text().splitlines() if not line.startswith('TWENTY_IMAGE=')]
path.write_text('\n'.join(lines) + '\nTWENTY_IMAGE=' + sys.argv[1] + '\n')
PY
  docker compose up -d --wait --wait-timeout 900
fi
curl --fail --silent http://127.0.0.1:13020/healthz
python3 ensure_boards.py
echo "Twenty operation completed. Backup: $backup"
