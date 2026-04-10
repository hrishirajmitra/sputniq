# Sputniq AgentOS Comprehensive Testing Plan

## 1. Unit Testing Strategy
### Components
- **Config Parser & Cycle Detection**: Test `sputniq.config.parser` to ensure linear DAG trees and reject circular dependencies (`test_circular_deps`).
- **Template Generation**: Test `engine.py` by mocking Jinja files and asserting correctness of output files (`Dockerfile`, `service.yaml`, `install.sh`).
- **Control Plane API**: Validate schemas (`pydantic.BaseModel` tests for definitions) and mock `docker` objects safely.

## 2. Integration Testing
- **Hierarchical Deployments**: Use a mock `builder.py` to ensure tool dependencies run *before* agents, and `WEB_SEARCH_SERVICE_URL` is generated properly in local memory prior to agent execution.
- **Teardown / Lifecycle**: Deploy test components labeled with `run_id`, trigger `/deployments/{run_id}` via `httpx` testing, and assert `docker rm` was invoked for all returned containers. 
- **Log Streaming**: Validate that tail queries on `GET /api/v1/logs/{cid}` accurately stream standard output buffers without crashing on not-found objects.

## 3. End-to-End (E2E) & Load Testing
- Create a pure, headless `debian:12` container and pipe `install.sh` via SSH to verify autonomous dependency deployment on Vanilla Linux targets.
- Load Test using Locust hitting `/api/ask` simultaneously. Ensures that the dynamic scaling and proxy mapping can handle concurrent execution properly.

## Identified Logical Flaws & Streamlining Results
1. **Dynamic Ephemeral Port Collision**: Originally, agents statically assumed ports like 8005 or mapped to simple localhost references. The redesign now pulls tool allocations and dynamically feeds ENV URLs sequentially. A better flaw-fix (Future Phase): Service Registry instead of flat ENV passing (helps scale-ups).
2. **Circular Dependency Pitfalls**: LangGraph workflows might deadlock. Added logic checks to the config DAG parse mapping.
3. **Ghost Containers**: Deletion endpoints now search by `run_id` labels instead of loosely grepping component names, entirely mitigating ghost deployments left active post-deletion.