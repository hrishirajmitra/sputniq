# AgentOS Implementation Phases

This document outlines the phased implementation strategy for the Sputniq AgentOS platform, breaking the work into independent, parallelizable streams.

## Phase 1: Foundation & Definition (The Control Data Layer)
**Goal:** Establish the core data structures, configuration parsing, and artifact generation pipeline (`DEFINE` & `BUILD`).
*   **1.1 Data Models & Schemas**: Define JSON schemas for `AgentDefinition`, `ToolDefinition`, `ModelDefinition`, and Core Messages (`AgentInput`, `ToolRequest`, `Error`). Implement these as Pydantic models.
*   **1.2 Configuration Parser**: Develop the Python logic to parse, validate, and resolve the dependency graph of `config.json`.
*   **1.3 Service Generator**: Create the templating engine (e.g., Jinja2) to dynamically generate `Dockerfile`, `service.yaml`, and `requirements.txt` based on the parsed configuration.
*   **1.4 AgentOS CLI (Base)**: Introduce the `agentos init`, `agentos validate`, and `agentos build` commands.

## Phase 2: Runtime Environment (The Data Plane)
**Goal:** Build the execution engines that run the agents, tools, and models (`RUN`).
*   **2.1 Python SDK (`agentos`)**: Implement the core agent decorator `@agent`, the `AgentContext` object, and mock handlers for `ctx.tool` and `ctx.model`.
*   **2.2 Message Bus Integration**: Setup local Kafka bindings. Define publishers and subscribers for the system components.
*   **2.3 Workflow Coordinator**: Implement the core state machine using LangGraph to dispatch steps, handle routing, and manage branching based on the parsed config.
*   **2.4 Executors**: Build the `tool-dispatcher` (validates schemas, enforces timeouts) and the `model-proxy` (standardizes LLM provider APIs, adds retry logic).
*   **2.5 Gateway Service**: Implement the ingress service (FastAPI) to handle incoming user requests and assign session/correlation IDs.

## Phase 3: Control Plane & Infrastructure (The Management Layer)
**Goal:** Establish the persistent state engines, API layer, and artifact management (`MANAGE`).
*   **3.1 API Server**: Build the FastAPI management application serving `/workflows`, `/agents`, `/deployments`, etc.
*   **3.2 State Management**: Implement session state storage using Redis/DynamoDB adapters and historical metadata storage using PostgreSQL.
*   **3.3 Artifact & Schema Registries**: Set up microservices to track built image manifests (`build.manifest.json`), signatures, and active tool schemas.
*   **3.4 CLI (Ops)**: Expand the CLI with `agentos logs`, `agentos status`, and operational commands.

## Phase 4: Packaging and Deployment (The Ops Plane)
**Goal:** Automate the containerization, scanning, and orchestration injection (`PACKAGE` & `DEPLOY`).
*   **4.1 Image Builder**: Integrate container building using Docker SDK for Python (or Buildah).
*   **4.2 Security & Scanning**: Embed Trivy or similar scanning tools into the packaging pipeline. Create the Artifact Bundle manifest generator.
*   **4.3 Deployment Engine**: Build the logic to instantiate the Kubernetes/Docker-Compose YAML files, wire secrets, and configure autoscaling parameters based on the `target runtime`.
*   **4.4 CLI (Deployment)**: Implement `agentos package` and `agentos deploy`.

## Phase 5: Observability & Production Readiness
**Goal:** Wire tracing, metrics, and security perimeters for robust systemic health.
*   **5.1 Distributed Tracing**: Instrument all components, specially Gateway and Workflow Coordinator, using OpenTelemetry to forward traces to Jaeger.
*   **5.2 Metrics & Logging**: Export Promtheus metrics across all Control and Data plane services. Aggregate structured JSON logs using Loki.
*   **5.3 Auth & Security**: Implement JWT/mTLS on the Gateway service and isolate the `tool-dispatcher` within secure networking boundaries.