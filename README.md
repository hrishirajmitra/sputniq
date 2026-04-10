# Sputniq AgentOS

AgentOS is a config-driven orchestration platform for building, deploying, and managing distributed agentic AI systems.

![image](https://img.shields.io/badge/Status-Beta-blue)
![image](https://img.shields.io/badge/Python-3.11%2B-green)

---

## ⚡ The Output - The UI
We've added a live dashboard directly into the control API. By deploying the platform, you'll be able to access the web UI at `http://localhost:8000/`.

The UI lets you inspect workflows, monitor registered tools, upload ZIP deployments, and chat directly with any running agent service from the same control plane.

---

## 🚀 One-Click Run (The Whole Thing)

To spin up the entire multi-service architecture including the **AgentOS Control API**, **Kafka Message Bus**, and **Zookeeper**, just use `docker compose`:

```bash
# 1. Build and run the whole stack in the background
docker compose up --build -d

# 2. Access the UI
# 🌐 Navigate your browser to: http://localhost:8000/
```

## 🛠️ Manual Installation (For Development)

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

## 🏗️ Generating & Deploying Sample Agent Apps

AgentOS supports deploying your entire Agent application (source code and `config.json`) as a single zip archive.

1. **Package the simple weather demo**:
   ```bash
   python scripts/create_sample_app.py
   ```
   *(This creates `sample_app.zip` from the checked-in `sample_app/` directory.)*

2. **Package the complex mission-control demo**:
   ```bash
   python scripts/create_complex_agent_app.py
   ```
   *(This creates `complex_agent_app.zip` with multiple agents, tools, and workflows.)*

3. **Deploy via the UI (Easiest)**:
   Navigate to `http://localhost:8000/`, upload one of the ZIP archives, then use the built-in chatbox to talk to any running agent deployment.

4. **Deploy via CLI/cURL**:
   You can deploy the sample application programmatically to the Control API:
   ```bash
   curl -X POST -F "file=@complex_agent_app.zip" http://localhost:8000/api/v1/registry/upload-zip
   ```

---

## ⌨️ CLI Reference

You can orchestrate and manage repos manually via the command line. Ensure you have run `pip install -e .` to activate the CLI.

- **`agentos init .`**: Scaffolds a new AgentOS repository with a standard `config.json` and directories structure.
- **`agentos validate`**: Runs schema validation, cycle detection, and reference verification against your `config.json`.
- **`agentos build`**: Generates deployment artifacts (Dockerfiles, requirements) into `.agentos/build`.
- **`agentos package`**: Bundles local services and logic.
- **`agentos deploy`**: Orchestrates application deployment (push to orchestrator).
- **`agentos logs` / `agentos status`**: Display platform metrics and status.

---

## 📚 Documentation Architecture

For deeper understanding of how AgentOS is put together and scaled:
- [📖 Implementation Phases](Documentation/implementation-phases.md)
- [📖 Project Plan](Documentation/project-plan.md)
- [📖 Testing & Integration](Documentation/testing-integration-plan.md)
