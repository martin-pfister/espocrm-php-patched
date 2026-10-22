"""Offline checks for the one-line patch and base-image resolver."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATCH = (ROOT / "patches/php-base.patch").read_text()
OLD_BASE = "FROM php:8.4-apache-trixie"
NEW_BASE = "FROM php:8.4.27-apache-trixie"

# The real upstream header/context; the tail detects unrelated file changes.
UPSTREAM = '''#
# NOTE: THIS DOCKERFILE IS GENERATED VIA "apply-templates.sh"
#
# PLEASE DO NOT EDIT IT DIRECTLY.
#

FROM php:8.4-apache-trixie

LABEL org.opencontainers.image.source=https://github.com/espocrm/espocrm
LABEL org.opencontainers.image.description="EspoCRM is a free and open-source CRM platform."

# Everything after the header must remain unchanged.
'''


class PatchTest(unittest.TestCase):
    def apply_patch(self, source=UPSTREAM, patch=PATCH):
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(["git", "init", "--quiet", "--initial-branch=main", directory], check=True)
            dockerfile = Path(directory) / "latest/apache/Dockerfile"
            dockerfile.parent.mkdir(parents=True)
            dockerfile.write_text(source)
            for args in (["--check", "-"], ["-"]):
                result = subprocess.run(
                    ["git", "apply", "--unidiff-zero", *args], cwd=directory, input=patch,
                    capture_output=True, text=True,
                )
                if result.returncode:
                    break
            return result, dockerfile.read_text()

    def test_patch_changes_only_from(self):
        changes = [line for line in PATCH.splitlines()
                   if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))]
        self.assertEqual(changes, ["-" + OLD_BASE, "+" + NEW_BASE])
        result, content = self.apply_patch()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(content, UPSTREAM.replace(OLD_BASE, NEW_BASE))

    def test_ci_digest_substitution_still_changes_only_from(self):
        resolved = NEW_BASE + "@sha256:" + "a" * 64
        patch = PATCH.replace("+" + NEW_BASE, "+" + resolved)
        result, content = self.apply_patch(patch=patch)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(content, UPSTREAM.replace(OLD_BASE, resolved))

    def test_unexpected_upstream_base_fails_without_changes(self):
        source = UPSTREAM.replace(OLD_BASE, "FROM php:8.5-apache-trixie")
        result, content = self.apply_patch(source=source)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(content, source)

    def test_shell_syntax(self):
        for script in (ROOT / "scripts").glob("*.sh"):
            with self.subTest(script=script.name):
                subprocess.run(["bash", "-n", str(script)], check=True)


class ResolveBaseTest(unittest.TestCase):
    def resolve(self, manifests, status=0):
        with tempfile.TemporaryDirectory() as directory:
            docker = Path(directory) / "docker"
            docker.write_text('#!/usr/bin/env bash\n'
                              'printf "%s\\n" "$TEST_MANIFEST"\n'
                              'exit "$TEST_STATUS"\n')
            docker.chmod(0o755)
            env = dict(os.environ, PATH=directory + os.pathsep + os.environ["PATH"],
                       TEST_MANIFEST=json.dumps({"manifests": manifests}),
                       TEST_STATUS=str(status))
            return subprocess.run(
                ["bash", str(ROOT / "scripts/resolve-base.sh"), "php:8.4.27-apache-trixie"],
                env=env, capture_output=True, text=True,
            )

    def test_selects_amd64_digest(self):
        digest = "sha256:" + "a" * 64
        result = self.resolve([
            {"platform": {"os": "linux", "architecture": "arm64"},
             "digest": "sha256:" + "b" * 64},
            {"platform": {"os": "linux", "architecture": "amd64"}, "digest": digest},
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), f"php:8.4.27-apache-trixie@{digest}")

    def test_rejects_unavailable_platform_or_invalid_digest(self):
        for manifests in (
            [],
            [{"platform": {"os": "linux", "architecture": "arm64"},
              "digest": "sha256:" + "a" * 64}],
            [{"platform": {"os": "linux", "architecture": "amd64"}, "digest": "invalid"}],
        ):
            with self.subTest(manifests=manifests):
                result = self.resolve(manifests)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")

    def test_propagates_registry_failure(self):
        result = self.resolve([], status=42)
        self.assertEqual(result.returncode, 42)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
