# EspoCRM with patched PHP

> [!WARNING]
> ## Switch to the official EspoCRM 9.3.10 image
>
> EspoCRM published a refreshed **9.3.10** container on **2026-10-22** with a fixed PHP version.
> **Use [`espocrm/espocrm:9.3.10`](https://hub.docker.com/layers/espocrm/espocrm/9.3.10) instead of this unofficial image.**
>
> Make sure to pull the refreshed image rather than reusing a cached 9.3.10 image.

Unofficial **EspoCRM 9.3.8 / PHP 8.4.27** image for **linux/amd64**:

```text
ghcr.io/martin-pfister/espocrm-php-patched:9.3.8-php8.4.27
```

## How it works

The [workflow](.github/workflows/image.yml) checks out
[upstream tag `9.3.8`](https://github.com/espocrm/espocrm-docker/tree/9.3.8),
[patches only the PHP base](patches/php-base.patch), and builds the original context:

```diff
-FROM php:8.4-apache-trixie
+FROM php:8.4.27-apache-trixie
```

Everything else in the upstream Dockerfile and scripts stays unchanged,
including unpinned Debian/PECL dependencies. The PHP base uses a patch-version
tag, not a digest, so base-image rebuilds can change subsequent builds.
CI tests CLI, extensions and Apache, then publishes that same image to GHCR.
The run summary records the upstream commit, PHP base tag and published image digest.

Push to `main` or run the workflow manually on `main` to publish. Pull requests
only build and test. Make the GHCR package public after its first publication.

## Use

- Back up and test your existing **9.3.8** installation first.
- Replace the image in `espocrm`, `espocrm-daemon` and `espocrm-websocket`,
  preserving mounts and configuration, then recreate those containers.
- Prefer the published digest over the mutable tag. Verify PHP and application
  functionality before restoring public access.

This updates PHP, not EspoCRM application code. Upstream startup/upgrade
behavior is unchanged.
The smoke test does not exercise installation, upgrades, or database access.

## Update

- PHP version: edit `patches/php-base.patch`.
- EspoCRM tag: edit `ESPOCRM_VERSION` in the workflow; test application upgrades separately.
- Keep the version examples above current. Run `bash -n scripts/smoke-test.sh`
  before pushing; CI checks the patch against upstream and smoke-tests the image.

## License

[AGPLv3](LICENSE). Build patch adapted from upstream on October 22, 2026.
EspoCRM is copyright EspoCRM, Inc. and its contributors; upstream licenses and
legal notices remain intact. Not affiliated with EspoCRM. No warranty.
