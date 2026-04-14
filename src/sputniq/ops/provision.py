import logging
import asyncio
from typing import List

from sputniq.ops.inventory import VMNode, get_inventory

logger = logging.getLogger(__name__)

BOOTSTRAP_SCRIPT = """
#!/bin/bash
set -e

echo "Starting phase 1: System Update"
sudo apt-get update -y
sudo apt-get install -y ca-certificates curl gnupg lsb-release

echo "Starting phase 2: Docker Installation"
sudo mkdir -p /etc/apt/keyrings
if [ ! -f /etc/apt/keyrings/docker.gpg ]; then
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
fi
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

echo "Starting phase 3: Permissions"
sudo usermod -aG docker $USER
echo "Bootstrap complete."
"""

async def provision_node_mock(node: VMNode):
    """
    Mock SSH provisioning process.
    In a real scenario, this uses 'asyncssh' to execute BOOTSTRAP_SCRIPT on the VM.
    """
    logger.info(f"Connecting to {node.username}@{node.ip_address} ({node.hostname})...")
    await asyncio.sleep(1) # simulate network latency
    
    logger.info(f"[{node.hostname}] Running bootstrap script...")
    await asyncio.sleep(2) # simulate apt-get installs and docker setup
    
    node.is_provisioned = True
    logger.info(f"[{node.hostname}] Successfully provisioned with Docker.")

async def provision_cluster():
    """Initializes the entire static inventory of VMs."""
    inventory = get_inventory()
    logger.info(f"Starting cluster provisioning for {len(inventory)} VMs.")
    
    # Provision all nodes concurrently
    tasks = [provision_node_mock(node) for node in inventory]
    await asyncio.gather(*tasks)
    
    logger.info("All nodes have been provisioned successfully.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(provision_cluster())
