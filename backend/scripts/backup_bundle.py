from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC = b"VEDICWAY-BACKUP-V1\n"
PAIR_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{7,63}")
CHUNK_SIZE = 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _key(path: Path) -> bytes:
    try:
        key = base64.urlsafe_b64decode(path.read_bytes().strip())
    except Exception as error:
        raise SystemExit("Backup encryption key is not valid URL-safe base64") from error
    if len(key) != 32:
        raise SystemExit("Backup encryption key must decode to exactly 32 bytes")
    return key


def _verify_sidecar(path: Path) -> None:
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not sidecar.is_file() or sidecar.read_text(encoding="ascii").split()[0] != _sha256(path):
        raise SystemExit(f"Backup checksum failed: {path.name}")


def _encrypt(source: Path, target: Path, key: bytes) -> None:
    nonce = os.urandom(12)
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(MAGIC)
    temporary = target.with_suffix(target.suffix + ".tmp")
    try:
        with source.open("rb") as src, temporary.open("wb") as dst:
            dst.write(MAGIC)
            dst.write(nonce)
            for chunk in iter(lambda: src.read(CHUNK_SIZE), b""):
                dst.write(encryptor.update(chunk))
            dst.write(encryptor.finalize())
            dst.write(encryptor.tag)
        os.replace(temporary, target)
        os.chmod(target, 0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _decrypt(source: Path, target: Path, key: bytes) -> None:
    size = source.stat().st_size
    header_size = len(MAGIC) + 12
    if size <= header_size + 16:
        raise SystemExit("Encrypted backup is truncated")
    with source.open("rb") as src:
        if src.read(len(MAGIC)) != MAGIC:
            raise SystemExit("Unknown encrypted backup format")
        nonce = src.read(12)
        src.seek(-16, os.SEEK_END)
        tag = src.read(16)
        src.seek(header_size)
        remaining = size - header_size - 16
        decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
        decryptor.authenticate_additional_data(MAGIC)
        try:
            with target.open("wb") as dst:
                while remaining:
                    chunk = src.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        raise SystemExit("Encrypted backup is truncated")
                    remaining -= len(chunk)
                    dst.write(decryptor.update(chunk))
                dst.write(decryptor.finalize())
        except InvalidTag as error:
            target.unlink(missing_ok=True)
            raise SystemExit("Encrypted backup authentication failed") from error


def seal(backup_dir: Path, pair_id: str, database: str, key_file: Path) -> Path:
    if not PAIR_RE.fullmatch(pair_id):
        raise SystemExit("Invalid BACKUP_SET_ID")
    postgres = backup_dir / f"{database}-{pair_id}.dump"
    runtime = backup_dir / f"vedicway-runtime-{pair_id}.tar.gz"
    for source in (postgres, runtime):
        if not source.is_file():
            raise SystemExit(f"Paired backup member is missing: {source.name}")
        _verify_sidecar(source)

    with tarfile.open(runtime, "r:gz") as archive:
        manifest_member = archive.extractfile("manifest.json")
        if manifest_member is None or json.load(manifest_member).get("backup_set_id") != pair_id:
            raise SystemExit("Runtime archive belongs to another backup set")

    target = backup_dir / f"vedicway-pair-{pair_id}.vwb"
    with tempfile.TemporaryDirectory(prefix="vedicway-pair-") as temporary:
        stage = Path(temporary)
        shutil.copy2(postgres, stage / "postgres.dump")
        shutil.copy2(runtime, stage / "runtime.tar.gz")
        manifest = {
            "schema": "vedicway.backup-pair.v1",
            "backup_set_id": pair_id,
            "created_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "files": {
                "postgres.dump": _sha256(postgres),
                "runtime.tar.gz": _sha256(runtime),
            },
        }
        (stage / "manifest.json").write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        plain = stage / "pair.tar"
        with tarfile.open(plain, "w") as archive:
            for name in ("manifest.json", "postgres.dump", "runtime.tar.gz"):
                archive.add(stage / name, arcname=name, recursive=False)
        _encrypt(plain, target, _key(key_file))

    checksum = target.with_suffix(target.suffix + ".sha256")
    checksum.write_text(f"{_sha256(target)}  {target.name}\n", encoding="ascii")
    os.chmod(checksum, 0o600)
    for source in (postgres, runtime):
        source.unlink()
        source.with_suffix(source.suffix + ".sha256").unlink()
    print(target.name)
    return target


def _safe_extract(archive: tarfile.TarFile, target: Path) -> None:
    expected = {"manifest.json", "postgres.dump", "runtime.tar.gz"}
    members = archive.getmembers()
    if {member.name for member in members} != expected or any(not member.isfile() for member in members):
        raise SystemExit("Backup pair contains an unexpected member set")
    archive.extractall(target, filter="data")


def unseal(backup_dir: Path, bundle_name: str, key_file: Path) -> Path:
    match = re.fullmatch(r"vedicway-pair-([A-Za-z0-9][A-Za-z0-9._-]{7,63})\.vwb", bundle_name)
    if not match or Path(bundle_name).name != bundle_name:
        raise SystemExit("BACKUP_BUNDLE_FILE must be a VedicWay bundle file name")
    pair_id = match.group(1)
    source = backup_dir / bundle_name
    _verify_sidecar(source)
    target = backup_dir / f".restore-{pair_id}"
    if target.exists():
        raise SystemExit(f"Restore staging already exists: {target.name}")
    with tempfile.TemporaryDirectory(prefix="vedicway-unseal-", dir=backup_dir) as temporary:
        stage = Path(temporary)
        plain = stage / "pair.tar"
        _decrypt(source, plain, _key(key_file))
        with tarfile.open(plain, "r") as archive:
            _safe_extract(archive, stage)
        manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("backup_set_id") != pair_id:
            raise SystemExit("Bundle name and encrypted manifest do not match")
        for name, digest in manifest.get("files", {}).items():
            if name not in {"postgres.dump", "runtime.tar.gz"} or _sha256(stage / name) != digest:
                raise SystemExit(f"Bundle member failed validation: {name}")
            (stage / f"{name}.sha256").write_text(f"{digest}  {name}\n", encoding="ascii")
        plain.unlink()
        os.replace(stage, target)
    print(target.name)
    return target


def cleanup(backup_dir: Path, pair_id: str) -> None:
    if not PAIR_RE.fullmatch(pair_id):
        raise SystemExit("Invalid BACKUP_SET_ID")
    target = backup_dir / f".restore-{pair_id}"
    if target.parent.resolve() != backup_dir.resolve() or not target.name.startswith(".restore-"):
        raise SystemExit("Unsafe restore staging path")
    shutil.rmtree(target, ignore_errors=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Encrypt and validate a paired VedicWay backup")
    parser.add_argument("action", choices=("seal", "unseal", "cleanup"))
    parser.add_argument("--backup-dir", type=Path, default=Path(os.environ.get("BACKUP_DIR", "/backups")))
    parser.add_argument("--pair-id", default=os.environ.get("BACKUP_SET_ID", ""))
    parser.add_argument("--bundle", default=os.environ.get("BACKUP_BUNDLE_FILE", ""))
    parser.add_argument("--database", default=os.environ.get("POSTGRES_DB", "vedicway"))
    parser.add_argument("--key-file", type=Path, default=Path(os.environ.get("BACKUP_KEY_FILE", "/run/secrets/backup_encryption_key")))
    args = parser.parse_args()
    if args.action == "seal":
        seal(args.backup_dir, args.pair_id, args.database, args.key_file)
    elif args.action == "unseal":
        unseal(args.backup_dir, args.bundle, args.key_file)
    else:
        cleanup(args.backup_dir, args.pair_id)


if __name__ == "__main__":
    main()
