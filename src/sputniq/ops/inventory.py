import logging
import json
import os
import subprocess
from dataclasses import dataclass
from typing import List
import random

logger = logging.getLogger(__name__)

@dataclass
class VMNode:
    id: str
    hostname: str
    ip_address: str
    username: str
    role: str = "worker"
    is_provisioned: bool = False

def get_inventory() -> List[VMNode]:
    """Retrieve the pool of available VM nodes from Docker."""
    nodes = []
    try:
        # Find all running containers that match the infrastructure node naming pattern
        res_ps = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True)
        container_names = [n for n in res_ps.stdout.splitlines() if n.startswith("infrastructure-node")]
        
        for idx, container_name in enumerate(container_names, start=1):
            res = subprocess.run(["docker", "inspect", "-f", "{{range $k, $v := .NetworkSettings.Networks}}{{$v.IPAddress}}{{end}}", container_name], capture_output=True, text=True)
            ip = res.stdout.strip()
            if ip:
                nodes.append(VMNode(
                    id=f"vm-{idx:02d}",
                    hostname=container_name,
                    ip_address=ip,
                    username="root"
                ))
    except Exception as e:
        logger.error(f"Error fetching inventory: {e}")
    return nodes

def get_available_node() -> VMNode:
    """Find a randomly available node for deployment."""
    nodes = get_inventory()
    if not nodes:
        raise RuntimeError("No nodes available in inventory")
    return random.choice(nodes)
