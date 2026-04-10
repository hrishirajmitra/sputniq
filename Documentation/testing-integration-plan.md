# Sputniq Testing & Integration Plan

Because AgentOS abstracts the underlying orchestration and execution layers (infrastructure-as-a-service for AI), ensuring components integrate correctly is as critical as verifying individual microservices.

## 1. Testing Strategy

### 1.1 Unit Testing (Isolated logic)
*All code should be heavily unit-tested within its module using Python `pytest` and `unittest.mock`.*
*   **Target Components**: Data validation (Pydantic/JSON schemas), SDK interfaces (`AgentContext.tool()`, `AgentContext.model()`), config parsers, templating logic (`Dockerfile` generation), routing logic within the LangGraph orchestrator.
*   **Requirements**: Ensure branch coverage is >85%, edge cases (invalid schemas, recursive dependencies, missing secrets) are caught correctly, and syntax errors in Python agent entrypoints throw clear exceptions at parsing time.

### 1.2 Component Integration Testing (Inter-service)
*Testing two or more connected components, generally stubbing external dependencies like physical Kafka clusters or external DBs with specialized mock local equivalents.*
*   **Target Scenarios**:
    *   `gateway` assigns traces -> feeds message -> `workflow-coordinator` logs it correctly.
    *   `api-server` correctly updates state in PostgreSQL or a Mocked DB.
    *   `workflow-coordinator` triggers a `tool-dispatcher` -> ensures the dispatcher validates schemas and returns a `ToolResponse` or `Error`.
*   **Requirements**: Validate message types/payload structures using shared JSON Schemas across the wire.

### 1.3 End-to-End System Integration Testing
*End-to-End workflow validation across the full suite of microservices in a containerized test environment.*
*   **Target Workflows**:
    *   **The Happy Path**: A basic `@agent` receiving input -> using a mock `@tool` -> utilizing a mock `model` -> returning a verified string response.
    *   **The Error Path**: Test the structured propagation of errors (e.g. `TOOL_TIMEOUT` or model API rate limit). The `Error` interface must correctly surface through `model-proxy` back up to the user via the `gateway`.
    *   **The Build Path**: CLI correctly parses a dummy `config.json`, builds images without errors, runs Trivy, and pushes to a local dummy registry.
*   **Environment Setup**: Utilize `Docker Compose` referencing local containers linked with actual infrastructure (Redis, Kafka, Postgres, Jaeger, Prometheus) within isolated test namespaces.

## 2. Integration Environments

### 2.1 Local Developer Integration (`agentos local`)
Developers should have a local sandbox using `docker-compose` built directly into the CLI that dynamically spins up lightweight versions of the infrastructure (e.g., MiniKube, Redpanda instead of Kafka). 

### 2.2 Continuous Integration Pipeline (GitHub Actions or Gitlab CI)
*   **Pre-Submit CI**: Run Linters (Ruff/Flake8), Pre-commit hooks, Unit Tests, and static schema validation tests for all Pull Requests.
*   **Post-Merge Integration**: Trigger Dockerized E2E system tests, build control plane container images, and publish to development artifact registries.

## 3. Tool Mocking & Observability Validation
Since integrating with physical LLM Providers (OpenAI, Anthropic) during CI is expensive and flaky:
*   **LLM Mocking Framework**: The `model-proxy` must have a natively built-in integration test mode (e.g., `--stub-models=true`) that intercepts any `ModelRequest` and responds with a static payload based on request fingerprints.
*   **Trace Verifications**: During E2E tests, make API assertions against the Jaeger backend endpoint to verify that a single interaction generated an unbroken distributed trace consisting of spans involving Gateway, Coordinator, Proxy, and Tool execution.