#!/usr/bin/env bash
set -Eeuo pipefail

: "${RELEASE_TAG:?RELEASE_TAG is required}"
: "${ARCHIVE_PATH:?ARCHIVE_PATH is required}"
: "${ARCHIVE_SHA256:?ARCHIVE_SHA256 is required}"

DEPLOY_ROOT="${DEPLOY_ROOT:-/opt/trade-review-agent}"
RELEASE_DIR="$DEPLOY_ROOT/.deploy/releases/$RELEASE_TAG"
STATE_DIR="$DEPLOY_ROOT/.deploy"
COMPOSE_FILE="$RELEASE_DIR/docker-compose.release.yml"
LOCK_FILE="$STATE_DIR/deploy.lock"
API_IMAGE="aitrading/trade-review-api:$RELEASE_TAG"
FRONTEND_IMAGE="aitrading/trade-review-frontend:$RELEASE_TAG"

mkdir -p "$RELEASE_DIR" "$DEPLOY_ROOT/work" "$DEPLOY_ROOT/outputs"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "ERROR: another deployment is already running" >&2
  exit 10
fi

if [[ ! -s "$DEPLOY_ROOT/.env" ]]; then
  echo "ERROR: $DEPLOY_ROOT/.env is missing or empty" >&2
  exit 11
fi
chmod 600 "$DEPLOY_ROOT/.env"
if [[ ! -s "$ARCHIVE_PATH" || ! -s "$COMPOSE_FILE" ]]; then
  echo "ERROR: release archive or compose manifest is missing" >&2
  exit 12
fi
actual_archive_sha256="$(sha256sum "$ARCHIVE_PATH" | awk '{print $1}')"
if [[ "$actual_archive_sha256" != "$ARCHIVE_SHA256" ]]; then
  echo "ERROR: uploaded release archive checksum mismatch" >&2
  exit 16
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: Docker must already be installed" >&2
  exit 13
fi
if docker compose version >/dev/null 2>&1; then
  COMPOSE_FLAVOR=v2
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_FLAVOR=v1
else
  echo "ERROR: docker compose v2 or docker-compose v1 is required" >&2
  exit 14
fi

available_kb="$(df -Pk "$DEPLOY_ROOT" | awk 'NR==2 {print $4}')"
archive_kb="$(du -Pk "$ARCHIVE_PATH" | awk '{print $1}')"
required_kb=$((archive_kb * 3 + 524288))
if (( available_kb < required_kb )); then
  echo "ERROR: insufficient disk space for release (need ${required_kb} KB, have ${available_kb} KB)" >&2
  exit 15
fi

old_api="$(docker inspect -f '{{.Config.Image}}' trade-review-api 2>/dev/null || true)"
old_frontend="$(docker inspect -f '{{.Config.Image}}' trade-review-frontend 2>/dev/null || true)"
old_tag="$(cat "$STATE_DIR/current-release" 2>/dev/null || true)"
if [[ -n "$old_api" && -n "$old_frontend" ]]; then
  rollback_tag="rollback-$RELEASE_TAG"
  docker image tag "$old_api" "aitrading/trade-review-api:$rollback_tag"
  docker image tag "$old_frontend" "aitrading/trade-review-frontend:$rollback_tag"
  printf 'API_IMAGE=%s\nFRONTEND_IMAGE=%s\n' "$old_api" "$old_frontend" > "$STATE_DIR/rollback-images.env"
fi

echo "Loading immutable release images: $RELEASE_TAG"
api_exists=0
frontend_exists=0
docker image inspect "$API_IMAGE" >/dev/null 2>&1 && api_exists=1
docker image inspect "$FRONTEND_IMAGE" >/dev/null 2>&1 && frontend_exists=1
if (( api_exists != frontend_exists )); then
  echo "ERROR: immutable release tag is only partially present; refusing to overwrite it" >&2
  exit 17
fi
if (( api_exists == 0 )); then
  docker load --input "$ARCHIVE_PATH"
else
  echo "Release images already exist; immutable tags will not be overwritten"
fi
docker image inspect "$API_IMAGE" >/dev/null
docker image inspect "$FRONTEND_IMAGE" >/dev/null

export DEPLOY_ROOT RELEASE_TAG
compose_up() {
  if [[ "$COMPOSE_FLAVOR" == v2 ]]; then
    docker compose -p trade-review-agent -f "$COMPOSE_FILE" up -d --no-build --force-recreate --remove-orphans
  else
    docker-compose -p trade-review-agent -f "$COMPOSE_FILE" up -d --no-build --force-recreate --remove-orphans
  fi
}

compose_ps() {
  if [[ "$COMPOSE_FLAVOR" == v2 ]]; then
    docker compose -p trade-review-agent -f "$COMPOSE_FILE" ps
  else
    docker-compose -p trade-review-agent -f "$COMPOSE_FILE" ps
  fi
}

compose_logs() {
  if [[ "$COMPOSE_FLAVOR" == v2 ]]; then
    docker compose -p trade-review-agent -f "$COMPOSE_FILE" logs --tail=120
  else
    docker-compose -p trade-review-agent -f "$COMPOSE_FILE" logs --tail=120
  fi
}

health_check() {
  local attempt
  for attempt in $(seq 1 60); do
    if curl -fsS --max-time 5 http://127.0.0.1:8600/api/health >/dev/null \
      && curl -fsS --max-time 5 http://127.0.0.1:3000/ >/dev/null; then
      return 0
    fi
    sleep 2
  done
  return 1
}

rollback() {
  echo "ERROR: release health check failed; rolling back" >&2
  if [[ -z "$old_api" || -z "$old_frontend" ]]; then
    echo "ERROR: no previous container images are available for automatic rollback" >&2
    return 1
  fi
  export RELEASE_TAG="$rollback_tag"
  compose_up || {
    echo "ERROR: rollback container switch failed" >&2
    return 1
  }
  health_check || {
    echo "ERROR: rollback health check failed" >&2
    return 1
  }
  echo "Rollback completed" >&2
}

if ! compose_up; then
  echo "ERROR: release container switch failed; attempting rollback" >&2
  compose_ps >&2 || true
  compose_logs >&2 || true
  if ! rollback; then
    echo "ERROR: automatic rollback failed after container switch error" >&2
    exit 22
  fi
  exit 21
fi
if ! health_check; then
  compose_ps >&2 || true
  compose_logs >&2 || true
  if ! rollback; then
    echo "ERROR: automatic rollback failed after health check error" >&2
    exit 22
  fi
  exit 20
fi

if [[ -f "$STATE_DIR/current-images.env" ]]; then
  cp "$STATE_DIR/current-images.env" "$STATE_DIR/previous-images.env"
elif [[ -n "$old_api" && -n "$old_frontend" ]]; then
  # First migration from the legacy online-build deployment still records its
  # image pair, so operators retain one known-good predecessor.
  printf 'API_IMAGE=%s\nFRONTEND_IMAGE=%s\n' "$old_api" "$old_frontend" > "$STATE_DIR/previous-images.env"
fi
if [[ -n "$old_tag" ]]; then
  printf '%s\n' "$old_tag" > "$STATE_DIR/previous-release"
fi
printf 'API_IMAGE=%s\nFRONTEND_IMAGE=%s\n' "$API_IMAGE" "$FRONTEND_IMAGE" > "$STATE_DIR/current-images.env"
printf '%s\n' "$RELEASE_TAG" > "$STATE_DIR/current-release"
rm -f -- "$ARCHIVE_PATH" "$STATE_DIR/rollback-images.env"

compose_ps
echo "Release $RELEASE_TAG is healthy"

if [[ -x "$STATE_DIR/bin/remote_cleanup.sh" ]]; then
  DEPLOY_ROOT="$DEPLOY_ROOT" "$STATE_DIR/bin/remote_cleanup.sh"
fi

# Install the safe cleanup policy for future runs. It retains the current and
# previous immutable releases and never removes Docker build cache globally.
if [[ -d /etc/cron.d && -w /etc/cron.d ]]; then
  printf '17 3 * * * root DEPLOY_ROOT=%q %q >>%q 2>&1\n' \
    "$DEPLOY_ROOT" "$STATE_DIR/bin/remote_cleanup.sh" "$STATE_DIR/cleanup.log" \
    > /etc/cron.d/aitrading-release-cleanup
  chmod 644 /etc/cron.d/aitrading-release-cleanup
fi

# Remove only the known destructive legacy entry from root's crontab while
# preserving every unrelated cron job. The replacement policy above is scoped
# to this application's labels and retains two releases.
if command -v crontab >/dev/null 2>&1; then
  old_crontab="$(mktemp)"
  new_crontab="$(mktemp)"
  crontab -l > "$old_crontab" 2>/dev/null || true
  awk '!/\/usr\/bin\/docker[[:space:]]+image[[:space:]]+prune[[:space:]]+-af([[:space:]]|$)/' \
    "$old_crontab" > "$new_crontab"
  crontab "$new_crontab"
  rm -f -- "$old_crontab" "$new_crontab"
fi

# Remove only the temporary rollback aliases created for this successful
# switch. The actual previous release tags remain available for rollback.
if [[ -n "${rollback_tag:-}" ]]; then
  docker image rm "aitrading/trade-review-api:$rollback_tag" >/dev/null 2>&1 || true
  docker image rm "aitrading/trade-review-frontend:$rollback_tag" >/dev/null 2>&1 || true
fi
