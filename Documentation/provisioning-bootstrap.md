# VM Provisioning and Bootstrap Process

The Sputniq platform manages a static inventory of bare-metal Linux virtual machines. To transition a VM from a blank slate into a ready-to-use worker node for the platform (capable of hosting agents, tools, and the orchestrator), a strict bootstrap process is followed.

## 1. Inventory & Access
The platform maintains a static list of 10-15 VMs (defined in `sputniq.ops.inventory`).
- **Prerequisites**: SSH access to these VMs via key-based authentication for a user with `sudo` privileges.

## 2. Bootstrap Phases

When a VM is provisioned, the following sequence of commands is executed over SSH:

### Phase 1: System Update & Dependencies
Update the package manager and install requisite tools.
```bash
sudo apt-get update -y
sudo apt-get upgrade -y
sudo apt-get install -y ca-certificates curl gnupg lsb-release
```

### Phase 2: Docker Installation
Install the Docker engine from a blank slate.
```bash
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
```

### Phase 3: Post-Installation & Security
Add the current user to the Docker group so that the platform deployment engine can run containers without full root access.
```bash
sudo usermod -aG docker $USER
```

## 3. Runtime Control
Once the bootstrap process completes, the platform relies on Kafka for operational instructions. The orchestrator deploys target Docker containers (e.g. Agent runtimes, Tool runners) to these initialized VMs and delegates load via Kafka topics.