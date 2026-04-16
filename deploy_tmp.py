import json
import sys
from pathlib import Path
from sputniq.ops.deploy import deploy_app
from sputniq.config.parser import load_config, resolve_references, detect_cycles

with __import__('zipfile').ZipFile('app.zip', 'r') as zip_ref:
    zip_ref.extractall('extracted_app')

config = load_config(Path('extracted_app/sputniq.json'))
resolve_references(config)
detect_cycles(config)
deploy_app(config, Path('extracted_app'))
