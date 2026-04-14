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
        for i in range(1, 16):
            # Assuming docker-compose-nodes.yml services start with infrastructure-node
            # Let's just use the default docker-compose container names: infrastructure-node-1-1
            container_name = f"infrastructure-node-{i}-1"
            res = subprocess.run(["docker", "inspect", "-f", "{{range $k, $v := .NetworkSettings.Networks}}{{$v.IPAddress}}{{end}}", container_name], capture_output=True, text=True)
            ip = res.stdout.strip()
            if ip:
                nodes.append(VMNode(
                    id=f"vm-{i:02d}",
                    hostname=f"node-{i:02d}",
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
