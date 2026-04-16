# Sputniq AgentOS

AgentOS is a config-driven orchestration platform for building, deploying, and managing distributed agentic AI systems.
---

##  The Output - The UI
We've added a stunning React-styled Dashboard built directly into the control API. By deploying the platform, you'll be able to access the web UI at `http://localhost:8000/`.

The UI allows you to visually inspect the running Workflows, monitor Registered Tools, and single-click upload the generated zip deployments in an immersive dark mode console setting.

---

## One-Click Run (The Whole Thing)

To spin up the entire multi-service architecture including the **AgentOS Control API**, **Kafka Message Bus**, and **Zookeeper**, just use `docker compose`:

```bash
# 0. Create a docket network for shared use 
docker network create sputniq-network

# 1. Build and run the whole stack in the background
docker compose up --build -d

# 2. Access the UI
# Navigate your browser to: http://localhost:8000/
```

## Manual Installation (For Development)

If you don't want to use Docker Compose, you can develop directly against local services:

1. Install the package in editable mode from the root of this repository:

```bash
pip install -e .
```

2. Start the Kafka Message bus locally:
```bash
docker compose up -d zookeeper kafka
```

3. Run the Control API Server with `uvicorn`:
```bash
uvicorn sputniq.api.server:app --reload --host 0.0.0.0 --port 8000
```
*(Proceed to `http://localhost:8000/` to test your local API server)*

---

##  Generating & Deploying a Sample Agent App

AgentOS supports deploying your entire Agent application (source code and `sputniq.json` or `config.json`) as a single zip archive.

1. **Generate the dummy deployment**:
   You can generate and deploy a functional sample application:

   ```bash
   cd sample_gemini_app/
   # Package the app to a zip manually or via scripts
   ```
   *(Ensure it contains `sputniq.json` and basic python agents)*

2. **Deploy via the UI (Easiest)**:
   Navigate to `http://localhost:8000/` and upload the newly generated app archive. The UI will reflect the deployed services in real-time.

3. **Deploy via CLI/cURL**:
   You can deploy the sample application programmatically to the Control API:
   ```bash
   curl -X POST -F "file=@your_app.zip" http://localhost:8000/api/v1/registry/upload-zip
   ```

---

## Starting Resource Nodes (App Instance Hosts)

To start the computational nodes that the platform will provision application instances on, execute the infrastructure setup script. This utilizes Docker-in-Docker to quickly spin up agent workers.

```bash
cd infrastructure
./setup-nodes.sh
```
*This script will generate SSH keys, build the DinD image, and start 15 nodes attached to the `sputniq_default` network.*

---

## CLI Reference

You can orchestrate and manage repos manually via the command line. Ensure you have run `pip install -e .` to activate the CLI.

- **`sputniq init .`** / **`agentos init .`**: Scaffolds a new AgentOS repository with a standard `sputniq.json` and directories structure.
- **`sputniq validate`**: Runs schema validation, cycle detection, and reference verification against your `config.json`.
- **`sputniq build`**: Generates deployment artifacts (Dockerfiles, requirements).
- **`sputniq package`**: Bundles local services and logic.
- **`sputniq deploy`**: Orchestrates application deployment (push to orchestrator).

---

## Documentation Architecture

For comprehensive platform capabilities, review the system documentation:

**Core Architecture & System Boot**
- [ Platform Architecture & System Flow](Documentation/platform-architecture.md)

**Hack-3 Deliverables (Execution & Verification)**
- [ DEV Process Document (1a)](Documentation/dev-process.md)
- [ Deploy Process Document (2a)](Documentation/deploy-process.md)
- [ Bootstrap Process Document (3a)](Documentation/bootstrap-process.md)
- [ Execution Flow Illustration (4a)](Documentation/execution-flow.md)

**General Project Plans**
- [ Implementation Phases](Documentation/implementation-phases.md)
- [ Project Plan](Documentation/project-plan.md)
- [ Testing & Integration](Documentation/testing-integration-plan.md)

