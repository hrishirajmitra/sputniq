# 3a — Server Initialization (Bootstrap Process)

**Document:** Bootstrap Process Explanation  
**Platform:** Sputniq AgentOS  
**Version:** 1.0.0

---

## 1. Overview

The Sputniq platform implements a **4-phase boot sequence** modeled after traditional application server architectures. The boot process separates the **System Boot Cycle** (infrastructure initialization) from the **App Boot Cycle** (application provisioning), ensuring a clean dependency chain from bare metal to running applications.

All components communicate via a centralized **Kafka message bus** started in Phase 1.

---

## 2. Boot Sequence Phases

```
╔══════════════════════════════════════════════════════════════╗
║                    BOOT MACHINE (Boot Script)                ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  Phase 1: Initial Bootstrap                                  ║
║  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐ ║
║  │Check Repo│─▶│Start     │─▶│Provision │─▶│Start System │ ║
║  │          │  │Kafka     │  │M/C       │  │Master       │ ║
║  └──────────┘  └──────────┘  └──────────┘  └──────┬──────┘ ║
║                                                     │        ║
║  Phase 2: System Master Start                       ▼        ║
║  ┌──────────────────────────────────────────────────────┐    ║
║  │              System INIT Config                       │    ║
║  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌──────────┐  │    ║
║  │  │Server   │ │App      │ │Security │ │Logging   │  │    ║
║  │  │L/C Mgr  │ │L/C Mgr  │ │Service  │ │Service   │  │    ║
║  │  └─────────┘ └─────────┘ └─────────┘ └──────────┘  │    ║
║  │  ┌─────────┐ ┌──────────────────────────────────┐   │    ║
║  │  │Deploy   │ │Request Dispatcher / HA Mgr / LB │   │    ║
║  │  │Manager  │ └──────────────────────────────────┘   │    ║
║  │  └─────────┘                                         │    ║
║  └──────────────────────────────────────────────────────┘    ║
║                              │                                ║
║  Phase 3: App Lifecycle      ▼                                ║
║  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐  ║
║  │Fetch     │─▶│Read      │─▶│Load      │─▶│Place        │  ║
║  │Apps      │  │Config    │  │Config    │  │Instances    │  ║
║  │from Repo │  │(instance)│  │(LDAP)    │  │(HA/Nodes)   │  ║
║  └──────────┘  └──────────┘  └──────────┘  └─────────────┘  ║
║                                                              ║
║  Phase 4: Machine Provisioning & Routing                     ║
║  ┌──────────┐  ┌──────────┐  ┌──────────┐                   ║
║  │Get IP    │─▶│Connect   │─▶│Run Agent │                   ║
║  │          │  │to Repo   │  │          │                   ║
║  └──────────┘  └──────────┘  └──────────┘                   ║
║                                                              ║
║          ┌─────────────────────────────────────┐             ║
║          │     All via KAFKA Message Bus        │             ║
║          └─────────────────────────────────────┘             ║
╚══════════════════════════════════════════════════════════════╝
```

---

## 3. Phase 1 — Initial Bootstrap (Boot Script)

**Entry Point:** `sputniq.runtime.bootstrap.PlatformBootstrap.run()`  
**CLI Command:** `agentos bootstrap`  
**API Endpoint:** `POST /api/v1/system/bootstrap`

### Step 1.1: Check Repository

The boot script verifies the repository structure:
- **System Repository**: Contains core system components (platform binaries, INIT configurations)
- **App Repository**: Contains application definitions, instance configurations, and load-balancing parameters

```python
# Internally calls:
await self._check_repo()
# Verifies system_repo and app_repo paths are accessible
```

### Step 1.2: Start Kafka

Ensures the central message bus is operational. In Docker Compose, this is handled by service dependencies. For manual startup:

```bash
docker compose up -d zookeeper kafka
```

The Kafka bus connects **all** platform components — every system service, lifecycle manager, and application communicates through it.

### Step 1.3: Provision Machine(s)

The `ServerLifecycleManager` provisions the initial operational machine(s):

```
Get IP → Connect to Repo → Run Agent
```

- **Get IP**: Allocate a network address for the node
- **Connect to Repo**: Establish connection to the system/app repository
- **Run Agent**: Start the node agent that manages containers on this machine

### Step 1.4: Start System Master

Hands control to the `SystemMaster` for Phase 2.

---

## 4. Phase 2 — System Master Start & Initialization

**Component:** `sputniq.runtime.system_master.SystemMaster`

The System Master reads the **System INIT Config** and launches all required core system services in order:

| # | Service                    | Responsibility                                      |
|---|----------------------------|-----------------------------------------------------|
| 1 | Server Lifecycle Manager   | Machine provisioning, health checks, decommissioning |
| 2 | App Lifecycle Manager      | Application bootstrap sequence                       |
| 3 | Security Service           | JWT/mTLS authentication, secret management           |
| 4 | Logging Service            | Structured log aggregation                           |
| 5 | Deployment Manager         | Build artifact tracking, image management            |
| 6 | Request Dispatcher         | Load balancing, HA failover, request routing          |

### System INIT Config Format

```json
{
  "kafka_bootstrap_servers": "localhost:9092",
  "lb_strategy": "round-robin",
  "initial_nodes": 1,
  "services": [
    "server-lifecycle-manager",
    "app-lifecycle-manager",
    "security-service",
    "logging-service",
    "deployment-manager",
    "request-dispatcher"
  ]
}
```

Each service is started sequentially. If any service fails to start, the boot sequence halts and reports the failure.

---

## 5. Phase 3 — Application Lifecycle Management

**Component:** `sputniq.runtime.lifecycle.AppLifecycleManager`

Once all system services are running, the App Lifecycle Manager takes over:

### Step 3.1: Fetch Apps from Repository

Retrieves the list of applications registered in the App Repository.

### Step 3.2: Read Instance Configuration

For each application, reads the per-instance configuration:
```json
{
  "instance_id": "weather-agent-0",
  "replicas": 1,
  "weight": 1,
  "ldap_group": null
}
```

### Step 3.3: Load Configuration

Loads and resolves the full configuration for each instance. This is where **external system integration** (e.g., LDAP) occurs:
- Resolve user/group bindings
- Apply security policies
- Inject environment-specific parameters

### Step 3.4: Place Instances

Coordinates with the **HA/Nodes Manager** (Request Dispatcher) to determine optimal instance placement across available nodes. Uses the configured load-balancing strategy (round-robin or weighted) for distribution.

---

## 6. Phase 4 — Machine Provisioning & App Execution Flow

### 6.1 Provisioning Workflow

When new machines are needed:
```
Get IP → Connect to Repo → Run Agent
```

The `ServerLifecycleManager` handles:
1. IP allocation from the address pool
2. Repository connectivity verification  
3. Node agent startup for container management

### 6.2 Request Routing

Once applications are running:

```
External Request
       │
       ▼
┌──────────────────┐
│Request Dispatcher│
│                  │──── HA/Nodes Manager ────┐
│  Load Balancer   │                          │
└──────┬───────────┘                          │
       │                                      │
       ▼                                      ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   App 1      │  │   App 2      │  │   App N      │
│   Node A     │  │   Node B     │  │   Node C     │
│  ┌────────┐  │  │  ┌────────┐  │  │  ┌────────┐  │
│  │Agent   │  │  │  │Agent   │  │  │  │Agent   │  │
│  │Gateway │  │  │  │Gateway │  │  │  │Gateway │  │
│  │Dispatch│  │  │  │Dispatch│  │  │  │Dispatch│  │
│  └────────┘  │  │  └────────┘  │  │  └────────┘  │
└──────────────┘  └──────────────┘  └──────────────┘
```

### 6.3 Communication

All inter-service communication flows through the **Kafka message bus**:

| Topic                     | Publisher           | Consumer             |
|---------------------------|---------------------|----------------------|
| `sputniq.boot.events`    | SystemMaster        | Observability        |
| `sputniq.agent.input`    | Gateway             | Agent Runtime        |
| `sputniq.agent.output`   | Agent Runtime       | Workflow Coordinator |
| `sputniq.tool.request`   | Agent Runtime       | Tool Dispatcher      |
| `sputniq.tool.response`  | Tool Dispatcher     | Agent Runtime        |
| `sputniq.model.request`  | Agent Runtime       | Model Proxy          |
| `sputniq.model.response` | Model Proxy         | Agent Runtime        |
| `sputniq.workflow.step`  | Coordinator         | Various              |
| `sputniq.heartbeat`      | All Services        | Health Monitor       |

---

## 7. Boot Cycle Separation

The platform explicitly separates two boot cycles:

### System Boot Cycle (System INIT Bootstrap)

| Phase               | Component              | Action                        |
|---------------------|------------------------|-------------------------------|
| `repo_check`        | Boot Script            | Verify repository access      |
| `kafka_start`       | Boot Script            | Ensure message bus is up      |
| `provision_mc`      | ServerLifecycleManager | Provision initial machines    |
| `system_master_start` | SystemMaster         | Read INIT config              |
| `system_services_starting` | SystemMaster    | Launch system services        |
| `system_services_ready`    | SystemMaster    | All services confirmed running|

### App Boot Cycle (App Bootstrap)

| Phase               | Component              | Action                        |
|---------------------|------------------------|-------------------------------|
| `fetch_apps`        | AppLifecycleManager    | Retrieve app list from repo   |
| `read_config`       | AppLifecycleManager    | Read instance configuration   |
| `load_config`       | AppLifecycleManager    | Load config (LDAP binding)    |
| `place_instances`   | AppLifecycleManager    | Coordinate with HA Manager    |
| `instances_running` | AppLifecycleManager    | All instances confirmed up    |

---

## 8. Monitoring Boot Status

### Via CLI
```bash
agentos boot-status
```

### Via API
```bash
curl http://localhost:8000/api/v1/system/boot-status
```

Returns:
```json
{
  "status": "bootstrapped",
  "system_boot_phase": "system_services_ready",
  "app_boot_phase": "instances_running",
  "is_system_ready": true,
  "is_app_ready": true,
  "system_services": [
    {"service_name": "server-lifecycle-manager", "status": "running"},
    {"service_name": "app-lifecycle-manager", "status": "running"},
    {"service_name": "security-service", "status": "running"},
    {"service_name": "logging-service", "status": "running"},
    {"service_name": "deployment-manager", "status": "running"},
    {"service_name": "request-dispatcher", "status": "running"}
  ],
  "provisioned_nodes": ["boot-node-0"],
  "boot_events": [...]
}
```
