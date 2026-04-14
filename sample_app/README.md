# Weather Assistant - Sputniq Sample App

This is a complete sample agentic application built on the Sputniq platform. 

## Structure

* `config.json`: The core platform schema definition linking everything together, pointing to tools, agents, models, and infrastructural dependencies like Redis and Kafka.
* `src/agents/weather.py`: Implements `WeatherAgent`, a Python class using the `@agent` decorator. It accepts an `AgentContext`, invokes a weather tool, interacts with the LLM API (`gemini-2.5-flash`), and emits an event payload.
* `src/tools/weather_api.py`: Implements a simple asynchronous tool (`get_weather`) mock to feed logic to the agent.

## Deployment & Testing

Make sure you are at the root of the sputniq framework or run these inside your virtual environment where `sputniq` is installed.

### 1. Validate the Application

Test the configuration file against the Sputniq schema validation:

```bash
PYTHONPATH=src python3 src/sputniq/cli/main.py validate --config sample_app/config.json
```

### 2. Build the App Runtime Files

Generate the orchestration engine (Docker and Kubernetes YAML) according to the `docker-compose` platform runtime defined in the config:

```bash
PYTHONPATH=src python3 src/sputniq/cli/main.py build --config sample_app/config.json --out sample_app/build
```

### 3. Deploy the Sandbox Stack (Optional)

Deploy the generated stack locally (you must have Docker running to use the builder's generated compose file):

```bash
PYTHONPATH=src python3 src/sputniq/cli/main.py deploy --env local
```

### Note
In production, you'll need to inject `GEMINI_API_KEY` into your environment during the run to interact with Google Gemini dependencies.
