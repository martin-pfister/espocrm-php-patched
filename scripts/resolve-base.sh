#!/usr/bin/env bash
set -euo pipefail

base_image=${1:?Usage: bash scripts/resolve-base.sh php:VERSION-apache-trixie}

# imagetools works without a running Docker daemon. Its formatted manifest
# includes the digest as well as platform descriptors.
manifest=$(docker buildx imagetools inspect "$base_image" --format '{{json .Manifest}}')

if ! digest=$(printf '%s\n' "$manifest" | jq -er '
    first(.manifests[]? | select(
        .platform.os == "linux" and .platform.architecture == "amd64"
    )) | .digest // empty | select(test("^sha256:[0-9a-f]{64}$"))
'); then
    printf 'No valid linux/amd64 manifest is available for %s.\n' "$base_image" >&2
    printf 'The upstream tag may still be a release placeholder. Retry after publication.\n' >&2
    exit 1
fi

printf '%s@%s\n' "$base_image" "$digest"
