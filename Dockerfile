FROM python:3.11-slim

WORKDIR /app

RUN pip install --upgrade pip
RUN apt-get update && apt-get install -y docker.io openssh-client && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/pyproject.toml
COPY src/ /app/src/

# Install the package
RUN pip install -e .

EXPOSE 8000

# Server will be started via docker-compose command
