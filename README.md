# Sputniq AgentOS

Sputniq AgentOS is a config-driven platform for building, validating, packaging, and operating agentic AI systems.

The platform treats four entity types as first-class citizens:

- **Agent**: an autonomous decision-making unit with session state, memory, tool access, and model access.
- **Tool**: a callable operation with a typed input/output schema.
- **Model**: an inference endpoint with a provider, capabilities, endpoint, and provider-specific configuration.
- **Orchestration**: a LangGraph execution graph composed of agents, tools, models, and control-flow nodes such as branches, loops, joins, and parallel fans.

## Run The Control Plane

```bash
docker compose up --build -d
```

The control API and registry UI run at `http://localhost:8000/`.

For local development:

```bash
pip install -e .
uvicorn sputniq.api.server:app --reload --host 0.0.0.0 --port 8000
```

## Upload Format

Uploads are zip archives with a root-level `config.json` and the source files referenced by every agent and tool entrypoint.

By default, `/api/v1/registry/upload-zip` validates the archive, registers agents/tools/models/orchestrations, and generates build artifacts in a temporary `.agentos/build` tree. Docker deployment is opt-in:

```bash
curl -X POST -F "file=@my_agent_system.zip" \
  "http://localhost:8000/api/v1/registry/upload-zip?deploy=false"
```

Set `deploy=true` when the local Docker daemon is available and you want Sputniq to build and run service containers.

## Config Shape

```json
{
  "platform": {"name": "support-system", "runtime": "docker-compose"},
  "agents": [
    {
      "id": "triage-agent",
      "entrypoint": "src/agents/triage.py:TriageAgent",
      "model": "gpt-4o",
      "tools": ["ticket-search"]
    }
  ],
  "tools": [
    {
      "id": "ticket-search",
      "entrypoint": "src/tools/ticket_search.py:search",
      "schema": {"input": {"query": {"type": "string"}}, "output": {"results": {"type": "array"}}}
    }
  ],
  "models": [
    {"id": "gpt-4o", "provider": "openai", "capabilities": ["chat", "function-calling"]}
  ],
  "orchestrations": [
    {
      "id": "support-flow",
      "entrypoint_step": "triage",
      "steps": [
        {"id": "triage", "type": "agent", "ref": "triage-agent", "next": ["classify"]},
        {
          "id": "classify",
          "type": "branch",
          "condition": "case_type",
          "routes": {"known": "lookup", "new": "draft"},
          "next": ["lookup", "draft"]
        },
        {"id": "lookup", "type": "tool", "ref": "ticket-search"},
        {"id": "draft", "type": "model", "ref": "gpt-4o"}
      ]
    }
  ]
}
```

The legacy `workflows` key and `/api/v1/registry/workflows` endpoints remain as compatibility aliases for `orchestrations`.

## CLI

- `agentos init .`: create a standard project layout and `config.json`
- `agentos validate --config config.json`: validate schema, references, and graph cycles
- `agentos build --config config.json --out .agentos/build`: generate service, schema, model endpoint, and orchestration graph artifacts
- `agentos package`, `agentos deploy`, `agentos logs`, `agentos status`: operational helpers

## Documentation

- [Implementation Phases](Documentation/implementation-phases.md)
- [Project Plan](Documentation/project-plan.md)
- [Testing & Integration](Documentation/testing-integration-plan.md)
