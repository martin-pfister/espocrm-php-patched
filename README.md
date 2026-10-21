# EspoCRM with patched PHP

Unofficial rebuild of the official EspoCRM Docker image, keeping **EspoCRM
9.3.8** while updating its PHP runtime to **8.4.26**. Not affiliated with or
endorsed by EspoCRM.

```text
ghcr.io/martin-pfister/espocrm-php-patched:9.3.8-php8.4.26
```

Only **linux/amd64** is built and tested. The image is published after a
successful GitHub Actions build and smoke test; this README is not a claim
that an image has already been published.

> This updates PHP, not EspoCRM. It does **not** fix vulnerabilities in
> EspoCRM 9.3.8 itself, guarantee that the entire image is vulnerability-free,
> or replace a longer-term application upgrade plan.

## Why rebuild?

The official EspoCRM image uses the Docker Official PHP image, whose PHP
runtime is compiled into `/usr/local`. Running `apt upgrade` does not upgrade
that PHP runtime.

On October 21, 2026, PHP released fixes for critical vulnerabilities
[CVE-2026-109618 and CVE-2026-109619](https://www.php.net/archive/2026.php#2026-10-21-5).
PHP 8.4.26 contains the fixes for the 8.4 branch. Both PHP CLI and Apache's
PHP module must be updated; replacing only the CLI binary is insufficient.

## Build approach

This is a rebuild of the historical image recipe, **not** a binary transplant
into the old image and **not** an independent build of the EspoCRM application.

| Input | Selection |
| --- | --- |
| Upstream Docker recipe and startup scripts | [`espocrm/espocrm-docker@a6d862f43d825289dd219088d5187931ca7493d6`](https://github.com/espocrm/espocrm-docker/tree/a6d862f43d825289dd219088d5187931ca7493d6/latest/apache) (9.3.8) |
| PHP base | `php:8.4.26-apache-trixie` |
| EspoCRM archive | [`EspoCRM-9.3.8.zip`](https://www.espocrm.com/downloads/EspoCRM-9.3.8.zip) |
| Archive SHA-256 | `e02583050c5f5a7e98cd12f9431870fc606581a62c10c5e4ef6dc091e882c18d` |
| PECL extensions | ev **1.2.3**, Redis **6.3.0** |
| ZeroMQ extension source | [`616b6c64ffd3866ed038615494306dd464ab53fc`](https://github.com/zeromq/php-zmq/tree/616b6c64ffd3866ed038615494306dd464ab53fc) (as upstream) |

The Dockerfile:

1. Fetches the historical Docker repository at the exact commit above.
2. Uses the patched PHP Apache/Trixie base and rebuilds the original set of
   additional PHP extensions against it.
3. Downloads the original EspoCRM 9.3.8 archive and checks its SHA-256 before
   extraction. Application version and checksum are not build arguments.
4. Copies the **generated** `latest/apache/docker-*.sh` scripts unchanged
   from that commit, including their embedded configuration helpers.
5. Retains upstream's PHP settings, Apache rewrite support, entrypoint and
   daemon/websocket commands.

The workflow resolves the PHP tag to its **linux/amd64 manifest digest**
before building and records that reference in the image labels and run
summary. An absent platform or an empty release-placeholder manifest causes
the workflow to fail; it never falls back to an older PHP image.

Differences from the historical recipe are the PHP base, explicit PECL
version pins, metadata and the commit-pinned source stage. The unmodified
upstream Dockerfile and license are included in the image under
`/usr/local/share/espocrm-build/`.

**This is not a bit-for-bit reproduction of the original image with only one
binary changed.** Rebuilding also uses current Debian packages and the stated
extension versions. Debian package versions are not snapshot-pinned. Review
and test each build; use its final image digest for an exact deployment.

## Existing installations and persistent volumes

The image bundles EspoCRM in `/usr/src/espocrm`; the historical entrypoint
initializes or upgrades an installation in `/var/www/html`.

For an existing **9.3.8** installation mounted at `/var/www/html`, the matching
target version should not trigger an application upgrade. The PHP runtime is
outside that mount, so replacing the container updates PHP while retaining
application data, uploads and customizations.

Upstream's startup logic is unchanged: **there is no additional version
assertion or startup guard.** An older installation may trigger upstream's
normal upgrade path; a newer installation is not automatically downgraded.
This image is intended for an installation already confirmed to be 9.3.8.
It does not enforce the version of files supplied by an external volume.

Keep the existing `/var/www/html` mount layout. Do not combine this runtime
update with the volume-layout changes used by newer EspoCRM releases.

## Publish with GitHub Actions

1. Create the public repository `martin-pfister/espocrm-php-patched` and push
   these files to its `main` branch. Enable GitHub Actions if necessary.
2. The workflow builds and tests pull requests without publishing. Pushes
   to `main`, and manual runs on `main`, publish after tests pass.
3. Authentication uses the workflow's built-in `GITHUB_TOKEN` with
   `packages: write`; no personal access token is needed. Organization or
   repository policies must permit this permission.
4. After the first successful publication, open the GitHub package's
   **Package settings → Change visibility → Public**. A public repository
   does not automatically make a newly created GHCR package public.
5. Copy the production digest reference from the workflow run summary.

Each publication has two tags:

- `9.3.8-php8.4.26`: a convenience tag, updated by subsequent successful builds.
- `9.3.8-php8.4.26-build.<run-id>.<attempt>`: a build-specific tag.

The workflow loads the image locally, tests it, then pushes **that same image
without rebuilding**. It checks the architecture, PHP CLI version, required
extensions, startup-script syntax, Apache configuration and the PHP version
served by Apache over HTTP. Smoke tests use no production volumes or
database and publish no host ports. They are not application integration
tests and do not validate LDAP credentials, jobs or websocket connections.

Public packages and standard GitHub-hosted runners for public repositories
are free under [GitHub's current Packages](https://docs.github.com/en/billing/concepts/product-billing/github-packages)
and [Actions](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
policies. Avoid paid larger runners and unnecessary artifact/cache storage.

## Build and test locally

Requires Docker with Buildx/BuildKit, Bash and `jq`. Run from the repository
root. A non-amd64 host needs amd64 emulation configured to execute build
steps and smoke tests.

```sh
PHP_BASE_IMAGE=$(bash scripts/resolve-base.sh php:8.4.26-apache-trixie)
docker buildx build --platform linux/amd64 --pull --load \
  --build-arg "PHP_BASE_IMAGE=$PHP_BASE_IMAGE" \
  --tag espocrm-php-patched:test .
bash scripts/smoke-test.sh espocrm-php-patched:test 8.4.26
```

If resolution reports a release placeholder, wait for the official PHP
image's amd64 publication and rerun. Do not substitute an older PHP release.

Offline repository checks require Python 3, Bash and `jq`, but no Docker daemon:

```sh
python3 -m unittest discover -s tests -v
```

The Docker build context is allowlisted to the Dockerfile and `.dockerignore`.
Do not commit credentials, `.env` files, deployment volumes or private LDAP
customizations to this public repository.

## Deploy to an existing Compose stack

Before deploying:

- Back up the **database and complete application volume consistently**.
- Record the current image digest and Compose configuration for rollback.
- Confirm the application is 9.3.8 in its About dialog or inspect only its
  version value, not its secret-bearing configuration:

  ```sh
  docker exec espocrm php -r '$c = require "/var/www/html/application/Espo/Resources/defaults/config.php"; echo $c["version"] ?? "not found", PHP_EOL;'
  ```

- Test against isolated copies of the database and application volume first.
  Disable outbound email, scheduled jobs and external integration side effects
  in staging. **Never share production data mounts with a test deployment.**
- Keep public access disabled until post-deployment checks pass.

Change the `image` in **all three** EspoCRM services, without changing their
mounts, environment, labels or entrypoints:

```yaml
services:
  espocrm:
    image: ghcr.io/martin-pfister/espocrm-php-patched:9.3.8-php8.4.26
  espocrm-daemon:
    image: ghcr.io/martin-pfister/espocrm-php-patched:9.3.8-php8.4.26
  espocrm-websocket:
    image: ghcr.io/martin-pfister/espocrm-php-patched:9.3.8-php8.4.26
```

This snippet shows **only the image changes**, not a complete Compose file.
For production, replace each tag reference with the same verified
`ghcr.io/martin-pfister/espocrm-php-patched@sha256:...` reference from the run
summary. Leave MariaDB and Traefik unchanged for this update.

With the database running, during the maintenance window:

```sh
docker compose pull espocrm espocrm-daemon espocrm-websocket
docker compose stop espocrm espocrm-daemon espocrm-websocket
docker compose up -d --no-deps espocrm espocrm-daemon espocrm-websocket
```

Retain any existing LDAP file bind mount on the web service. An override
mounted only on that service is still not present in the daemon/websocket
containers; the rebuild does not change this behavior.

Before restoring public access:

```sh
docker compose exec -T espocrm php -v
docker compose exec -T espocrm-daemon php -v
docker compose exec -T espocrm-websocket php -v
docker compose logs --tail=100 espocrm espocrm-daemon espocrm-websocket
```

Confirm PHP 8.4.26 in all three services, EspoCRM 9.3.8, successful LDAP login,
uploads, scheduled jobs and websocket functionality. The CI HTTP smoke test
checks Apache's module as well as CLI; `php -v` alone checks only CLI.

### Rollback

Keep public access disabled, stop all three EspoCRM services, restore their
previous image references and recreate them. If application or database
state changed during testing/deployment, restore a matching backup pair as
needed. Returning to the old image also returns to vulnerable PHP: **do not
re-expose it publicly as a security workaround**.

## Maintenance

- For another PHP security update, change the explicit `PHP_BASE_IMAGE`
  default in `Dockerfile`. The workflow derives the PHP version and image
  tag from it. Keep the EspoCRM commit, archive and checksum unchanged when
  the intent is still a PHP-only application-version-preserving rebuild.
- Review extension compatibility and explicit PECL pins. Do not silently
  switch to the current EspoCRM Docker repository's `master` or `latest`.
- Rerun the build after the official PHP image is available. The base digest
  is fixed for that run, but later builds may resolve a refreshed base.
- Test every build in staging and pin its published digest. This repository
  performs no automatic production deployments or scheduled rebuilds.
- Plan an EspoCRM application upgrade separately; keeping 9.3.8 indefinitely
  is not a complete security maintenance strategy.

## Upstream, source and licensing

This repository's build recipe is adapted from EspoCRM's Docker repository.
See [NOTICE.md](NOTICE.md) and [LICENSE](LICENSE) (GNU AGPLv3). The application
archive and its notices are retained unchanged, including EspoCRM's additional
legal-notice requirements. Other components retain their own licenses.

Sources and build instructions are available here and at:

- [Historical Docker build context](https://github.com/espocrm/espocrm-docker/tree/a6d862f43d825289dd219088d5187931ca7493d6/latest/apache)
- [EspoCRM 9.3.8 source](https://github.com/espocrm/espocrm/tree/9.3.8)
- [Original EspoCRM 9.3.8 distribution archive](https://www.espocrm.com/downloads/EspoCRM-9.3.8.zip)
- [Docker Official PHP image sources](https://github.com/docker-library/php)
- [PHP 8.4.26 source](https://www.php.net/distributions/php-8.4.26.tar.xz)

No production application files, credentials or private customizations are
included. Images are provided without warranty.
