#!/bin/bash
PYTHONPATH=src ./.venv/bin/uvicorn sputniq.api.server:app --reload --port 8000
