import logging
from pathlib import Path

import docker
from docker.errors import BuildError, APIError

logger = logging.getLogger(__name__)

class ImageBuilder:
    """Builds Docker images for the generated services."""
    def __init__(self, base_url: str = None):
        if base_url:
            self.client = docker.DockerClient(base_url=base_url)
        else:
            self.client = docker.from_env()

    def build_service(self, service_dir: Path, tag: str) -> None:
        """Build a docker image from a service directory containing a Dockerfile."""
        if not (service_dir / "Dockerfile").exists():
            raise FileNotFoundError(f"No Dockerfile found in {service_dir}")
            
        try:
            import sputniq
            sputniq_path = Path(sputniq.__file__).parent
            import shutil
            dest_sputniq = service_dir / "sputniq"
            if not dest_sputniq.exists():
                shutil.copytree(sputniq_path, dest_sputniq, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        except Exception as e:
            logger.warning(f"Could not copy sputniq core sdk into service context: {e}")

        logger.info(f"Building Docker image {tag} from {service_dir}")
        try:
            image, build_logs = self.client.images.build(
                path=str(service_dir),
                tag=tag,
                rm=True, nocache=True
            )
            logger.info(f"Successfully built image {tag} (ID: {image.short_id})")
        except BuildError as e:
            logger.error(f"Image build failed for {tag}")
            for line in e.build_log:
                if 'stream' in line:
                    logger.error(line['stream'].strip())
            raise
        except APIError as e:
            logger.error(f"Docker API error during build of {tag}: {e}")
            raise
