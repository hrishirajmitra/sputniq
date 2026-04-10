import json
import pytest
from pathlib import Path

from sputniq.ops.security import DependencyScanner, ArtifactManifest

@pytest.fixture
def fake_vuln_dir(tmp_path):
    d = tmp_path / "vuln_service"
    d.mkdir()
    d.joinpath("requirements.txt").write_text("urllib3==1.25\nrequests==2.20")
    return d

@pytest.fixture
def fake_safe_dir(tmp_path):
    d = tmp_path / "safe_service"
    d.mkdir()
    d.joinpath("requirements.txt").write_text("numpy!=old")
    return d

def test_scanner_no_requirements(tmp_path):
    scanner = DependencyScanner()
    res = scanner.scan_bundle(tmp_path)
    assert res == {"status": "ok", "vulnerabilities": 0, "msg": "No Python requirements to scan."}

def test_scanner_safe_bundle(fake_safe_dir):
    scanner = DependencyScanner()
    res = scanner.scan_bundle(fake_safe_dir)
    assert res["status"] == "ok"
    assert res["vulnerabilities"] == 0

def test_scanner_vulnerable_bundle(fake_vuln_dir):
    scanner = DependencyScanner()
    res = scanner.scan_bundle(fake_vuln_dir)
    assert res["status"] == "failed"
    assert res["vulnerabilities"] == 1
    assert "CVE-2020-26137" in res["details"][0]["cve"]

def test_artifact_manifest_generation(tmp_path):
    manifest = ArtifactManifest(tmp_path)
    
    manifest.add_service("agent-a", "agent/tag:v1.0")
    manifest.attach_scan("agent-a", {"status": "ok", "vulnerabilities": 0})
    manifest.save()
    
    res = json.loads(tmp_path.joinpath("build.manifest.json").read_text())
    assert res["version"] == "1.0"
    assert len(res["services"]) == 1
    assert res["services"][0]["id"] == "agent-a"
    assert res["services"][0]["image"] == "agent/tag:v1.0"
    
    assert res["security_scans"]["agent-a"]["status"] == "ok"
