# 1a. DEV Process Document

This document outlines the Application Development process on the Sputniq platform.

## Supported Interfaces
The Sputniq platform typically provides a robust SDK defining:
* **Tool Registration Interface:** Let's developers annotate standard Python functions to be discoverable by agents.
* **Service/Agent Definition:** Developers create classes inheriting from base agent abstractions.
* **Message Bus Interface (Kafka):** Used to communicate across services in a micro-service architecture.

## The Descriptor File (`sputniq.json`)
The application defines its topology via a JSON descriptor file, mapping the application structure. It must include:
* Application Metadata (name, version)
* Components definition (Agents, Tools)
* Dependencies and Scaling rules (Instances)
* Environment Variables and Secrets

## Steps to Develop a Sputniq App
1. **Initialize Workspace:** Run the system CLI or manually define the app directory structure.
2. **Implement Business Logic:** Use the provided SDK to author custom tools and intelligence modules (e.g., `src/agents/`, `src/tools/`).
3. **Write Configuration:** Describe the environment, required memory limits, and node assignments in `sputniq.json`.
4. **Local Testing:** Test scripts using the platform local runner to simulate deployment.
5. **Package Output:** Bundle logic into a zip or a tarball alongside `sputniq.json` for deployment.
