"""Offline checks for fixed application inputs and base-image resolution."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_COMMIT = "a6d862f43d825289dd219088d5187931ca7493d6"
ESPOCRM_SHA256 = "e02583050c5f5a7e98cd12f9431870fc606581a62c10c5e4ef6dc091e882c18d"


class BuildInputsTest(unittest.TestCase):
    def test_application_inputs_are_fixed(self):
        dockerfile = (ROOT / "Dockerfile").read_text()
        self.assertIn(f"espocrm-docker.git#{UPSTREAM_COMMIT}", dockerfile)
        self.assertIn("ENV ESPOCRM_VERSION=9.3.8\n", dockerfile)
        self.assertIn(f"ENV ESPOCRM_SHA256={ESPOCRM_SHA256}\n", dockerfile)
        self.assertIn("https://www.espocrm.com/downloads/EspoCRM-9.3.8.zip", dockerfile)
        self.assertIn('sha256sum -c -', dockerfile)
        self.assertNotIn("ARG ESPOCRM_VERSION", dockerfile)
        self.assertNotIn("ARG ESPOCRM_SHA256", dockerfile)

    def test_generated_scripts_and_license_come_from_same_commit(self):
        dockerfile = (ROOT / "Dockerfile").read_text()
        self.assertIn("/upstream/latest/apache/docker-*.sh /usr/local/bin/", dockerfile)
        self.assertIn("/upstream/LICENSE /usr/local/share/espocrm-build/LICENSE", dockerfile)

    def test_shell_syntax(self):
        for script in (ROOT / "scripts").glob("*.sh"):
            with self.subTest(script=script.name):
                subprocess.run(["bash", "-n", str(script)], check=True)

    def test_license_matches_upstream(self):
        content = (ROOT / "LICENSE").read_bytes()
        git_object = b"blob " + str(len(content)).encode() + b"\0" + content
        self.assertEqual(
            hashlib.sha1(git_object).hexdigest(),
            "be3f7b28e564e7dd05eaf59d64adba1a4065ac0e",
        )

    def test_dockerfile_run_shell_syntax(self):
        instruction = ""
        for line in (ROOT / "Dockerfile").read_text().splitlines():
            if line.endswith("\\"):
                instruction += line[:-1]
                continue
            instruction += line + "\n"
            if instruction.startswith("RUN "):
                subprocess.run(["sh", "-n"], input=instruction[4:], text=True, check=True)
            instruction = ""


class ResolveBaseTest(unittest.TestCase):
    def resolve(self, manifest, docker_status=0, max_attempts=1, manifest_sequence=None):
        with tempfile.TemporaryDirectory() as directory:
            docker = Path(directory) / "docker"
            counter = Path(directory) / "counter"
            docker.write_text(
                '#!/usr/bin/env python3\n'
                'import json\n'
                'import os\n'
                'import pathlib\n'
                'import sys\n'
                'status = int(os.environ["TEST_DOCKER_STATUS"])\n'
                'if status:\n'
                '    sys.exit(status)\n'
                'sequence = os.environ.get("TEST_MANIFEST_SEQUENCE")\n'
                'if sequence:\n'
                '    manifests = json.loads(sequence)\n'
                '    counter = pathlib.Path(os.environ["TEST_DOCKER_COUNTER"])\n'
                '    index = int(counter.read_text()) if counter.exists() else 0\n'
                '    counter.write_text(str(index + 1))\n'
                '    manifest = manifests[index if index < len(manifests) else -1]\n'
                '    print(json.dumps(manifest))\n'
                'else:\n'
                '    print(os.environ["TEST_MANIFEST"])\n'
            )
            docker.chmod(0o755)
            env = dict(os.environ)
            env.update(
                PATH=directory + os.pathsep + env["PATH"],
                TEST_MANIFEST=json.dumps(manifest),
                TEST_DOCKER_STATUS=str(docker_status),
                TEST_DOCKER_COUNTER=str(counter),
                RESOLVE_BASE_MAX_ATTEMPTS=str(max_attempts),
                RESOLVE_BASE_RETRY_DELAY_SECONDS="0",
            )
            if manifest_sequence is not None:
                env["TEST_MANIFEST_SEQUENCE"] = json.dumps(manifest_sequence)
            return subprocess.run(
                ["bash", str(ROOT / "scripts/resolve-base.sh"),
                 "php:8.4.27-apache-trixie"],
                env=env, capture_output=True, text=True,
            )

    def test_selects_amd64_and_returns_digest_reference(self):
        digest = "sha256:" + "a" * 64
        result = self.resolve({"manifests": [
            {"platform": {"os": "linux", "architecture": "arm64"},
             "digest": "sha256:" + "b" * 64},
            {"platform": {"os": "linux", "architecture": "amd64"},
             "digest": digest},
        ]})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), f"php:8.4.27-apache-trixie@{digest}")

    def test_rejects_placeholder(self):
        result = self.resolve({"manifests": []})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("release placeholder", result.stderr)

    def test_rejects_other_architecture(self):
        result = self.resolve({"manifests": [
            {"platform": {"os": "linux", "architecture": "arm64"},
             "digest": "sha256:" + "a" * 64},
        ]})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_rejects_malformed_digest(self):
        result = self.resolve({"manifests": [
            {"platform": {"os": "linux", "architecture": "amd64"},
             "digest": "not-a-digest"},
        ]})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_propagates_registry_failure(self):
        result = self.resolve({}, docker_status=42)
        self.assertEqual(result.returncode, 42)
        self.assertEqual(result.stdout, "")

    def test_retries_placeholder_until_manifest_is_published(self):
        digest = "sha256:" + "a" * 64
        result = self.resolve(
            {},
            max_attempts=2,
            manifest_sequence=[
                {"manifests": []},
                {"manifests": [
                    {"platform": {"os": "linux", "architecture": "amd64"},
                     "digest": digest},
                ]},
            ],
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), f"php:8.4.27-apache-trixie@{digest}")


class SmokeTestHarnessTest(unittest.TestCase):
    """Check orchestration with a fake Docker CLI; not actual runtime tests."""

    def run_smoke_test(self, platform="linux/amd64", cli_status=0,
                       apache_response="8.4.27:apache2handler"):
        with tempfile.TemporaryDirectory() as directory:
            docker = Path(directory) / "docker"
            log = Path(directory) / "commands.jsonl"
            docker.write_text('''#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
with open(os.environ["TEST_DOCKER_LOG"], "a") as log:
    log.write(json.dumps(args) + "\\n")
if args[:2] == ["image", "inspect"]:
    print(os.environ["TEST_PLATFORM"])
elif args[0] == "run" and "--detach" in args:
    print("temporary-smoke-test-container")
elif args[0] == "run" and args[args.index("--entrypoint") + 1] == "php":
    sys.exit(int(os.environ["TEST_CLI_STATUS"]))
elif args[0] == "exec":
    print(os.environ["TEST_APACHE_RESPONSE"], end="")
''')
            docker.chmod(0o755)
            env = dict(os.environ)
            env.update(
                PATH=directory + os.pathsep + env["PATH"],
                TEST_DOCKER_LOG=str(log),
                TEST_PLATFORM=platform,
                TEST_CLI_STATUS=str(cli_status),
                TEST_APACHE_RESPONSE=apache_response,
            )
            result = subprocess.run(
                ["bash", str(ROOT / "scripts/smoke-test.sh"), "test:image", "8.4.27"],
                env=env, capture_output=True, text=True, timeout=10,
            )
            commands = [json.loads(line) for line in log.read_text().splitlines()]
            return result, commands

    def test_success_uses_isolated_containers_and_cleans_up(self):
        result, commands = self.run_smoke_test()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("HTTP smoke test passed", result.stdout)
        for command in commands:
            if command[0] == "run":
                self.assertIn("--entrypoint", command)
                self.assertEqual(command[command.index("--network") + 1], "none")
                self.assertNotIn("--publish", command)
                self.assertNotIn("--volume", command)
        self.assertEqual(commands[-1], ["rm", "--force", "temporary-smoke-test-container"])

    def test_wrong_platform_stops_before_running_containers(self):
        result, commands = self.run_smoke_test(platform="linux/arm64")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(commands), 1)

    def test_cli_failure_stops_before_apache(self):
        result, commands = self.run_smoke_test(cli_status=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any("--detach" in command for command in commands))

    def test_wrong_apache_version_fails_and_cleans_up(self):
        result, commands = self.run_smoke_test(apache_response="8.4.21:apache2handler")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unexpected Apache PHP response", result.stderr)
        self.assertEqual(commands[-1], ["rm", "--force", "temporary-smoke-test-container"])


if __name__ == "__main__":
    unittest.main()
