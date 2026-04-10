import sys
from pathlib import Path
from sputniq.config.parser import load_config
from sputniq.ops.deploy import deploy_app

config = load_config('research_app/config.json')
deploy_app(config, Path('research_app'))
