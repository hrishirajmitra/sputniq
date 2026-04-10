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
            
        # Pre-allocate ports for all services
        import socket
        def get_free_port():
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(('', 0))
            p = s.getsockname()[1]
            s.close()
            return str(p)
            
        service_ports = {service_id: get_free_port() for service_id, _ in built_tags}
        
        # Build the injected environment map
        service_env = {
            "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
        }
        for sid, port in service_ports.items():
            env_key = f"{sid.upper().replace('-', '_')}_SERVICE_URL"
            service_env[env_key] = f"http://localhost:{port}/api/tool"
            
        # Run containers directly via python docker sdk
        client = builder.client
        deployed_services = {}
        for service_id, tag in built_tags:
            assigned_port = service_ports[service_id]
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
                container_env = service_env.copy()
                container_env.update({
                    "SPUTNIQ_SERVICE_ID": service_id,
                    "PORT": assigned_port
                })
                
                client.containers.run(
                    image=tag,
                    name=container_name,
                    detach=True,
                    network_mode="host",
                    environment=container_env,
                    labels={"sputniq.run_id": run_id, "sputniq.service_id": service_id}
                )
                deployed_services[service_id] = assigned_port
        
        logger.info(f"Deployment {run_id} completed successfully")
        return {"run_id": run_id, "services": deployed_services}
    except Exception as e:
        logger.error(f"Deployment failed: {str(e)}", exc_info=True)


def teardown_app(run_id: str) -> int:
    """Tear down all containers and networks associated with a specific run_id."""
    try:
        client = docker.from_env()
        containers = client.containers.list(all=True, filters={"label": f"sputniq.run_id={run_id}"})
        removed_count = 0
        for c in containers:
            logger.info(f"Removing container {c.name} for run_id {run_id}")
            c.remove(force=True)
            removed_count += 1
        return removed_count
    except Exception as e:
        logger.error(f"Teardown failed: {str(e)}", exc_info=True)
        raise

