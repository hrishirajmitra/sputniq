# Sputniq  
## Platform Implementation Specification  

**Config-driven orchestration for agentic AI systems**  
DEFINE • BUILD • PACKAGE • DEPLOY • RUN • MANAGE  

---

## 1. Overview

AgentOS is a config-driven orchestration platform for building, deploying, and managing distributed agentic AI systems. Developers describe agents, tools, models, and workflows in a declarative `config.json` alongside source code. The platform interprets this configuration and automatically provisions the full infrastructure stack: generating service definitions, packaging containers, deploying components, wiring communication, and managing runtime execution.

The platform abstracts containerization, service mesh communication, scaling, and observability — allowing developers to focus entirely on agent logic and system behavior.

---

## 2. Core Concepts

### 2.1 First-Class Entities

The platform treats four entity types as first-class citizens. All configuration, tooling, observability, and runtime management is expressed in terms of these entities.

- **Agent** — An autonomous decision-making unit. Perceives context, selects actions, invokes tools and models. Stateful across turns within a session.  
- **Tool** — A callable function with a typed schema. Agents invoke tools for concrete operations: API calls, database queries, file I/O, external services.  
- **Model** — An inference endpoint with a defined input/output contract. May be hosted (OpenAI, Anthropic, Bedrock) or locally deployed (vLLM).  
- **Workflow** — A directed execution graph composed of agents, tools, model calls, and control flow nodes (branches, loops, parallel fans).  

---

### 2.2 Communication Model

All inter-entity communication is message-driven and asynchronous. Components communicate via a central message bus. Every message carries:

- `correlation_id` (request trace)  
- `session_id` (user/task group)  
- entity routing  
- typed payload  
- nanosecond timestamp  

**Message kinds:**
AgentInput, AgentOutput, ToolRequest, ToolResponse, ModelRequest, ModelResponse, WorkflowStep, WorkflowComplete, Error, HeartBeat.

---

## 3. Platform Lifecycle

The platform operates across six stages. Each stage has precise inputs, outputs, and a well-defined set of operations. No stage is optional in a production deployment.

---

### Stage 1 — DEFINE

Author `config.json` — the single source of truth for system topology  

#### 3.1 What happens
The developer authors `config.json` at the project root alongside source code. This file declares all agents, tools, models, workflows, and infrastructure requirements. No infrastructure code is written.

---

### 3.2 config.json top-level schema

```json
{
  "platform": { "name", "version", "namespace", "runtime", "region" },
  "agents":    [ AgentDefinition ],
  "tools":     [ ToolDefinition ],
  "models":    [ ModelDefinition ],
  "workflows": [ WorkflowDefinition ],
  "infrastructure": InfrastructureConfig,
  "observability": ObservabilityConfig
}
````

---

### 3.3 AgentDefinition

```json
{
  "id": "research-agent",
  "description": "Searches the web and synthesizes answers",
  "entrypoint": "src/agents/research.py:ResearchAgent",
  "model": "gpt-4o",
  "tools": ["web-search", "summarizer"],
  "memory": { "type": "sliding-window", "max_tokens": 8192 },
  "system_prompt": "You are a research assistant...",
  "max_turns": 20,
  "timeout_ms": 30000,
  "retry": { "max_attempts": 3, "backoff": "exponential" }
}
```

---

### 3.4 ToolDefinition

```json
{
  "id": "web-search",
  "entrypoint": "src/tools/search.py:search",
  "schema": {
    "input":  { "query": { "type": "string", "required": true } },
    "output": { "results": { "type": "array" } }
  },
  "timeout_ms": 10000,
  "rate_limit": { "requests_per_minute": 60 }
}
```

---

### 3.5 Validation rules

* All ref fields in workflow steps must resolve to a declared entity ID
* Circular dependencies in workflow steps are rejected at parse time
* Model capabilities must include function-calling for agents that use tools
* Secret references must correspond to declared names in `infrastructure.secrets`
* Tool schema types must be valid JSON Schema primitives

---

### Stage 2 — BUILD

Validate the definition graph and generate all service artifacts

#### 3.6 Build pipeline (in order)

* Config validation — Full schema validation with dependency graph resolution
* Code analysis — Validates entrypoints and method signatures
* Dependency resolution — Reads requirements/package manifests
* Service definition generation — Dockerfiles, YAML, SDK shims
* Message schema registry — Compiles tool schemas
* Build manifest — Writes `build.manifest.json`

---

### 3.7 Generated file tree

```
.agentos/build/
  manifest.json
  services/
    research-agent/
      Dockerfile
      service.yaml
      requirements.txt
    web-search/
      Dockerfile
      service.yaml
    workflow-coordinator/
      Dockerfile
      service.yaml
  schemas/
    tool-schemas.json
    message-schemas.json
```

---

### Stage 3 — PACKAGE

Build container images, scan for vulnerabilities, produce versioned bundle

#### 3.8 Packaging steps

* Image build
* Image scanning (Trivy)
* Artifact bundle creation
* Registry push

---

### 3.9 Bundle manifest

```json
{
  "bundle_id": "b-20240512-a3f9c",
  "version": "1.4.2",
  "config_hash": "sha256:abc123...",
  "built_at": "2024-05-12T14:32:00Z",
  "services": {
    "research-agent": {
      "image": "registry.example.com/myns/research-agent:1.4.2-a3f9c1",
      "digest": "sha256:def456..."
    }
  },
  "signature": "base64-encoded-sig"
}
```

---

### Stage 4 — DEPLOY

Instantiate and wire all services into the target runtime

#### 3.10 Deployment pipeline

* Infrastructure provisioning
* Autoscaling setup
* Message bus provisioning
* Secret injection
* Health verification

---

### Stage 5 — RUN

Agent-driven workflow execution

#### 3.11 Runtime components

**Gateway Service**

* Handles inbound requests
* Assigns IDs
* Authentication
* Rate limiting

**Workflow Coordinator**

* State machine
* Step dispatch
* Error handling

**Agent Runtime**

* Context reconstruction
* Tool execution loop
* Output generation

**Tool Dispatcher**

* Schema validation
* Execution isolation
* Timeout enforcement

**Model Proxy**

* Provider abstraction
* Retry logic
* Metrics & logging

---

### Stage 6 — MANAGE

Observability, scaling, and operations

#### 3.12 Observability stack

* Distributed tracing
* Structured logging
* Metrics (Prometheus)
* Agent action log

---

### 3.13 Management API

| Method | Path                        | Description       |
| ------ | --------------------------- | ----------------- |
| GET    | /workflows                  | List workflows    |
| POST   | /workflows/{id}/trigger     | Trigger execution |
| GET    | /executions/{exec_id}       | Execution details |
| DELETE | /executions/{exec_id}       | Cancel execution  |
| GET    | /agents/{id}/sessions       | Active sessions   |
| DELETE | /agents/{id}/sessions/{sid} | Terminate session |
| GET    | /tools/{id}/invocations     | Tool history      |
| GET    | /models/{id}/usage          | Model usage       |
| POST   | /deployments                | Deploy bundle     |
| POST   | /deployments/{id}/rollback  | Rollback          |
| GET    | /health                     | System health     |

---

## 4. Server Architecture

### 4.1 Control Plane Services

| Service              | Responsibility  | Language | Scaling    |
| -------------------- | --------------- | -------- | ---------- |
| api-server           | Management API  | Go       | Horizontal |
| build-controller     | Build pipeline  | Go       | Single     |
| workflow-coordinator | Workflow engine | Go       | Horizontal |
| schema-registry      | Schema storage  | Go       | Horizontal |
| artifact-store       | Metadata        | Go       | Horizontal |

---

### 4.2 Data Plane Services

* gateway
* model-proxy
* tool-dispatcher
* agent services
* tool services

---

### 4.3 Storage Dependencies

| Component      | Purpose       | Technology       |
| -------------- | ------------- | ---------------- |
| State store    | Session state | Redis / DynamoDB |
| Artifact store | Metadata      | PostgreSQL       |
| Object storage | Bundles       | S3               |
| Message bus    | Communication | NATS / Kafka     |
| Metrics store  | Metrics       | Prometheus       |
| Trace store    | Traces        | Jaeger           |
| Log sink       | Logs          | Loki             |

---

## 5. SDK Interface

### 5.1 Python SDK

```python
from agentos import agent, tool, context

@agent(id='research-agent')
class ResearchAgent:
    async def run(self, ctx: context.AgentContext) -> str:
        results = await ctx.tool('web-search', query=ctx.input)
        return await ctx.model('gpt-4o', messages=[
            {'role': 'system', 'content': 'Summarize the following...'},
            {'role': 'user',   'content': str(results)}
        ])
```

---

### 5.2 Context Methods

* ctx.input
* ctx.session_id
* ctx.tool(...)
* ctx.model(...)
* ctx.memory
* ctx.emit(...)
* ctx.logger

---

## 6. CLI Reference

```
agentos init
agentos validate
agentos build
agentos package
agentos deploy
agentos run
agentos logs
agentos trace
agentos status
agentos scale
agentos rollback
agentos diff
agentos destroy
```

---

## 7. Security Model

* Secrets never stored in config/images
* Message-bus-only communication
* Tool isolation with resource constraints
* Authentication via JWT / mTLS
* Full audit logging
* Image signing (Cosign)

---

## 8. Error Handling Model

Errors propagate as structured messages:

```json
{
  "error_code": "TOOL_TIMEOUT",
  "message": "web-search timed out after 10000ms",
  "entity_id": "web-search",
  "correlation_id": "...",
  "session_id": "...",
  "retryable": true,
  "context": { "query": "latest AI news" }
}
```

---
