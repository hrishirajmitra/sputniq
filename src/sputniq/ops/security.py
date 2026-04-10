import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class DependencyScanner:
    """Invokes system-level Trivy/Snyk style tool scans to validate requirements.txt and Dockerfile."""
    def scan_bundle(self, service_dir: Path) -> dict:
        """Mock behavior: reads directory requirements and simulates report."""
        if not (service_dir / "requirements.txt").exists():
            return {"status": "ok", "vulnerabilities": 0, "msg": "No Python requirements to scan."}

        # Simulating finding a vulnerability if old insecure packages were given
        content = (service_dir / "requirements.txt").read_text()
        vulnerabilities = []
        if "urllib3==1.25" in content:
             vulnerabilities.append({"package": "urllib3", "cve": "CVE-2020-26137", "severity": "HIGH"})
             
        if vulnerabilities:
             return {"status": "failed", "vulnerabilities": len(vulnerabilities), "details": vulnerabilities}
        
        return {"status": "ok", "vulnerabilities": 0}

class ArtifactManifest:
    """Generates the `build.manifest.json` for deployment orchestration tracking."""
    def __init__(self, target_dir: Path):
        self.target_dir = target_dir
        self.services = []
        self.scans = {}

    def add_service(self, service_id: str, image_tag: str):
        self.services.append({"id": service_id, "image": image_tag})

    def attach_scan(self, service_id: str, scan_result: dict):
        self.scans[service_id] = scan_result
        
    def save(self):
        manifest_path = self.target_dir / "build.manifest.json"
        
        payload = {
            "version": "1.0",
            "services": self.services,
            "security_scans": self.scans
        }
        
        manifest_path.write_text(json.dumps(payload, indent=2))
        logger.info(f"Manifest written to {manifest_path}")

