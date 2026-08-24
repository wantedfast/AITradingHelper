"""Build or acquire immutable images locally, then release them over SSH.

The production host never receives a Docker build context and never runs npm,
Next.js, pip, or ``docker build``. It only receives a compressed ``docker save``
archive plus the release manifests, loads the images, and switches containers.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.parse

import paramiko


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REMOTE_ROOT = "/opt/trade-review-agent"
TAG_PATTERN = re.compile(r"^[0-9a-f]{7,40}$")
ARCHIVE_TAG_PATTERN = re.compile(r"aitrading-([0-9a-f]{7,40})\.tar\.gz$")
LOCAL_BUILD_DESCRIPTION = "docker compose -f docker-compose.prod.yml build"
LOCAL_SAVE_DESCRIPTION = "docker save"


def command_output(args: list[str]) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def release_tag(explicit: str | None, archive_name: str | None = None) -> str:
    tag = explicit
    if not tag and archive_name:
        match = ARCHIVE_TAG_PATTERN.search(archive_name)
        tag = match.group(1) if match else None
    if not tag:
        tag = command_output(["git", "rev-parse", "HEAD"])
    if not TAG_PATTERN.fullmatch(tag):
        raise ValueError("RELEASE_TAG must be a 7-40 character lowercase git SHA")
    return tag


def local_release_tag(explicit: str | None) -> str:
    """Bind a local build to the exact source commit being built.

    Prebuilt archives may legitimately use an abbreviated validated SHA in
    their filename, but source builds must never let an operator attach an
    arbitrary hex label to the current checkout.
    """

    head = command_output(["git", "rev-parse", "HEAD"])
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise RuntimeError("local git HEAD is not a canonical full 40-character SHA")
    if explicit and explicit != head:
        raise ValueError("local RELEASE_TAG must exactly match git rev-parse HEAD")
    return head


def compose_command() -> list[str]:
    try:
        subprocess.run(
            ["docker", "compose", "version"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return ["docker", "compose"]
    except (FileNotFoundError, subprocess.CalledProcessError):
        if shutil.which("docker-compose"):
            return ["docker-compose"]
    raise RuntimeError("local Docker Compose v2 or docker-compose v1 is required to build images")


def build_archive(tag: str, output_dir: Path) -> Path:
    if tag != local_release_tag(tag):
        raise RuntimeError("local release provenance check failed")
    if command_output(["git", "status", "--porcelain"]):
        raise RuntimeError("working tree is dirty; commit changes before creating an immutable release")
    compose = compose_command()
    env = os.environ.copy()
    env.update(
        {
            "RELEASE_TAG": tag,
            "API_IMAGE": f"aitrading/trade-review-api:{tag}",
            "FRONTEND_IMAGE": f"aitrading/trade-review-frontend:{tag}",
        }
    )
    print(f"Building immutable images locally ({LOCAL_BUILD_DESCRIPTION})")
    subprocess.run(
        compose
        + ["-f", "docker-compose.prod.yml", "build"],
        cwd=ROOT,
        env=env,
        check=True,
    )
    images = [
        f"aitrading/trade-review-api:{tag}",
        f"aitrading/trade-review-frontend:{tag}",
    ]
    for image in images:
        subprocess.run(["docker", "image", "inspect", image], check=True, stdout=subprocess.DEVNULL)

    output_dir.mkdir(parents=True, exist_ok=True)
    tar_path = output_dir / f"aitrading-{tag}.tar"
    archive_path = tar_path.with_suffix(".tar.gz")
    print(f"Packaging images locally ({LOCAL_SAVE_DESCRIPTION})")
    subprocess.run(["docker", "save", "--output", str(tar_path), *images], check=True)
    with tar_path.open("rb") as source, gzip.open(archive_path, "wb", compresslevel=6) as target:
        shutil.copyfileobj(source, target, length=8 * 1024 * 1024)
    tar_path.unlink()
    return archive_path


def download_archive(url: str, output_dir: Path) -> Path:
    name = Path(urllib.parse.urlparse(url).path).name or "release.tar.gz"
    destination = output_dir / name
    print(f"Downloading prebuilt release archive to {destination}")
    request = urllib.request.Request(url, headers={"User-Agent": "AITradingHelper-deployer/1"})
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as target:
        shutil.copyfileobj(response, target, length=8 * 1024 * 1024)
    return destination


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def password_from_environment() -> str | None:
    password = os.environ.get("DEPLOY_PASSWORD")
    if password:
        return password
    ssh_file = os.environ.get("DEPLOY_SSH_FILE")
    if not ssh_file:
        return None
    lines = Path(ssh_file).expanduser().read_text(encoding="utf-8-sig").splitlines()
    if len(lines) < 2:
        raise RuntimeError("DEPLOY_SSH_FILE must contain username on line 1 and password on line 2")
    os.environ.setdefault("DEPLOY_USER", lines[0].strip())
    return lines[1].strip()


def connect() -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    password = password_from_environment()
    client.connect(
        os.environ.get("DEPLOY_HOST", "123.56.166.126"),
        port=int(os.environ.get("DEPLOY_PORT", "22")),
        username=os.environ.get("DEPLOY_USER", "root"),
        password=password,
        timeout=30,
        look_for_keys=password is None,
        allow_agent=password is None,
    )
    return client


def run_remote(client: paramiko.SSHClient, command: str, *, timeout: int | None = None) -> None:
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout, get_pty=True)
    stdin.close()
    while not stdout.channel.exit_status_ready():
        if stdout.channel.recv_ready():
            sys.stdout.write(stdout.channel.recv(65536).decode("utf-8", errors="replace"))
            sys.stdout.flush()
        if stderr.channel.recv_stderr_ready():
            sys.stderr.write(stderr.channel.recv_stderr(65536).decode("utf-8", errors="replace"))
            sys.stderr.flush()
        time.sleep(0.1)
    remaining = stdout.read().decode("utf-8", errors="replace")
    errors = stderr.read().decode("utf-8", errors="replace")
    if remaining:
        sys.stdout.write(remaining)
    if errors:
        sys.stderr.write(errors)
    code = stdout.channel.recv_exit_status()
    if code:
        raise RuntimeError(f"remote release failed with exit code {code}")


def sftp_mkdirs(sftp: paramiko.SFTPClient, path: str) -> None:
    current = ""
    for part in path.strip("/").split("/"):
        current += "/" + part
        try:
            sftp.stat(current)
        except FileNotFoundError:
            sftp.mkdir(current)


def upload(sftp: paramiko.SFTPClient, local: Path, remote: str) -> None:
    partial = remote + ".partial"
    print(f"Uploading {local.name}")
    sftp.put(str(local), partial)
    sftp.rename(partial, remote)


def deploy(archive: Path, tag: str, archive_sha256: str) -> None:
    remote_root = os.environ.get("DEPLOY_REMOTE_DIR", DEFAULT_REMOTE_ROOT).rstrip("/")
    release_dir = f"{remote_root}/.deploy/releases/{tag}"
    bin_dir = f"{remote_root}/.deploy/bin"
    remote_archive = f"{release_dir}/{archive.name}"
    client = connect()
    try:
        # Check the production host before transferring a potentially large
        # archive. This command contains paths and sizes only, never credentials.
        required_kb = archive.stat().st_size // 1024 * 3 + 524288
        preflight = (
            f"mkdir -p {shlex.quote(release_dir)} {shlex.quote(bin_dir)} && "
            f"test -s {shlex.quote(remote_root + '/.env')} && "
            "command -v docker >/dev/null && "
            "(docker compose version >/dev/null 2>&1 || command -v docker-compose >/dev/null) && "
            f"test $(df -Pk {shlex.quote(remote_root)} | awk 'NR==2 {{print $4}}') -ge {required_kb}"
        )
        run_remote(client, preflight, timeout=30)
        sftp = client.open_sftp()
        sftp_mkdirs(sftp, release_dir)
        sftp_mkdirs(sftp, bin_dir)
        upload(sftp, archive, remote_archive)
        upload(sftp, ROOT / "docker-compose.release.yml", f"{release_dir}/docker-compose.release.yml")
        upload(sftp, ROOT / "deploy" / "remote_release.sh", f"{bin_dir}/remote_release.sh")
        upload(sftp, ROOT / "deploy" / "remote_cleanup.sh", f"{bin_dir}/remote_cleanup.sh")
        sftp.close()
        quoted_root = shlex.quote(remote_root)
        command = (
            f"chmod 700 {shlex.quote(bin_dir)}/remote_release.sh {shlex.quote(bin_dir)}/remote_cleanup.sh && "
            f"DEPLOY_ROOT={quoted_root} RELEASE_TAG={shlex.quote(tag)} "
            f"ARCHIVE_PATH={shlex.quote(remote_archive)} "
            f"ARCHIVE_SHA256={shlex.quote(archive_sha256)} {shlex.quote(bin_dir)}/remote_release.sh"
        )
        run_remote(client, command, timeout=None)
    finally:
        client.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--archive", type=Path, help="existing docker-save .tar.gz archive")
    source.add_argument("--release-url", help="public URL of a prebuilt docker-save .tar.gz archive")
    parser.add_argument("--tag", help="immutable git SHA (inferred from a standard archive name or local git)")
    parser.add_argument("--sha256", dest="expected_sha256", help="optional archive SHA-256 verification")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_name = str(args.archive or args.release_url or "")
    explicit_tag = args.tag or os.environ.get("RELEASE_TAG")
    if args.archive or args.release_url:
        tag = release_tag(explicit_tag, source_name)
    else:
        tag = local_release_tag(explicit_tag)
    with tempfile.TemporaryDirectory(prefix="aitrading-release-") as temp:
        temp_dir = Path(temp)
        if args.archive:
            archive = args.archive.resolve()
            if not archive.is_file():
                raise FileNotFoundError(f"release archive does not exist: {archive}")
        elif args.release_url:
            archive = download_archive(args.release_url, temp_dir)
        else:
            archive = build_archive(tag, temp_dir)
        if args.expected_sha256 and sha256(archive).lower() != args.expected_sha256.lower():
            raise RuntimeError("release archive SHA-256 mismatch")
        archive_digest = sha256(archive)
        print(f"Release tag: {tag}; archive SHA-256: {archive_digest}")
        deploy(archive, tag, archive_digest)


if __name__ == "__main__":
    main()
