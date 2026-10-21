#!/usr/bin/env bash
set -euo pipefail

base_image=${1:?Usage: bash scripts/resolve-base.sh php:VERSION-apache-trixie}
max_attempts=${RESOLVE_BASE_MAX_ATTEMPTS:-20}
retry_delay_seconds=${RESOLVE_BASE_RETRY_DELAY_SECONDS:-15}

# imagetools works without a running Docker daemon. Its formatted manifest
# includes the digest as well as platform descriptors.
for ((attempt = 1; attempt <= max_attempts; attempt++)); do
    if manifest=$(docker buildx imagetools inspect "$base_image" --format '{{json .Manifest}}'); then
        :
    else
        status=$?
        exit "$status"
    fi

    if digest=$(printf '%s\n' "$manifest" | jq -er '
        first(.manifests[]? | select(
            .platform.os == "linux" and .platform.architecture == "amd64"
        )) | .digest // empty | select(test("^sha256:[0-9a-f]{64}$"))
    '); then
        printf '%s@%s\n' "$base_image" "$digest"
        exit 0
    fi

    if ((attempt < max_attempts)); then
        printf 'No valid linux/amd64 manifest is available for %s (attempt %d/%d).\n' \
            "$base_image" "$attempt" "$max_attempts" >&2
        printf 'The upstream tag may still be a release placeholder. Retrying in %ss.\n' \
            "$retry_delay_seconds" >&2
        sleep "$retry_delay_seconds"
    fi
done

printf 'No valid linux/amd64 manifest is available for %s.\n' "$base_image" >&2
printf 'The upstream tag may still be a release placeholder. Retry after publication.\n' >&2
exit 1
