"""Tests for AEGIS — software integrity & tamper-evidence.

Tamper-EVIDENT: a changed file is detected and fires the response (drop to free),
but AEGIS never harms the machine. A missing manifest is 'unverified', not a
false alarm. The signed-manifest round-trip uses the project's Ed25519 path.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from pradyos.aegis import IntegrityGuard, hash_tree, load_signed_manifest, sign_manifest
from pradyos.licensing.vault import generate_keypair
from pradyos.sovereign_web import create_app


def _pkg(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "a.py").write_text("x = 1\n", encoding="utf-8")
    (pkg / "b.py").write_text("y = 2\n", encoding="utf-8")
    return pkg


def test_hash_tree_covers_py_files(tmp_path):
    pkg = _pkg(tmp_path)
    h = hash_tree(pkg)
    assert set(h) == {"pkg/a.py", "pkg/b.py"}


def test_clean_tree_verifies_ok(tmp_path):
    pkg = _pkg(tmp_path)
    guard = IntegrityGuard(expected=hash_tree(pkg), root=pkg)
    assert guard.verify()["status"] == "ok"


def test_tamper_is_detected_and_fires_response(tmp_path):
    pkg = _pkg(tmp_path)
    expected = hash_tree(pkg)
    fired: list = []
    guard = IntegrityGuard(expected=expected, root=pkg, on_tamper=lambda r: fired.append(r))
    (pkg / "a.py").write_text("x = 999  # altered\n", encoding="utf-8")
    report = guard.verify()
    assert report["status"] == "tampered"
    assert "pkg/a.py" in report["changed"]
    assert fired  # the tamper-evident response ran


def test_missing_file_is_flagged(tmp_path):
    pkg = _pkg(tmp_path)
    expected = hash_tree(pkg)
    (pkg / "b.py").unlink()
    assert "pkg/b.py" in IntegrityGuard(expected=expected, root=pkg).verify()["missing"]


def test_no_manifest_is_unverified():
    assert IntegrityGuard(expected=None).verify()["status"] == "unverified"


def test_on_tamper_fires_only_once(tmp_path):
    pkg = _pkg(tmp_path)
    expected = hash_tree(pkg)
    fired: list = []
    guard = IntegrityGuard(expected=expected, root=pkg, on_tamper=lambda r: fired.append(1))
    (pkg / "a.py").write_text("z=0\n", encoding="utf-8")
    guard.verify()
    guard.verify()
    assert len(fired) == 1


def test_signed_manifest_round_trip(tmp_path):
    pkg = _pkg(tmp_path)
    priv, pub = generate_keypair()
    token = sign_manifest(hash_tree(pkg), priv)
    assert load_signed_manifest(token, pub) == hash_tree(pkg)


def test_bad_signature_rejected(tmp_path):
    pkg = _pkg(tmp_path)
    priv, _ = generate_keypair()
    _, other_pub = generate_keypair()  # a different key
    token = sign_manifest(hash_tree(pkg), priv)
    assert load_signed_manifest(token, other_pub) is None


def test_http_aegis_unverified_by_default():
    c = TestClient(create_app())
    assert c.get("/api/v1/aegis/verify").json()["status"] == "unverified"
    assert c.get("/api/v1/aegis/status").json()["configured"] is False
