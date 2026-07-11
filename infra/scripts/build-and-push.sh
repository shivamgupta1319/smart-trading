#!/usr/bin/env bash
set -euo pipefail
# ─────────────────────────────────────────────────────────────────────────────
# RUN ON DEV PC. Build all smart-trading-v2 images from source and push to
# Docker Hub as shivam13gupta/smart-trading-v2-{api,engine,frontend}. work-pc then
# only pulls them (infra/scripts/deploy.sh) — no source/Node/Python needed there.
#
# NOTE ON DOCKER ACCOUNTS: the default docker login on this dev PC is a DIFFERENT
# Hub account (e.g. wisfluxp) that has NO push rights to the shivam13gupta/* repos,
# so a plain `docker push` fails with "denied: requested access to the resource is
# denied". We therefore push via a SECOND, isolated docker config that is logged in
# as shivam13gupta. Override with DOCKER_CFG=... if your account dir differs.
#
# NOTE ON SCANNER + SCHEDULER: both run from the ENGINE image (different command),
# so rebuilding/pushing `engine` is all that is needed to update them too.
# ─────────────────────────────────────────────────────────────────────────────

IMAGE_API="${APP_IMAGE_API:-shivam13gupta/smart-trading-v2-api}"
IMAGE_ENGINE="${APP_IMAGE_ENGINE:-shivam13gupta/smart-trading-v2-engine}"
IMAGE_FRONTEND="${APP_IMAGE_FRONTEND:-shivam13gupta/smart-trading-v2-frontend}"
TAG="${TAG:-latest}"
PLATFORM="${PLATFORM:-linux/amd64}"                  # work-pc is x86_64
DOCKER_CFG="${DOCKER_CFG:-$HOME/.docker-account2}"   # logged in as shivam13gupta; keeps default login untouched

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"         # infra/scripts -> repo root
GIT_SHA="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo dev)"

# Fail early with a clear message if the push account isn't logged in.
if [ ! -f "$DOCKER_CFG/config.json" ]; then
  echo "ERROR: $DOCKER_CFG/config.json not found."
  echo "       Log the shivam13gupta account into an isolated config first, e.g.:"
  echo "         docker --config $DOCKER_CFG login -u shivam13gupta"
  exit 1
fi

echo "==> Repo root : $REPO_ROOT"
echo "==> GIT_SHA   : $GIT_SHA"
echo "==> Platform  : $PLATFORM"
echo "==> Docker cfg: $DOCKER_CFG"
echo "==> Tag       : $TAG"
echo

# Build only the image(s) named as args (api|engine|frontend), or all if none given.
TARGETS=("$@"); [ ${#TARGETS[@]} -eq 0 ] && TARGETS=(api engine frontend)

build_push() {
  local image="$1" dockerfile="$2" context="$3"
  echo "==> Building $image:$TAG  (-f $dockerfile, ctx $context)"
  docker --config "$DOCKER_CFG" build \
    --platform "$PLATFORM" \
    -f "$REPO_ROOT/$dockerfile" \
    -t "$image:$TAG" \
    "$REPO_ROOT/$context"
  echo "==> Pushing $image:$TAG"
  docker --config "$DOCKER_CFG" push "$image:$TAG"
  echo
}

for t in "${TARGETS[@]}"; do
  case "$t" in
    api)      build_push "$IMAGE_API"      "apps/api/Dockerfile"      "." ;;
    engine)   build_push "$IMAGE_ENGINE"   "apps/engine/Dockerfile"   "apps/engine" ;;
    frontend) build_push "$IMAGE_FRONTEND" "apps/frontend/Dockerfile" "." ;;
    *) echo "unknown target: $t (expected api|engine|frontend)"; exit 2 ;;
  esac
done

echo "==> Done. On work-pc:  cd infra && ./scripts/deploy.sh"
echo "    (engine push also refreshes the scanner + scheduler containers)"
