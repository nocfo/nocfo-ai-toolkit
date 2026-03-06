#!/usr/bin/env bash

set -euo pipefail

for ARGUMENT in "$@"; do
  KEY="$(echo "$ARGUMENT" | cut -f1 -d=)"
  KEY_LENGTH=${#KEY}
  VALUE="${ARGUMENT:$KEY_LENGTH+1}"
  export "$KEY"="$VALUE"
done

if [[ -z "${DEV_BUILD_TAG:-}" && -z "${BUILD_TAG:-}" ]]; then
  echo "Error: Either DEV_BUILD_TAG or BUILD_TAG must be supplied."
  exit 1
fi

AWS_REGION="${AWS_REGION:-eu-west-1}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-141239391012}"
ECR_URL="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
REPOSITORY_NAME="nocfo-mcp"

if [[ -n "${DEV_BUILD_TAG:-}" ]]; then
  IMAGE_TAG="${REPOSITORY_NAME}:${DEV_BUILD_TAG}_dev"
  BUILD_TAG="${DEV_BUILD_TAG}"
else
  IMAGE_TAG="${REPOSITORY_NAME}:${BUILD_TAG}"
fi

ECR_TAG="${ECR_URL}/${IMAGE_TAG}"

echo "Logging in to ECR..."
aws ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin "${ECR_URL}"

echo "Building and pushing image ${ECR_TAG}..."
docker buildx build \
  --platform linux/amd64 \
  --tag "${ECR_TAG}" \
  --file ./Dockerfile \
  --push \
  .

echo "Image pushed: ${ECR_TAG}"
