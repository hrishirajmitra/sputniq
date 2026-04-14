# 2a — Application Packaging & Deployment Process

**Document:** Deploy Process  
**Platform:** Sputniq AgentOS  
**Version:** 1.0.0

---

## 1. Overview

This document details how an application is packaged and deployed on the Sputniq platform. The deployment pipeline transforms a validated `config.json` and source code into running containerized services connected via a Kafka message bus.

---

## 2. Deployment Pipeline

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ VALIDATE │──▶│ GENERATE │──▶│ PACKAGE  │──▶│  DEPLOY  │──▶│  VERIFY  │
│  config  │   │artifacts │   │  images  │   │  launch  │   │  health  │
└──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
```

---

## 3. Stage 1: Validation

```bash
agentos validate --config config.json
```

The validation pipeline performs:

| Check                     | Description                                             |
|---------------------------|---------------------------------------------------------|
| Schema validation         | Pydantic model validation of all config sections        |
| Reference resolution      | Agent→Tool, Agent→Model, Workflow Step→Entity bindings  |
| Cycle detection           | DFS-based cycle detection in workflow step graphs        |
| Runtime contracts          | Model capabilities match agent requirements             |
| Source tree validation    | Entrypoint files exist, correct symbols exported         |

---

## 4. Stage 2: Build Artifact Generation

```bash
agentos build --config config.json --out .agentos/build
```

The generator creates a service for every entity:

**Application Services** (Data Plane):
- One service per `agent` — runs the agent loop
- One service per `tool` — exposes the tool via HTTP

**Platform Services** (Control + Data Plane):
- `gateway` — Request ingress, session/correlation ID assignment
- `workflow-coordinator` — LangGraph-based step dispatch
- `tool-dispatcher` — Schema validation, timeout enforcement
- `model-proxy` — LLM provider abstraction, retry logic
- `schema-registry` — Tool/message schema storage
- `artifact-store` — Build artifact metadata
- `build-controller` — Build pipeline management

Each service gets:
```
services/<service-id>/
├── Dockerfile           # Multi-stage Python build
├── service.yaml         # Service metadata
├── requirements.txt     # Python dependencies
└── .sputniq_service_runner.py  # Auto-generated service entrypoint
```

Additionally, the build produces:
```
schemas/
├── tool-schemas.json      # Compiled tool input/output schemas
└── message-schemas.json   # Message type JSON schemas (AgentInput, ToolRequest, etc.)
```

And the **build manifest**:
```json
{
  "platform": "my-agent-system",
  "version": "1.0.0",
  "namespace": "default",
  "built_at": "2026-04-14T12:00:00Z",
  "services": {
    "weather-agent": { "kind": "agent", "plane": "data-plane" },
    "get-weather": { "kind": "tool", "plane": "data-plane" },
    "gateway": { "kind": "platform", "plane": "data-plane" }
  }
}
```

---

## 5. Stage 3: Packaging

```bash
agentos package --dir .agentos/build
```

Packaging performs these steps:

### 5.1 Image Build
Uses the Docker SDK to build an OCI image for every service:
```python
# Internal: ImageBuilder.build_service(service_dir, tag)
docker build -t namespace/service-id:version .agentos/build/services/service-id
```

### 5.2 Security Scanning
The `DependencyScanner` runs vulnerability analysis against each service's `requirements.txt`:
- Detects known CVEs in dependencies
- Reports severity (LOW / MEDIUM / HIGH / CRITICAL)
- Blocks deployment if CRITICAL vulnerabilities are found

### 5.3 Artifact Bundle
Generates a signed deployment bundle:
```json
{
  "bundle_id": "b-a3f9c12def45",
  "version": "1.0.0",
  "config_hash": "sha256:abc123...",
  "built_at": "2026-04-14T12:00:00Z",
  "services": {
    "weather-agent": {
      "image": "example/weather-agent:1.0.0",
      "digest": "sha256:def456..."
    }
  },
  "signature": "unsigned-local-build"
}
```

---

## 6. Stage 4: Deployment

### 6.1 Via CLI
```bash
agentos deploy --env dev
```

### 6.2 Via ZIP Upload (UI or cURL)
```bash
# Package the app as a ZIP
python scripts/create_sample_app.py

# Upload via cURL
curl -X POST -F "file=@sample_app.zip" http://localhost:8000/api/v1/registry/upload-zip
```

### 6.3 Via API
```bash
# Trigger bootstrap (system + apps)
curl -X POST http://localhost:8000/api/v1/system/bootstrap \
  -H "Content-Type: application/json" \
  -d '{"app_repository": [{"name": "my-app"}]}'
```

### 6.4 Deployment Steps (Internal)

1. **Network Provisioning**: Creates an isolated Docker bridge network (`sputniq-runtime-<app-slug>`)
2. **Port Allocation**: Dynamically allocates host ports starting from 8100, avoiding conflicts
3. **Service Definition Write**: Writes `.sputniq_service.json` into each service directory with full deployment context
4. **Image Build**: Builds Docker images for all services
5. **Container Launch**: Starts containers with:
   - Network attachment (runtime + control networks)
   - Environment variables (Kafka, service ID, port, role)
   - Docker labels for management (`sputniq.managed=true`, etc.)
6. **Health Verification**: Waits up to 18 seconds for each container to reach `running` status
7. **Rollback on Failure**: If any container fails, all started containers are removed

---

## 7. Stage 5: Verification

After deployment, the platform verifies:

| Check                | Method                                    |
|----------------------|-------------------------------------------|
| Container status     | Docker API `container.status == "running"`|
| Health endpoint      | `GET /health` on each service             |
| Registry sync        | Workflows, tools, agents registered in API|
| Message bus          | Kafka topics created and accessible       |

```bash
# Check health
curl http://localhost:8000/health

# List deployments
curl http://localhost:8000/api/v1/registry/deployments

# Check boot status
curl http://localhost:8000/api/v1/system/boot-status
```

---

## 8. Deployment Architecture

```
┌──────────────────────────────────────────────────────┐
│                    Docker Host                        │
│                                                       │
│  ┌─────────────┐  ┌──────────┐  ┌─────────────────┐ │
│  │  Zookeeper   │  │  Kafka   │  │  sputniq-redis  │ │
│  └─────────────┘  └──────────┘  └─────────────────┘ │
│                                                       │
│  ┌────────────────────────────────────────────────┐  │
│  │         sputniq-control network                │  │
│  │                                                 │  │
│  │  ┌─────────────────┐  ┌───────────────────┐   │  │
│  │  │  API Server      │  │   Jaeger (Traces) │   │  │
│  │  │  :8000            │  │   :16686           │   │  │
│  │  └─────────────────┘  └───────────────────┘   │  │
│  └────────────────────────────────────────────────┘  │
│                                                       │
│  ┌────────────────────────────────────────────────┐  │
│  │    sputniq-runtime-<app> network               │  │
│  │                                                 │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐       │  │
│  │  │ gateway  │ │ agent    │ │ tool     │       │  │
│  │  │ :8100    │ │ :8101    │ │ :8102    │       │  │
│  │  └──────────┘ └──────────┘ └──────────┘       │  │
│  │  ┌──────────┐ ┌──────────┐                     │  │
│  │  │model-    │ │workflow- │                     │  │
│  │  │proxy     │ │coord    │                     │  │
│  │  │:8103     │ │:8104    │                     │  │
│  │  └──────────┘ └──────────┘                     │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

---

## 9. Runtime Options

| Runtime          | Command                           | Use Case              |
|------------------|-----------------------------------|-----------------------|
| Docker Compose   | `docker compose up --build -d`    | Local development     |
| Manual           | `pip install -e . && uvicorn ...` | Active development    |
| Kubernetes       | `agentos deploy --env prod`       | Production deployment |
