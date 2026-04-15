# Platform Architecture & System Flow

## I. Core Definitions & Application Model

### 1. App Model Definition
* **Artefacts:** The core binaries or code components. These represent the executable and logic layer of the application that the platform hosts and orchestrates.
* **Dev Model:** The development workflow and standards. This encompasses the guidelines, SDKs, and tooling provided to developers to build compatible applications.
* **Packaging & Deployment:** How the application is packaged and deployed to the platform. Applications are typically packaged alongside a declarative configuration (`sputniq.json` or `config.json`) into an archive (like a zip file) and pushed to the control plane.
* **Sample App:** A baseline application used for testing and validation, demonstrating the end-to-end capabilities of the platform.

### 2. Runtime Definition
Define the runtime environment specific to the app artifact type.
* **System Runtime:** The foundational runtime environment that executes the core platform components (e.g., Control API, Load Balancers, Lifecycle Managers, Kafka).
* **App Type Runtime:** The sandboxed execution environment provisioned specifically for an application based on its type (e.g., Python agent processes, web workers), managing its dependencies and execution loop.

### 3. Repository (Repo) Structure
* **System Repository:** Contains core system components (e.g., Binaries, INIT configurations, orchestration scripts).
* **App Repository:** Divided into distinct definitions:
  * **App:** The base application definitions (source code, primary logic).
  * **Instances + Load:** Configurations for specific application instances and load balancing parameters dictating how the application spreads across nodes.

### 4. Boot Cycles
Startups are separated into two distinct phases:
* **System Boot Cycle (System INIT bootstrap):** The bootstrapping of the cluster, control plane, and central messaging infrastructure.
* **App Boot Cycle (App bootstrap):** The process of deploying, configuring, and starting individual application workloads on the platform.

---

## II. System Architecture & Boot Sequence

### Phase 1: Initial Bootstrap (The First Machine)
The process begins on the "BOOT M/C" (Boot Machine) via a primary Boot Script.
1. **Check Repo:** Verify the repository structure and fetch initial states.
2. **Start Kafka:** Initialize the central Kafka message bus (which connects all underlying services and agents).
3. **Provision M/C:** Provision the initial operational machines/nodes.
4. **Start System Master:** Initialize the core control plane to begin accepting commands.

### Phase 2: System Master Start & Initialization
Once the System Master starts, it reads the System INIT config and launches all required core System Services.
* **Core System Services Launched:**
  * **Server Lifecycle (L/C) Manager:** Monitors running server nodes and their health.
  * **App Lifecycle (L/C) Manager:** Oversees the deployment, startup, and shutdown of applications.
  * **Security Service:** Handles authentication, authorization, and secret management.
  * **Logging Service:** Centralized telemetry and logging collection.
  * **Deployment Manager:** Orchestrates the staging and distribution of application builds.
  * **Request Dispatcher / High Availability (HA) Manager / Load Balancer (LB):** Routes incoming traffic and distributes internal load.

### Phase 3: Application Lifecycle Management (App L/C Mgr)
The App Lifecycle Manager takes over to bootstrap the applications based on the configurations.
1. **Executes the startup sequence.**
2. **Retrieves the list of apps** from the repository or deployed registry.
3. **Reads the configuration** for specific instances.
4. **Loads the configuration for each instance** (integrating with external systems like LDAP if required).
5. **Coordinates with the HA/Nodes Manager** to place instances optimally across available nodes.

### Phase 4: Machine Provisioning & App Execution Flow
1. **Provisioning Workflow:** When a new machine is provisioned, the flow is: Get IP -> Connect to Repo -> Run Agent (join cluster).
2. **Routing:** External/Internal requests hit the Request Dispatcher, which routes traffic through the Load Balancer (LB) and interfaces with the HA/Nodes Manager.
3. **App Execution:** Applications (e.g., App 1, App 2) run in their designated nodes with internal components executing their business logic.
4. **Communication:** All system services, lifecycle managers, and applications communicate via the centralized Kafka message bus started in Phase 1.
