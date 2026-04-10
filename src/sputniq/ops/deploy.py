import subprocess
import logging
import docker
from pathlib import Path
from sputniq.ops.builder import ImageBuilder
from sputniq.generator.engine import generate_build_artifacts
import shutil
import tempfile
from pydantic import BaseModel

logger = logging.getLogger(__name__)

def deploy_app(config, extract_dir: Path):
    try:
        logger.info(f"Starting deployment for {config.platform.name}")
        build_dir = extract_dir / ".agentos" / "build"
        generate_build_artifacts(config, build_dir)
        
        builder = ImageBuilder()
        built_tags = []
        
        import uuid
        run_id = str(uuid.uuid4())[:8]

        # Build agents
        for agent in config.agents:
            service_dir = build_dir / "services" / agent.id
            shutil.copytree(extract_dir, service_dir, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".agentos"))
            tag = f"{config.platform.namespace}/{agent.id}:{config.platform.version}-{run_id}"
            builder.build_service(service_dir, tag)
            built_tags.append((agent.id, tag))
            
        # Build tools
        for tool in config.tools:
            service_dir = build_dir / "services" / tool.id
            shutil.copytree(extract_dir, service_dir, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".agentos"))
            tag = f"{config.platform.namespace}/{tool.id}:{config.platform.version}-{run_id}"
            builder.build_service(service_dir, tag)
            built_tags.append((tool.id, tag))
            
        # Run containers directly via python docker sdk
        client = builder.client
        deployed_services = {}
        for service_id, tag in built_tags:
            import socket
            def get_free_port():
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.bind(('', 0))
                p = s.getsockname()[1]
                s.close()
                return str(p)
                
            assigned_port = get_free_port()
            container_name = f"sputniq-{service_id}-{run_id}"
            
            # Remove old container if it exists
            try:
                old_c = client.containers.get(container_name)
                old_c.remove(force=True)
                logger.info(f"Removed old container {container_name}")
            except docker.errors.NotFound:
                pass
                
            runtime = getattr(config.platform, 'runtime', "docker")
            
            logger.info(f"Running new container {container_name} with runtime {runtime}")
            
            if runtime in ("docker", "docker-compose"):
                # Easiest way is host networking so it can reach the local kafka at :9092 natively
                client.containers.run(
                    image=tag,
                    name=container_name,
                    detach=True,
                    network_mode="host",
                    environment={
                        "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
                        "SPUTNIQ_SERVICE_ID": service_id,
                        "PORT": assigned_port
                    }
                )
                deployed_services[service_id] = assigned_port
        
        logger.info("Deployment completed successfully")
        return deployed_services
    except Exception as e:
        logger.error(f"Deployment failed: {str(e)}", exc_info=True)

