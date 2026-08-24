#!/usr/bin/env bash
set -Eeuo pipefail

DEPLOY_ROOT="${DEPLOY_ROOT:-/opt/trade-review-agent}"
STATE_DIR="$DEPLOY_ROOT/.deploy"

# Stopped containers are safe to remove. Running containers, volumes, networks,
# and Docker build cache are deliberately outside this cleanup policy.
docker container prune -f \
  --filter "label=com.aitrading.managed=true" \
  --filter "until=168h" >/dev/null

declare -A keep=()
for state_file in "$STATE_DIR/current-images.env" "$STATE_DIR/previous-images.env"; do
  if [[ -f "$state_file" ]]; then
    while IFS='=' read -r key value; do
      case "$key" in
        API_IMAGE|FRONTEND_IMAGE) [[ -n "$value" ]] && keep["$value"]=1 ;;
      esac
    done < "$state_file"
  fi
done

while IFS= read -r image_ref; do
  [[ -z "$image_ref" ]] && continue
  case "$image_ref" in
    aitrading/trade-review-api:*|aitrading/trade-review-frontend:*) ;;
    *) continue ;;
  esac
  if [[ -z "${keep[$image_ref]+x}" ]]; then
    docker image rm "$image_ref" >/dev/null 2>&1 || true
  fi
done < <(docker image ls --filter "label=com.aitrading.managed=true" --format '{{.Repository}}:{{.Tag}}')

# Keep only current and previous release directories. Uploaded archives are no
# longer needed after docker load and are deleted immediately by the deployer.
current_tag="$(cat "$STATE_DIR/current-release" 2>/dev/null || true)"
previous_tag="$(cat "$STATE_DIR/previous-release" 2>/dev/null || true)"
if [[ -d "$STATE_DIR/releases" ]]; then
  while IFS= read -r -d '' release_dir; do
    tag="$(basename "$release_dir")"
    if [[ "$tag" != "$current_tag" && "$tag" != "$previous_tag" ]]; then
      rm -rf -- "$release_dir"
    fi
  done < <(find "$STATE_DIR/releases" -mindepth 1 -maxdepth 1 -type d -print0)
fi

# Do not run docker image prune -af or docker builder prune here. Those commands
# caused the next production deploy to perform a full build on a 2 GB server.
