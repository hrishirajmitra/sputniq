FROM python:3.11-slim

WORKDIR /app

RUN pip install --upgrade pip

COPY pyproject.toml /app/pyproject.toml
COPY src/ /app/src/

# Install the package
RUN pip install -e .

EXPOSE 8000

# Server will be started via docker-compose command
