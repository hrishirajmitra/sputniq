# 1a — Application Development Process

**Document:** DEV Process  
**Platform:** Sputniq AgentOS  
**Version:** 1.0.0

---

## 1. Overview

This document defines the complete development workflow for building applications on the Sputniq AgentOS platform. The platform uses a **config-driven, declarative** approach where developers express their system's topology in a `config.json` descriptor file alongside their source code.

---

## 2. Development Steps

### Step 1: Initialize Project

```bash
agentos init .
```

This scaffolds a new project with:
```
my-project/
├── config.json           # Descriptor file (system topology)
├── src/
│   ├── agents/           # Agent implementations
│   └── tools/            # Tool implementations
```

### Step 2: Define the Descriptor File (`config.json`)

The descriptor file is the **single source of truth** for the entire system. It declares:

| Section           | Purpose                                          |
|-------------------|--------------------------------------------------|
| `platform`        | Project metadata (name, version, namespace, runtime) |
| `agents`          | Autonomous agent definitions                     |
| `tools`           | Callable function definitions with typed schemas  |
| `models`          | LLM inference endpoint configurations            |
| `workflows`       | Directed execution graphs of steps                |
| `infrastructure`  | Secret management, message bus, state store       |
| `runtime`         | System vs App runtime definitions                 |
| `repository`      | System and App repository paths                   |
| `boot`            | Boot cycle parameters and instance configs        |

### Step 3: Implement Agent Logic

Agents are Python classes decorated with `@agent` and exposing an async `run()` method:

```python
from sputniq.sdk.decorators import agent
from sputniq.sdk.context import AgentContext

@agent(id="my-agent")
class MyAgent:
    async def run(self, ctx: AgentContext) -> str:
        # Access input
        user_query = ctx.input

        # Call a tool
        results = await ctx.tool("my-tool", query=user_query)

        # Call a model
        response = await ctx.model("gpt-4o", messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": str(results)},
        ])

        # Emit observability events
        ctx.emit("agent_response", {"response": response})
        return response
```

### Step 4: Implement Tool Logic

Tools are Python functions with typed input/output:

```python
def my_tool(query: str) -> dict:
    """A callable tool with a typed schema."""
    return {"query": query, "results": ["result1", "result2"]}
```

### Step 5: Validate Configuration

```bash
agentos validate
```

This runs:
- JSON schema validation
- Reference resolution (agents → tools → models)
- Cycle detection in workflow graphs
- Entrypoint file and symbol verification
- Runtime contract validation (e.g., function-calling capability)

### Step 6: Build Artifacts

```bash
agentos build
```

Generates the `.agentos/build/` tree:
```
.agentos/build/
├── manifest.json
├── services/
│   ├── my-agent/
│   │   ├── Dockerfile
│   │   ├── service.yaml
│   │   └── requirements.txt
│   └── my-tool/
│       ├── Dockerfile
│       └── service.yaml
└── schemas/
    ├── tool-schemas.json
    └── message-schemas.json
```

### Step 7: Test Locally

```python
# Unit testing with the SDK
from sputniq.sdk.context import AgentContext

ctx = AgentContext.for_testing(input="What's the weather?", tool_return={"temp": 25})
result = await MyAgent().run(ctx)
ctx.tool_mock.assert_called_once_with("my-tool", query="What's the weather?")
```

---

## 3. Interfaces

### 3.1 SDK Interface

| Interface                     | Description                              |
|-------------------------------|------------------------------------------|
| `@agent(id="...")`           | Class decorator to register an agent     |
| `AgentContext.input`          | The input payload for this invocation    |
| `AgentContext.session_id`     | Unique session identifier                |
| `AgentContext.correlation_id` | Request trace correlation ID             |
| `ctx.tool(tool_id, **kwargs)` | Invoke a registered tool                |
| `ctx.model(model_id, msgs)`  | Call an LLM endpoint                     |
| `ctx.memory`                  | Session memory (message history)         |
| `ctx.emit(event_type, data)` | Emit structured observability event      |
| `ctx.logger`                  | Structured logger for the agent          |

### 3.2 CLI Interface

| Command              | Description                              |
|----------------------|------------------------------------------|
| `agentos init .`     | Scaffold a new project                   |
| `agentos validate`   | Validate config.json                     |
| `agentos build`      | Generate build artifacts                 |
| `agentos package`    | Build container images + scan            |
| `agentos deploy`     | Deploy to target runtime                 |
| `agentos bootstrap`  | Run the full 4-phase boot sequence       |
| `agentos boot-status`| Show current boot phase                  |
| `agentos logs`       | View service logs                        |
| `agentos status`     | Show platform status                     |

### 3.3 API Interface

| Method | Endpoint                        | Description                  |
|--------|---------------------------------|------------------------------|
| POST   | `/api/v1/registry/upload-zip`   | Deploy an app from ZIP       |
| GET    | `/api/v1/registry/workflows`    | List registered workflows    |
| GET    | `/api/v1/registry/agents`       | List registered agents       |
| GET    | `/api/v1/registry/tools`        | List registered tools        |
| POST   | `/api/v1/system/bootstrap`      | Trigger platform bootstrap   |
| GET    | `/api/v1/system/boot-status`    | Current boot phase           |
| GET    | `/api/v1/system/services`       | List system services         |
| GET    | `/api/v1/nodes`                 | List provisioned nodes       |
| GET    | `/health`                       | System health check          |

---

## 4. Descriptor File Reference (`config.json`)

### 4.1 Platform Section

```json
{
  "platform": {
    "name": "my-agent-system",     // Required: unique system name
    "version": "1.0.0",           // Semantic version
    "namespace": "default",        // Deployment namespace
    "runtime": "docker-compose",   // "docker-compose" | "kubernetes"
    "region": "local"              // Deployment region
  }
}
```

### 4.2 Agent Definition

```json
{
  "id": "research-agent",
  "description": "Searches and synthesizes",
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

### 4.3 Tool Definition

```json
{
  "id": "web-search",
  "entrypoint": "src/tools/search.py:search",
  "schema": {
    "input":  { "type": "object", "properties": { "query": { "type": "string" } }, "required": ["query"] },
    "output": { "type": "string" }
  },
  "timeout_ms": 10000,
  "rate_limit": { "requests_per_minute": 60 }
}
```

### 4.4 Model Definition

```json
{
  "id": "gpt-4o",
  "provider": "openai",
  "capabilities": ["chat", "function-calling"],
  "endpoint": null,
  "config": {}
}
```

### 4.5 Workflow Definition

```json
{
  "id": "main-workflow",
  "description": "Primary execution workflow",
  "entrypoint_step": "step-1",
  "steps": [
    { "id": "step-1", "type": "agent", "ref": "research-agent", "next": ["step-2"] },
    { "id": "step-2", "type": "tool", "ref": "summarizer" }
  ]
}
```

### 4.6 Boot Cycle Configuration

```json
{
  "boot": {
    "auto_bootstrap": false,
    "system_init": {
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
    },
    "app_instances": [
      { "instance_id": "agent-0", "replicas": 1, "weight": 1 }
    ]
  }
}
```

### 4.7 Runtime & Repository

```json
{
  "runtime": {
    "system_runtime": "docker",
    "app_type_runtime": "python",
    "runtime_version": "3.11"
  },
  "repository": {
    "system_repo": ".",
    "app_repo": "."
  }
}
```

---

## 5. Developer Workflow Summary

```
┌─────────┐    ┌──────────┐    ┌─────────┐    ┌──────────┐    ┌─────────┐
│  init   │──▶│  write   │──▶│validate │──▶│  build   │──▶│  test   │
│  project│    │  code +  │    │ config  │    │artifacts │    │ locally │
│         │    │  config  │    │         │    │          │    │         │
└─────────┘    └──────────┘    └─────────┘    └──────────┘    └─────────┘
```
