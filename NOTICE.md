# Upstream attribution and modifications

The Dockerfile is adapted from the official EspoCRM Docker image's Apache
build recipe at:

https://github.com/espocrm/espocrm-docker/blob/a6d862f43d825289dd219088d5187931ca7493d6/latest/apache/Dockerfile

Modifications made on October 21, 2026:

- Select PHP 8.4.27 Apache/Trixie instead of the moving PHP 8.4 base tag.
- Pin the ev and Redis PECL extension versions.
- Fetch the complete generated startup scripts from a commit-pinned upstream
  stage rather than a local copy of the build context.
- Add unofficial-image source, version and licensing metadata.
- Include the upstream Dockerfile and license for provenance.
- Add build, smoke-test, publishing and documentation files.

The EspoCRM 9.3.8 application archive, its checksum and upstream generated
startup scripts are unchanged. EspoCRM is copyright EspoCRM, Inc. and its
contributors. Preserve the application's copyright and legal notices,
including its additional legal-notice requirements.

This adapted build recipe and the accompanying project files are distributed
under the GNU Affero General Public License, version 3; see LICENSE.
The image's other components retain their respective licenses.

This is an unofficial project and is not endorsed by EspoCRM, PHP or Docker.
