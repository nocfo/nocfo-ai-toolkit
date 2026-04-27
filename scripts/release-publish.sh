#!/usr/bin/env bash

set -euo pipefail

RELEASE_BRANCH="${RELEASE_BRANCH:-main}"

for ARGUMENT in "$@"; do
  KEY="$(echo "$ARGUMENT" | cut -f1 -d=)"
  KEY_LENGTH=${#KEY}
  VALUE="${ARGUMENT:$KEY_LENGTH+1}"
  export "$KEY"="$VALUE"
done

if [[ -z "${VERSION:-}" || -z "${BUILD_TAG:-}" ]]; then
  echo "Error: VERSION and BUILD_TAG must be supplied."
  exit 1
fi

if [[ -z "${POETRY_PYPI_TOKEN_PYPI:-}" ]]; then
  echo "Error: POETRY_PYPI_TOKEN_PYPI is required for PyPI publish."
  exit 1
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Error: release must run inside a git repository."
  exit 1
fi

git fetch origin "${RELEASE_BRANCH}" --tags --prune

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Error: git working tree must be clean before release."
  exit 1
fi

UNTRACKED_FILES="$(git ls-files --others --exclude-standard)"
if [[ -n "${UNTRACKED_FILES}" ]]; then
  if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then
    echo "Info: untracked files present in CI workspace; continuing."
    printf '%s\n' "${UNTRACKED_FILES}"
  else
    echo "Error: untracked files detected. Commit/stash/remove before release."
    printf '%s\n' "${UNTRACKED_FILES}"
    exit 1
  fi
fi

CURRENT_COMMIT="$(git rev-parse HEAD)"
REMOTE_COMMIT="$(git rev-parse "origin/${RELEASE_BRANCH}")"

if [[ "${CURRENT_COMMIT}" != "${REMOTE_COMMIT}" ]]; then
  echo "Error: release must run from origin/${RELEASE_BRANCH} HEAD."
  echo "Current: ${CURRENT_COMMIT}"
  echo "Remote : ${REMOTE_COMMIT}"
  exit 1
fi

EXPECTED_TAG="v${VERSION}"
if [[ "${BUILD_TAG}" != "${EXPECTED_TAG}" ]]; then
  echo "Error: BUILD_TAG (${BUILD_TAG}) must match VERSION (${VERSION}) as ${EXPECTED_TAG}."
  exit 1
fi

./scripts/build-and-push-to-ecr.sh "BUILD_TAG=${BUILD_TAG}"

echo "Publishing PyPI package version ${VERSION}..."
poetry version "${VERSION}"
poetry build
poetry publish --skip-existing --no-interaction --no-ansi

echo "Release publish completed for ${BUILD_TAG} (${VERSION})"
