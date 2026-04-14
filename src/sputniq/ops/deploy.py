from sputniq.ops.inventory import get_available_node
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

def delete_app(app_id: str, nodes: list) -> bool:
    try:
        import docker
        # Group by IP to use correct remote client
        for node in nodes:
            ip = node.get("ip")
            if not ip: continue
            
            try:
                # In real scenario we use DOCKER_HOST via SSH context
                from sputniq.ops.inventory import get_inventory
                nodes = get_inventory()
                node_match = [n for n in nodes if n.ip_address == ip]
                if not node_match: continue
                username = node_match[0].username
                remote_docker_host = f"ssh://{username}@{ip}"
                remote_client = docker.DockerClient(base_url=remote_docker_host, use_ssh_client=True)
            except Exception as e:
                logger.error(f"Could not connect to remote {ip} for deletion: {e}")
                continue

            container_name = node.get("container")
            try:
                c = remote_client.containers.get(container_name)
                c.remove(force=True)
                logger.info(f"Deleted container {container_name} on {ip}")
            except docker.errors.NotFound:
                pass
            except Exception as e:
                logger.warning(f"Could not delete {container_name}: {e}")
                
        return True
    except Exception as e:
        logger.error(f"Failed to delete app {app_id}: {str(e)}", exc_info=True)
        return False

def deploy_app(config, extract_dir: Path):
    try:
        logger.info(f"Starting deployment for {config.platform.name}")
        build_dir = extract_dir / ".agentos" / "build"
        generate_build_artifacts(config, build_dir)
        
        builder = ImageBuilder()
        built_tags = []
        
        # Build agents
        for agent in config.agents:
            service_dir = build_dir / "services" / agent.id
            if (service_dir / "requirements.txt").exists() and (extract_dir / "requirements.txt").exists():
                orig_reqs = (service_dir / "requirements.txt").read_text()
                user_reqs = (extract_dir / "requirements.txt").read_text()
                shutil.copytree(extract_dir, service_dir, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".agentos"))
                (service_dir / "requirements.txt").write_text(orig_reqs + "\n" + user_reqs)
            else:
                shutil.copytree(extract_dir, service_dir, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".agentos"))
                
            tag = f"{config.platform.namespace}/{agent.id}:{config.platform.version}"
            builder.build_service(service_dir, tag)
            built_tags.append((agent.id, tag))
            
        # Build tools
        for tool in getattr(config, 'tools', []):
            service_dir = build_dir / "services" / tool.id
            if (service_dir / "requirements.txt").exists() and (extract_dir / "requirements.txt").exists():
                orig_reqs = (service_dir / "requirements.txt").read_text()
                user_reqs = (extract_dir / "requirements.txt").read_text()
                shutil.copytree(extract_dir, service_dir, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".agentos"))
                (service_dir / "requirements.txt").write_text(orig_reqs + "\n" + user_reqs)
            else:
                shutil.copytree(extract_dir, service_dir, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".agentos"))
            tag = f"{config.platform.namespace}/{tool.id}:{config.platform.version}"
            builder.build_service(service_dir, tag)
            built_tags.append((tool.id, tag))
            
        # Build workflows (orchestrators)
        for workflow in getattr(config, 'workflows', []):
            service_dir = build_dir / "services" / workflow.id
            if (service_dir / "requirements.txt").exists() and (extract_dir / "requirements.txt").exists():
                orig_reqs = (service_dir / "requirements.txt").read_text()
                user_reqs = (extract_dir / "requirements.txt").read_text()
                shutil.copytree(extract_dir, service_dir, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".agentos"))
                (service_dir / "requirements.txt").write_text(orig_reqs + "\n" + user_reqs)
            else:
                shutil.copytree(extract_dir, service_dir, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".agentos"))
            tag = f"{config.platform.namespace}/{workflow.id}:{config.platform.version}"
            builder.build_service(service_dir, tag)
            built_tags.append((workflow.id, tag))
            
        # Select target Linux VM iteratively or via load-balancer
        result_nodes = []
        for idx, (service_id, tag) in enumerate(built_tags):
            selected_node = get_available_node()
            logger.info(f"Deploying to target VM: {selected_node.hostname} ({selected_node.ip_address})")
            
            # Connecting remote docker socket
            remote_docker_host = f"ssh://{selected_node.username}@{selected_node.ip_address}"
            
            try:
                remote_client = docker.DockerClient(base_url=remote_docker_host, use_ssh_client=True)
                logger.info("Connected to remote docker daemon.")
                
                # Image synchronization: save locally, load remotely
                logger.info(f"Syncing image {tag} to remote node via SSH CLI...")
                # Use subprocess for much faster transfer than paramiko
                import subprocess
                sp1 = subprocess.Popen(["docker", "save", tag], stdout=subprocess.PIPE)
                sp2 = subprocess.Popen([
                    "ssh", "-o", "StrictHostKeyChecking=no", "-i", "/root/.ssh/id_rsa",
                    f"root@{selected_node.ip_address}", "docker", "load"
                ], stdin=sp1.stdout, stdout=subprocess.PIPE)
                sp1.stdout.close()
                sp2.communicate()
                logger.info(f"Image {tag} synced successfully.")
            except Exception as e:
                logger.error(f"Could not deploy to {remote_docker_host}: {e}")
                raise RuntimeError(f"Deploy to {selected_node.hostname} failed.")
            
            container_name = f"sputniq-{config.platform.name}-{service_id}"
            
            # Remove old container if it exists
            try:
                old_c = remote_client.containers.get(container_name)
                old_c.remove(force=True)
                logger.info(f"Removed old container {container_name}")
            except docker.errors.NotFound:
                pass
                
            runtime = getattr(config.platform, 'runtime', "docker")
            
            logger.info(f"Running new container {container_name} with runtime {runtime}")
            
            if runtime in ("docker", "docker-compose"):
                try:
                    # Using host.docker.internal allows linux docker to hit host's exposed localhost services
                    target_client = remote_client
                    
                    # Merge platform env vars with default ones
                    container_env = config.platform.env.copy() if hasattr(config.platform, "env") else {}
                    container_env.update({
                        "SPUTNIQ_KAFKA_BROKERS": "kafka:9092",
                        "KAFKA_BOOTSTRAP_SERVERS": "kafka:9092",
                        "SPUTNIQ_SERVICE_ID": service_id
                    })
                    
                    c = target_client.containers.run(
                        image=tag,
                        name=container_name,
                        detach=True,
                        ports={"8080/tcp": None},
                        extra_hosts={"kafka": "172.18.0.1"},
                        environment=container_env
                    )
                    c.reload()
                    port_bindings = c.attrs.get("NetworkSettings", {}).get("Ports", {}).get("8080/tcp")
                    port = port_bindings[0]["HostPort"] if port_bindings else "N/A"
                    
                    result_nodes.append({
                        "service_id": service_id,
                        "ip": selected_node.ip_address,
                        "hostname": selected_node.hostname,
                        "container": container_name,
                        "port": port,
                        "status": "running"
                    })
                except Exception as ce:
                    logger.error(f"Failed to start container {container_name}: {ce}")
                    result_nodes.append({
                        "service_id": service_id,
                        "ip": selected_node.ip_address,
                        "hostname": selected_node.hostname,
                        "container": container_name,
                        "port": "N/A",
                        "status": "failed",
                        "error": str(ce)
                    })
        
        logger.info("Deployment completed successfully")
        return {
            "app_id": config.platform.name,
            "version": config.platform.version,
            "nodes": result_nodes
        }
    except Exception as e:
        logger.error(f"Deployment failed: {str(e)}", exc_info=True)
        raise

