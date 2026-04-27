#!/usr/bin/env bash

set -euo pipefail

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

./scripts/build-and-push-to-ecr.sh "BUILD_TAG=${BUILD_TAG}"

echo "Publishing PyPI package version ${VERSION}..."
poetry version "${VERSION}"
poetry build
poetry publish --skip-existing --no-interaction --no-ansi

echo "Release publish completed for ${BUILD_TAG} (${VERSION})"
