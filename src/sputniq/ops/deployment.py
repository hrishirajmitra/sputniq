import json
import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

class DeploymentEngine:
    """Instantiates deployment configurations based on the specified target runtime."""
    
    def __init__(self, templates_dir: Path):
        self.templates_dir = templates_dir
        self.env = Environment(loader=FileSystemLoader(str(self.templates_dir)), autoescape=True)
        
    def render_manifest(self, platform_config: dict, manifest_file: Path, output_dir: Path):
        """Loads `build.manifest.json` artifacts onto the deployment YAMLs."""
        manifest_data = json.loads(manifest_file.read_text())
        runtime = platform_config.get("runtime", "docker-compose")
        
        target_template = f"deployment-{runtime}.yaml.j2"
        if not (self.templates_dir / target_template).exists():
            raise FileNotFoundError(f"Missing {target_template} template configured for runtime {runtime}")
            
        template = self.env.get_template(target_template)
        output_str = template.render(
            platform=platform_config,
            services=manifest_data["services"],
            scans=manifest_data.get("security_scans", {})
        )
        
        output_file = output_dir / f"deployment-{runtime}.yaml"
        output_file.write_text(output_str)
        return output_file
