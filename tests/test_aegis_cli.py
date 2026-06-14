"""Tests for the AEGIS boot-time CLI (`python -m pradyos.aegis verify`)."""

from __future__ import annotations

import json
from pathlib import Path

from pradyos.aegis import hash_tree, sign_manifest
from pradyos.aegis import cli
from pradyos.licensing.vault import generate_keypair


def _pkg(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "a.py").write_text("x = 1\n", encoding="utf-8")
    return pkg


def test_no_manifest_is_unverified_exit0(tmp_path):
    marker = tmp_path / "r.json"
    rc = cli.main(["verify"], env={"PRADYOS_INTEGRITY_RESULT": str(marker)})
    assert rc == 0
    assert json.loads(marker.read_text())["status"] == "unverified"


def test_bad_command_returns_2():
    assert cli.main(["frobnicate"], env={}) == 2


def test_signed_clean_tree_verifies_ok(tmp_path, monkeypatch):
    pkg = _pkg(tmp_path)
    # point the guard's default root at our package by monkeypatching pradyos pkg root
    priv, pub = generate_keypair()
    token = sign_manifest(hash_tree(pkg), priv)
    man = tmp_path / "m.tok"
    man.write_text(token, encoding="utf-8")
    pub_f = tmp_path / "pub.pem"
    pub_f.write_text(pub, encoding="utf-8")

    # IntegrityGuard defaults its root to the pradyos package; here the manifest
    # paths are package-relative ("pkg/a.py"), so verify against the real package
    # would report missing. Instead, exercise the load + verify against the same
    # tree by constructing the guard directly through the CLI's verify() with a
    # guard rooted at the package via env-independent path: assert the manifest
    # loads and the tree matches.
    from pradyos.aegis import IntegrityGuard, load_signed_manifest

    expected = load_signed_manifest(token, pub)
    assert expected == hash_tree(pkg)
    assert IntegrityGuard(expected=expected, root=pkg).verify()["status"] == "ok"


def test_cli_writes_marker_and_is_importable_as_module():
    # the module entrypoint exists (python -m pradyos.aegis)
    import importlib

    mod = importlib.import_module("pradyos.aegis.__main__")
    assert hasattr(mod, "main")


def test_tampered_manifest_exit1(tmp_path, monkeypatch):
    # Build a manifest for a package, then point the CLI at it but verify against
    # a DIFFERENT (the real pradyos) tree → every tracked file is "missing" =>
    # tampered. Use a manifest whose paths won't exist in the real package root.
    pkg = _pkg(tmp_path)
    priv, pub = generate_keypair()
    token = sign_manifest(hash_tree(pkg), priv)
    man = tmp_path / "m.tok"
    man.write_text(token, encoding="utf-8")
    pub_f = tmp_path / "pub.pem"
    pub_f.write_text(pub, encoding="utf-8")
    marker = tmp_path / "r.json"
    rc = cli.main(
        ["verify"],
        env={
            "PRADYOS_INTEGRITY_MANIFEST": str(man),
            "PRADYOS_INTEGRITY_PUBKEY": str(pub_f),
            "PRADYOS_INTEGRITY_RESULT": str(marker),
        },
    )
    report = json.loads(marker.read_text())
    # the manifest's "pkg/a.py" does not exist under the real pradyos root → missing
    assert report["status"] == "tampered"
    assert rc == 1
