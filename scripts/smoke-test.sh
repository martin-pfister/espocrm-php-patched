#!/usr/bin/env bash
set -euo pipefail

image=${1:?Usage: bash scripts/smoke-test.sh IMAGE EXPECTED_PHP_VERSION}
expected_php_version=${2:?Expected PHP patch version is required}

platform=$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$image")
if [ "$platform" != linux/amd64 ]; then
    printf 'Expected linux/amd64, got %s\n' "$platform" >&2
    exit 1
fi

# Bypass EspoCRM's entrypoint: these tests must not install an application,
# connect to a database, or touch a production volume.
docker run --rm --network none --entrypoint php \
    -e EXPECTED_PHP_VERSION="$expected_php_version" "$image" -r '
    if (PHP_VERSION !== getenv("EXPECTED_PHP_VERSION")) {
        fwrite(STDERR, "Unexpected PHP version: " . PHP_VERSION . PHP_EOL);
        exit(1);
    }
    $required = [
        "bcmath", "curl", "dom", "ev", "exif", "fileinfo", "gd", "ldap",
        "mbstring", "openssl", "pcntl", "pdo_mysql", "pdo_pgsql", "posix",
        "redis", "sodium", "zip", "zmq", "Zend OPcache",
    ];
    foreach ($required as $extension) {
        if (!extension_loaded($extension)) {
            fwrite(STDERR, "Missing extension: " . $extension . PHP_EOL);
            exit(1);
        }
    }
    echo "PHP ", PHP_VERSION, ": required extensions loaded", PHP_EOL;
    '

docker run --rm --network none --entrypoint bash "$image" -ec '
    for script in docker-entrypoint.sh docker-daemon.sh docker-websocket.sh; do
        test -x "/usr/local/bin/$script"
        bash -n "/usr/local/bin/$script"
    done
'
docker run --rm --network none --entrypoint apache2ctl "$image" -t

# Exercise Apache's actual PHP module, not just the CLI. Nothing is exposed on
# the host: curl runs inside this temporary, network-isolated container.
container_id=
cleanup() {
    if [ -n "$container_id" ]; then
        docker rm --force "$container_id" > /dev/null
    fi
}
trap cleanup EXIT

container_id=$(docker run --detach --network none --entrypoint sh "$image" -ec '
    echo "<?php echo PHP_VERSION, chr(58), PHP_SAPI;" > /var/www/html/php-runtime-check.php
    exec apache2-foreground
')

response=
for attempt in $(seq 1 30); do
    if response=$(docker exec "$container_id" curl --fail --silent --show-error \
        --max-time 2 http://127.0.0.1/php-runtime-check.php 2>/dev/null); then
        break
    fi
    sleep 1
done

if [ "$response" != "$expected_php_version:apache2handler" ]; then
    printf 'Unexpected Apache PHP response: %s\n' "$response" >&2
    docker logs "$container_id" >&2
    exit 1
fi

printf 'Apache PHP %s: HTTP smoke test passed\n' "$expected_php_version"
