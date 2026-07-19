from __future__ import annotations

import importlib.util
import json
import tarfile
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "backup_bundle.py"
SPEC = importlib.util.spec_from_file_location("vedicway_backup_bundle", SCRIPT)
assert SPEC and SPEC.loader
backup_bundle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backup_bundle)


def _source_pair(root: Path, pair_id: str) -> tuple[Path, Path]:
    postgres = root / f"vedicway-{pair_id}.dump"
    postgres.write_bytes(b"postgres-dump")
    runtime = root / f"vedicway-runtime-{pair_id}.tar.gz"
    manifest = root / "runtime-manifest.json"
    manifest.write_text(json.dumps({"backup_set_id": pair_id}), encoding="utf-8")
    with tarfile.open(runtime, "w:gz") as archive:
        archive.add(manifest, arcname="manifest.json")
    for path in (postgres, runtime):
        path.with_suffix(path.suffix + ".sha256").write_text(
            f"{backup_bundle._sha256(path)}  {path.name}\n", encoding="ascii"
        )
    return postgres, runtime


def test_pair_is_encrypted_authenticated_and_unsealed_to_staging(tmp_path) -> None:
    pair_id = "20260719T010000Z-deadbeef"
    key_file = tmp_path / "backup.key"
    key_file.write_bytes(Fernet.generate_key())
    postgres, runtime = _source_pair(tmp_path, pair_id)

    bundle = backup_bundle.seal(tmp_path, pair_id, "vedicway", key_file)

    assert bundle.read_bytes().startswith(backup_bundle.MAGIC)
    assert b"postgres-dump" not in bundle.read_bytes()
    assert not postgres.exists()
    assert not runtime.exists()
    stage = backup_bundle.unseal(tmp_path, bundle.name, key_file)
    assert (stage / "postgres.dump").read_bytes() == b"postgres-dump"
    assert (stage / "runtime.tar.gz.sha256").is_file()


def test_tampered_pair_fails_authenticated_decryption(tmp_path) -> None:
    pair_id = "20260719T010000Z-feedface"
    key_file = tmp_path / "backup.key"
    key_file.write_bytes(Fernet.generate_key())
    _source_pair(tmp_path, pair_id)
    bundle = backup_bundle.seal(tmp_path, pair_id, "vedicway", key_file)
    damaged = bytearray(bundle.read_bytes())
    damaged[len(backup_bundle.MAGIC) + 20] ^= 1
    bundle.write_bytes(damaged)
    bundle.with_suffix(bundle.suffix + ".sha256").write_text(
        f"{backup_bundle._sha256(bundle)}  {bundle.name}\n", encoding="ascii"
    )

    with pytest.raises(SystemExit, match="authentication failed"):
        backup_bundle.unseal(tmp_path, bundle.name, key_file)
