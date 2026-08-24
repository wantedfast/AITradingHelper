import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from deploy import prebuilt_deploy


ROOT = Path(__file__).parents[1]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def executable_shell(source: str) -> str:
    """Ignore comments so documentation cannot satisfy command contracts."""
    return "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )


class PrebuiltDeployContractTest(unittest.TestCase):
    def test_release_tag_is_inferred_from_standard_archive_name(self) -> None:
        self.assertEqual(
            prebuilt_deploy.release_tag(None, "aitrading-abcdef123456.tar.gz"),
            "abcdef123456",
        )

    def test_release_tag_rejects_mutable_or_shell_unsafe_values(self) -> None:
        for value in ("latest", "main", "abc123;touch-x", "ABCDEF1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                prebuilt_deploy.release_tag(value)

    def test_local_build_accepts_exact_full_git_head(self) -> None:
        head = "a" * 40
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / f"aitrading-{head}.tar.gz"
            archive.write_bytes(b"release")
            with mock.patch.object(
                prebuilt_deploy,
                "parse_args",
                return_value=mock.Mock(
                    archive=None,
                    release_url=None,
                    tag=head,
                    expected_sha256=None,
                ),
            ), mock.patch.object(
                prebuilt_deploy, "command_output", return_value=head
            ), mock.patch.object(
                prebuilt_deploy, "build_archive", return_value=archive
            ) as build, mock.patch.object(prebuilt_deploy, "deploy") as deploy:
                prebuilt_deploy.main()
                build.assert_called_once_with(head, mock.ANY)
                deploy.assert_called_once_with(archive, head, prebuilt_deploy.sha256(archive))

    def test_local_build_rejects_explicit_hex_not_equal_to_full_git_head(self) -> None:
        head = "a" * 40
        for candidate in ("abcdef1", "b" * 40):
            with self.subTest(candidate=candidate), mock.patch.object(
                prebuilt_deploy,
                "parse_args",
                return_value=mock.Mock(
                    archive=None,
                    release_url=None,
                    tag=candidate,
                    expected_sha256=None,
                ),
            ), mock.patch.object(
                prebuilt_deploy, "command_output", return_value=head
            ), mock.patch.object(prebuilt_deploy, "build_archive") as build, mock.patch.object(
                prebuilt_deploy, "deploy"
            ) as deploy:
                with self.assertRaisesRegex(ValueError, "HEAD|git"):
                    prebuilt_deploy.main()
                build.assert_not_called()
                deploy.assert_not_called()

    def test_prebuilt_archive_tag_does_not_need_to_equal_local_head(self) -> None:
        archive_tag = "b" * 40
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / f"aitrading-{archive_tag}.tar.gz"
            archive.write_bytes(b"release")
            with mock.patch.object(
                prebuilt_deploy,
                "parse_args",
                return_value=mock.Mock(
                    archive=archive,
                    release_url=None,
                    tag=archive_tag,
                    expected_sha256=None,
                ),
            ), mock.patch.object(
                prebuilt_deploy, "command_output", return_value="a" * 40
            ), mock.patch.object(prebuilt_deploy, "deploy") as deploy:
                prebuilt_deploy.main()
                deploy.assert_called_once_with(
                    archive.resolve(), archive_tag, prebuilt_deploy.sha256(archive)
                )

    def test_release_url_mode_accepts_validated_archive_tag(self) -> None:
        archive_tag = "c" * 40
        url = f"https://example.invalid/aitrading-{archive_tag}.tar.gz"
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / f"aitrading-{archive_tag}.tar.gz"
            archive.write_bytes(b"release")
            with mock.patch.object(
                prebuilt_deploy,
                "parse_args",
                return_value=mock.Mock(
                    archive=None,
                    release_url=url,
                    tag=None,
                    expected_sha256=None,
                ),
            ), mock.patch.object(
                prebuilt_deploy, "download_archive", return_value=archive
            ) as download, mock.patch.object(
                prebuilt_deploy, "command_output", return_value="a" * 40
            ), mock.patch.object(prebuilt_deploy, "deploy") as deploy:
                prebuilt_deploy.main()
                download.assert_called_once_with(url, mock.ANY)
                deploy.assert_called_once_with(
                    archive, archive_tag, prebuilt_deploy.sha256(archive)
                )

    def test_missing_prebuilt_archive_is_rejected_before_connecting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "aitrading-abcdef1.tar.gz"
            with mock.patch.object(
                prebuilt_deploy,
                "parse_args",
                return_value=mock.Mock(
                    archive=missing,
                    release_url=None,
                    tag="abcdef1",
                    expected_sha256=None,
                ),
            ), mock.patch.object(prebuilt_deploy, "deploy") as deploy:
                with self.assertRaises(FileNotFoundError):
                    prebuilt_deploy.main()
                deploy.assert_not_called()

    def test_archive_checksum_mismatch_is_rejected_before_connecting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "aitrading-abcdef1.tar.gz"
            archive.write_bytes(b"not-a-release")
            with mock.patch.object(
                prebuilt_deploy,
                "parse_args",
                return_value=mock.Mock(
                    archive=archive,
                    release_url=None,
                    tag="abcdef1",
                    expected_sha256="0" * 64,
                ),
            ), mock.patch.object(prebuilt_deploy, "deploy") as deploy:
                with self.assertRaisesRegex(RuntimeError, "SHA-256 mismatch"):
                    prebuilt_deploy.main()
                deploy.assert_not_called()

    def test_local_orchestrator_builds_packages_and_uploads_images(self) -> None:
        source = read("deploy/prebuilt_deploy.py")

        self.assertRegex(source, r"docker(?:\s+compose|-compose).*build")
        self.assertIn("docker save", source)
        self.assertTrue(
            "put(" in source or "scp" in source,
            "release archive must be uploaded by the local orchestrator",
        )
        self.assertIn("remote_release.sh", source)

    def test_orchestrator_accepts_a_prebuilt_archive_without_local_docker(self) -> None:
        source = read("deploy/prebuilt_deploy.py")

        self.assertRegex(source, r"(?:RELEASE_ARCHIVE|release.archive|--archive)")
        self.assertRegex(source, r"exists\(|is_file\(")

    def test_release_tag_is_immutable_and_not_latest(self) -> None:
        local = read("deploy/prebuilt_deploy.py")
        compose = read("docker-compose.release.yml")

        self.assertNotRegex(compose, r"image:\s*[^\n]*:latest(?:\s|$)")
        self.assertEqual(compose.count("${RELEASE_TAG}"), 2)
        self.assertRegex(local, r"RELEASE_TAG")
        self.assertRegex(local, r"(?:git|rev-parse|sha)")

    def test_release_compose_has_no_build_context_and_managed_images_are_labeled(self) -> None:
        compose = executable_shell(read("docker-compose.release.yml"))
        self.assertNotRegex(compose, r"(?m)^\s*build\s*:")
        self.assertIn('LABEL com.aitrading.managed="true"', read("Dockerfile"))
        self.assertIn('LABEL com.aitrading.managed="true"', read("frontend/Dockerfile"))

    def test_remote_release_only_loads_and_switches_prebuilt_images(self) -> None:
        source = executable_shell(read("deploy/remote_release.sh")).lower()

        for forbidden in ("docker build", "docker compose build", "docker-compose build", "npm ", "next build"):
            self.assertNotIn(forbidden, source)
        self.assertIn("docker load", source)
        self.assertRegex(source, r"(?:docker compose|docker-compose).*up[^\n]*--no-build")

    def test_remote_verifies_uploaded_archive_before_docker_load(self) -> None:
        source = executable_shell(read("deploy/remote_release.sh"))

        checksum = source.find("sha256sum")
        load = source.find("docker load")
        self.assertGreaterEqual(checksum, 0)
        self.assertGreater(load, checksum)
        self.assertIn("ARCHIVE_SHA256", source)
        self.assertRegex(source[checksum:load], r"exit\s+\d+")

    def test_remote_release_preserves_runtime_state(self) -> None:
        source = executable_shell(read("deploy/remote_release.sh"))

        self.assertNotRegex(
            source,
            r"rm\s+-[^\n]*(?:\$DEPLOY_ROOT/\.env|\$DEPLOY_ROOT/work|\$DEPLOY_ROOT/outputs)",
        )
        self.assertNotRegex(source, r"git\s+(?:clean|reset)")
        for name in (".env", "work", "outputs"):
            self.assertIn(name, source)

    def test_failed_health_check_rolls_back_to_previous_release(self) -> None:
        source = executable_shell(read("deploy/remote_release.sh"))

        self.assertRegex(source, r"PREVIOUS|previous|rollback|ROLLBACK")
        health_at = source.find("/api/health")
        self.assertGreaterEqual(health_at, 0)
        self.assertRegex(
            source,
            r"(?s)rollback\(\).*?old_api.*?old_frontend.*?compose_up.*?health_check",
        )

    def test_initial_compose_failure_enters_rollback_and_exits_nonzero(self) -> None:
        source = executable_shell(read("deploy/remote_release.sh"))

        # `set -e` alone is unsafe here: an unguarded compose_up exits the
        # script before rollback. The first release switch must explicitly
        # catch that nonzero status, attempt rollback, and retain a failure exit.
        top_level = source.find("\n}\n\nif ! compose_up")
        self.assertGreaterEqual(
            top_level,
            0,
            "initial compose_up failure must be handled explicitly outside rollback()",
        )
        next_health_check = source.find("\nif ! health_check", top_level)
        self.assertGreater(next_health_check, top_level)
        switch = source[top_level:next_health_check]
        self.assertRegex(switch, r"\brollback\b")
        self.assertRegex(switch, r"\bexit\s+[1-9][0-9]*\b")

    def test_cleanup_retains_current_and_previous_images(self) -> None:
        source = executable_shell(read("deploy/remote_cleanup.sh"))

        self.assertRegex(source, r"CURRENT|current")
        self.assertRegex(source, r"PREVIOUS|previous")
        self.assertNotIn("docker image prune -af", source)
        self.assertRegex(source, r"docker\s+(?:image\s+)?rm")

    def test_cleanup_never_globally_prunes_containers(self) -> None:
        source = executable_shell(read("deploy/remote_cleanup.sh"))

        prune = re.search(r"(?s)docker container prune(.*?)(?:>/dev/null|\n\n)", source)
        if prune:
            self.assertIn("label=com.aitrading.managed=true", prune.group(1))

    def test_managed_image_cleanup_is_scoped_to_aitrading_repositories(self) -> None:
        source = executable_shell(read("deploy/remote_cleanup.sh"))

        self.assertIn("label=com.aitrading.managed=true", source)
        self.assertRegex(source, r"aitrading/(?:trade-review|\*)")

    def test_release_replaces_only_exact_legacy_root_prune_cron(self) -> None:
        source = executable_shell(read("deploy/remote_release.sh"))

        self.assertIn("crontab -l", source)
        self.assertRegex(source, r"(?:awk|grep\s+-v).*docker.*image.*prune.*-af")
        self.assertRegex(source, r"crontab\s+[\"$a-zA-Z_]+'?")
        self.assertNotRegex(source, r"crontab\s+-r")

    def test_compose_v1_and_v2_are_supported(self) -> None:
        remote = executable_shell(read("deploy/remote_release.sh"))
        local = read("deploy/prebuilt_deploy.py")

        combined = remote + "\n" + local
        self.assertIn("docker compose", combined)
        self.assertIn("docker-compose", combined)

    def test_credentials_are_environment_only_and_not_logged(self) -> None:
        source = read("deploy/prebuilt_deploy.py")

        self.assertIn("DEPLOY_PASSWORD", source)
        self.assertRegex(source, r"os\.environ(?:\[|\.get\()")
        self.assertNotRegex(source, r"add_argument\([^\n]*(?:password|secret)")
        self.assertNotRegex(source, r"print\([^\n]*(?:PASSWORD|password|secret)")

    def test_ci_builds_sha_tagged_archive_without_server_secrets(self) -> None:
        source = read(".github/workflows/build-release-images.yml")

        self.assertRegex(source, r"github\.sha|GITHUB_SHA")
        self.assertRegex(source, r"docker (?:compose .*build|build)")
        self.assertIn("docker save", source)
        self.assertRegex(source, r"upload-artifact")
        for forbidden in ("DEPLOY_PASSWORD", "DEPLOY_HOST", "ssh", "scp"):
            self.assertNotIn(forbidden, source)

    def test_frontend_dockerignore_excludes_build_and_test_outputs(self) -> None:
        source = read("frontend/.dockerignore")

        for pattern in (".next", "*.log", "coverage", "test-results", "playwright-report"):
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, source)


if __name__ == "__main__":
    unittest.main()
