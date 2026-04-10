# Sputniq AgentOS

AgentOS is a config-driven orchestration platform for building, deploying, and managing distributed agentic AI systems.

![image](https://img.shields.io/badge/Status-Beta-blue)
![image](https://img.shields.io/badge/Python-3.11%2B-green)

---

## ⚡ The Output - The UI
We've added a stunning React-styled Dashboard built directly into the control API. By deploying the platform, you'll be able to access the web UI at `http://localhost:8000/`.

The UI allows you to visually inspect the running Workflows, monitor Registered Tools, and single-click upload the generated zip deployments in an immersive dark mode console setting.

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

## 🏗️ Generating & Deploying a Sample Agent App

AgentOS supports deploying your entire Agent application (source code and `config.json`) as a single zip archive.

1. **Generate the dummy deployment**:
   We have a script to rapidly generate a functional sample app and package it:

   ```bash
   python scripts/create_sample_app.py
   ```
   *(This creates `sample_app.zip` containing a `config.json` and basic python agents)*

2. **Deploy via the UI (Easiest)**:
   Navigate to `http://localhost:8000/` and upload the newly generated `sample_app.zip`. The UI will reflect the deployed services in real-time.

3. **Deploy via CLI/cURL**:
   You can deploy the sample application programmatically to the Control API:
   ```bash
   curl -X POST -F "file=@sample_app.zip" http://localhost:8000/api/v1/registry/upload-zip
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
