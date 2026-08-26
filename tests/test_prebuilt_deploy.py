import re
import io
import hashlib
import os
import shutil
import subprocess
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
    def test_same_healthy_release_is_a_noop_instead_of_recreating_containers(self) -> None:
        bash = shutil.which("bash")
        if bash is None:
            for candidate in (
                Path(r"C:\Program Files\Git\bin\bash.exe"),
                Path(r"C:\Program Files\Git\usr\bin\bash.exe"),
            ):
                if candidate.exists():
                    bash = str(candidate)
                    break
        if bash is None:
            self.skipTest("bash is required for the release behavior test")

        tag = "a" * 40
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            def bash_path(path: Path) -> str:
                resolved = path.resolve()
                return f"/{resolved.drive[0].lower()}/{resolved.as_posix()[3:]}"

            release_dir = root / ".deploy" / "releases" / tag
            fake_bin = root / "fake-bin"
            release_dir.mkdir(parents=True)
            fake_bin.mkdir()
            (root / ".env").write_text("SAFE_TEST_VALUE=1\n", encoding="utf-8")
            (root / ".deploy" / "current-release").write_bytes((tag + "\n").encode("ascii"))
            (release_dir / "docker-compose.release.yml").write_text("services: {}\n", encoding="utf-8")
            archive = release_dir / f"aitrading-{tag}.tar.gz"
            archive.write_bytes(b"verified release archive")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            docker_log = root / "docker.log"

            (fake_bin / "docker").write_text(
                "#!/usr/bin/env bash\n"
                "echo \"$*\" >> \"$DOCKER_LOG\"\n"
                "case \"$*\" in\n"
                "  'compose version') exit 0 ;;\n"
                "  image\\ inspect*) exit 0 ;;\n"
                "  inspect*State.Running*) echo true; exit 0 ;;\n"
                "  inspect*State.Health.Status*) echo healthy; exit 0 ;;\n"
                "esac\n"
                "exit 99\n",
                encoding="utf-8",
                newline="\n",
            )
            (fake_bin / "curl").write_text(
                "#!/usr/bin/env bash\nexit 0\n", encoding="utf-8", newline="\n"
            )
            shutil.copyfile(fake_bin / "curl", fake_bin / "curl.exe")
            (fake_bin / "flock").write_text(
                "#!/usr/bin/env bash\nexit 0\n", encoding="utf-8", newline="\n"
            )
            for executable in (
                fake_bin / "docker",
                fake_bin / "curl",
                fake_bin / "curl.exe",
                fake_bin / "flock",
            ):
                executable.chmod(0o755)

            env = os.environ.copy()
            env.update(
                {
                    "PATH": bash_path(fake_bin) + ":/usr/bin:/bin",
                    "DOCKER_LOG": bash_path(docker_log),
                    "DEPLOY_ROOT": bash_path(root),
                    "RELEASE_TAG": tag,
                    "ARCHIVE_PATH": bash_path(archive),
                    "ARCHIVE_SHA256": digest,
                    "CURL_BIN": bash_path(fake_bin / "curl"),
                }
            )
            completed = subprocess.run(
                [bash, str(ROOT / "deploy" / "remote_release.sh")],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
            )

            observed_calls = docker_log.read_text(encoding="utf-8") if docker_log.exists() else ""
            self.assertEqual(
                completed.returncode,
                0,
                completed.stdout + completed.stderr + "\ndocker calls:\n" + observed_calls,
            )
            self.assertIn("already healthy", completed.stdout.lower())
            docker_calls = observed_calls
            self.assertNotIn(" up ", f" {docker_calls} ")
            self.assertNotIn("image tag", docker_calls)
            self.assertNotIn("load", docker_calls)

    def test_remote_release_runs_in_a_systemd_unit_that_survives_ssh_disconnect(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.sftp = mock.Mock()

            def open_sftp(self):
                return self.sftp

            def close(self) -> None:
                pass

        tag = "b" * 40
        digest = "c" * 64
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / f"aitrading-{tag}.tar.gz"
            archive.write_bytes(b"release")
            client = FakeClient()
            commands: list[str] = []

            def record_remote(_client, command: str, *, timeout=None) -> None:
                commands.append(command)

            with mock.patch.object(prebuilt_deploy, "connect", return_value=client), mock.patch.object(
                prebuilt_deploy, "run_remote", side_effect=record_remote
            ), mock.patch.object(prebuilt_deploy, "sftp_mkdirs"), mock.patch.object(
                prebuilt_deploy, "remote_archive_matches", return_value=True
            ), mock.patch.object(prebuilt_deploy, "upload"), mock.patch.object(
                prebuilt_deploy, "upload_shell_script"
            ):
                prebuilt_deploy.deploy(archive, tag, digest)

        release_command = commands[-1]
        self.assertIn("systemd-run", release_command)
        self.assertIn("--wait", release_command)
        self.assertIn("--collect", release_command)
        self.assertIn("--setenv", release_command)

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

    def test_remote_shell_scripts_have_lf_shebang_and_no_crlf_bytes(self) -> None:
        for relative_path in ("deploy/remote_release.sh", "deploy/remote_cleanup.sh"):
            with self.subTest(path=relative_path):
                source = (ROOT / relative_path).read_bytes()
                self.assertTrue(source.startswith(b"#!/usr/bin/env bash\n"))
                self.assertNotIn(b"\r\n", source)

    def test_gitattributes_enforces_lf_for_shell_scripts(self) -> None:
        source = read(".gitattributes")
        self.assertRegex(source, r"(?m)^\*\.sh\s+text(?:\s+[^\n]*)?\s+eol=lf\s*$")

    def test_uploader_never_sends_crlf_shell_script(self) -> None:
        class RecordingSftp:
            def __init__(self) -> None:
                self.uploaded: bytes | None = None
                self.renamed = False

            def file(self, _remote: str, _mode: str):
                owner = self

                class Buffer(io.BytesIO):
                    def __exit__(self, *args):
                        owner.uploaded = self.getvalue()
                        self.close()

                return Buffer()

            def posix_rename(self, _partial: str, _remote: str) -> None:
                self.renamed = True

        with tempfile.TemporaryDirectory() as temp_dir:
            script = Path(temp_dir) / "unsafe.sh"
            script.write_bytes(b"#!/usr/bin/env bash\r\necho unsafe\r\n")
            sftp = RecordingSftp()
            try:
                prebuilt_deploy.upload_shell_script(sftp, script, "/tmp/unsafe.sh")
            except (RuntimeError, ValueError):
                self.assertIsNone(sftp.uploaded)
                self.assertFalse(sftp.renamed)
            else:
                self.assertIsNotNone(sftp.uploaded)
                self.assertNotIn(b"\r\n", sftp.uploaded)
                self.assertTrue(sftp.uploaded.startswith(b"#!/usr/bin/env bash\n"))

    def test_matching_remote_archive_is_not_uploaded_again(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.sftp = mock.Mock()

            def open_sftp(self):
                return self.sftp

            def close(self) -> None:
                pass

        tag = "d" * 40
        digest = "e" * 64
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / f"aitrading-{tag}.tar.gz"
            archive.write_bytes(b"already uploaded")
            client = FakeClient()
            with mock.patch.object(prebuilt_deploy, "connect", return_value=client), mock.patch.object(
                prebuilt_deploy, "run_remote"
            ), mock.patch.object(
                prebuilt_deploy, "sftp_mkdirs"
            ), mock.patch.object(
                prebuilt_deploy, "remote_archive_matches", return_value=True
            ) as matches, mock.patch.object(
                prebuilt_deploy, "upload"
            ) as upload, mock.patch.object(
                prebuilt_deploy, "upload_shell_script"
            ):
                prebuilt_deploy.deploy(archive, tag, digest)

            matches.assert_called_once_with(
                client,
                f"/opt/trade-review-agent/.deploy/releases/{tag}/{archive.name}",
                archive.stat().st_size,
                digest,
            )
            self.assertEqual(upload.call_count, 1, "only the small compose manifest is uploaded")
            self.assertNotEqual(upload.call_args.args[1], archive)

    def test_small_release_files_atomically_replace_existing_remote_files(self) -> None:
        sftp = mock.Mock()
        prebuilt_deploy.promote_upload(sftp, "/tmp/file.partial", "/tmp/file")
        sftp.posix_rename.assert_called_once_with("/tmp/file.partial", "/tmp/file")
        sftp.rename.assert_not_called()

        fallback = mock.Mock()
        fallback.posix_rename.side_effect = OSError("extension unavailable")
        prebuilt_deploy.promote_upload(fallback, "/tmp/file.partial", "/tmp/file")
        fallback.remove.assert_called_once_with("/tmp/file")
        fallback.rename.assert_called_once_with("/tmp/file.partial", "/tmp/file")


if __name__ == "__main__":
    unittest.main()
