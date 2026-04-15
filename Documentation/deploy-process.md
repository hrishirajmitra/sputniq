# 2a. Deploy Process Document

This document defines the Packaging and Deployment lifecycle of a Sputniq application.

## Packaging
1. **Source Bundling:** The application repository (containing the Python source, required SDK components, and the `sputniq.json` descriptor) is zipped.
2. **Dependency Resolution:** The system builder reads the dependency list and creates packaging artifacts (like Dockerfiles or raw python setups).
3. **Validation:** The control plane applies a validation schema against the packaged `sputniq.json` before accepting it.

## Deployment Workflows
1. **Upload:** External CI tools or developers push the zip artifact via the Control API (`POST /registry/upload-zip`).
2. **System Ingestion:** The Control API unpackages and registers the new version within the System Repository.
3. **Distribution Setup:** The Deployment Manager updates the list of active apps, storing the definitions.
4. **Rolling Update / Scheduling:** The App Lifecycle Manager reads the newly available definitions, coordinates with the HA/Nodes Manager, and schedules instances to restart on provisioned worker nodes across the cluster.
