import json
import zipfile
from pathlib import Path
import os

def create_sample_app():
    # Setup paths
    base_dir = Path(__file__).parent.parent
    sample_app_dir = base_dir / "sample_app"
    sample_app_dir.mkdir(exist_ok=True)
    
    # 1. Generate config.json mapping tools, agents, workflows
    config_json = {
        "platform": {
            "name": "sample-agent-system",
            "version": "1.0.0",
            "namespace": "example",
            "runtime": "docker-compose",
            "region": "local"
        },
        "agents": [
            {
                "id": "weather-agent",
                "description": "Answers questions about the weather.",
                "entrypoint": "src/agents/weather.py:WeatherAgent",
                "model": "gpt-mock",
                "tools": ["get-weather"]
            }
        ],
        "tools": [
            {
                "id": "get-weather",
                "entrypoint": "src/tools/weather.py:get_weather",
                "schema": {
                    "input": {
                        "type": "object", 
                        "properties": {
                            "location": {"type": "string"}
                        },
                        "required": ["location"]
                    },
                    "output": {"type": "string"}
                }
            }
        ],
        "models": [
            {
                "id": "gpt-mock",
                "provider": "openai",
                "capabilities": ["chat"]
            }
        ],
        "workflows": [
            {
                "id": "weather-workflow",
                "description": "Workflow for fetching weather",
                "entrypoint_step": "step-1",
                "steps": [
                    {"id": "step-1", "type": "agent", "ref": "weather-agent"}
                ]
            }
        ]
    }
    
    # Write config.json
    with open(sample_app_dir / "config.json", "w") as f:
        json.dump(config_json, f, indent=2)
        
    # Write some dummy source code
    src_dir = sample_app_dir / "src"
    agents_dir = src_dir / "agents"
    tools_dir = src_dir / "tools"
    
    agents_dir.mkdir(parents=True, exist_ok=True)
    tools_dir.mkdir(parents=True, exist_ok=True)
    
    with open(agents_dir / "weather.py", "w") as f:
        f.write("class WeatherAgent:\\n    def process(self, context, message):\\n        return f'Fetching weather for: {message}'\\n")
        
    with open(tools_dir / "weather.py", "w") as f:
        f.write("def get_weather(location: str):\\n    return f'The weather in {location} is sunny.'\\n")


    print(f"Created sample app source in {sample_app_dir}")
    
    # 2. Package it into a .zip
    zip_path = base_dir / "sample_app.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(sample_app_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, sample_app_dir)
                zipf.write(file_path, arcname)
                
    print(f"Successfully packaged sample app into {zip_path}")
    
if __name__ == "__main__":
    create_sample_app()
