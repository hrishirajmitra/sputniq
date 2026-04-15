# Sputniq End-to-End Setup & Deployment Guide

This guide covers how to start the Sputniq infrastructure from completely scratch, deploy a bundled application (`app.zip`), and test the distributed system.

## 1. Start the Infrastructure Nodes
First, simulate the physical hardware cluster by spinning up the Docker-in-Docker nodes.

```bash
cd infrastructure
./setup-nodes.sh
cd ..
```
*Note: This script will create a bridge network and spin up 15 `infrastructure-node-*` containers with internal Docker engines and SSH access.*

## 2. Start the Control Plane
Boot up the main API server, Kafka, and Zookeeper using Docker Compose. The API server has been configured to automatically mount SSH keys to securely communicate with the nodes.

```bash
docker compose build
docker compose up -d
```
*Wait ~15-30 seconds for Kafka to stabilize and the API server to be fully ready.*

## 3. Deploy your Application
With `app.zip` (containing your `sputniq.json`, `app.py`, etc.) in the root directory, upload it to the registry. The Control Plane will parse your zip, build the necessary Docker images, and distribute them across the infrastructure nodes.

```bash
# Upload and deploy the zip file
curl -X POST "http://127.0.0.1:8000/api/v1/registry/upload-zip" -F "file=@app.zip"
```

## 4. Verify Deployments
Check the status of the deployed containers across the cluster:

```bash
# View all registered deployments globally
curl -s http://localhost:8000/api/v1/registry/deployments

# Or, manually inspect a specific infrastructure node:
docker exec infrastructure-node-6-1 docker ps
```

## 5. Test the Pipeline
To test the pipeline end-to-end, you need to find where the **query pipeline** was deployed and hit its endpoint.

**A. Find the Node IP and Port:**
1. Identify which node the `api-query-pipeline` was deployed to (e.g., `infrastructure-node-6-1`).
2. Get that node's internal IP address:
```bash
docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' infrastructure-node-6-1
```
3. Check the mapped port on that node:
```bash
docker exec infrastructure-node-6-1 docker ps
```

**B. Send a Test Query:**
Using the IP and Port identified above (e.g., `172.18.0.2` and `32768`), run:

```bash
curl -s -X POST "http://<NODE_IP>:<PORT>/api/ask" \
     -H "Content-Type: application/json" \
     -d '{"query": "Fetch the custom API data from https://jsonplaceholder.typicode.com/todos/1"}'
```

The request will seamlessly traverse from the node's API gateway -> LangGraph -> Kafka (to find the worker) -> and finally return the LLM's response!

## 6. Tear Down and Cleanup
If you ever need to completely restart or clean up your environment:

```bash
# 1. Take down the API server and Kafka
docker compose down

# 2. Take down the 15 simulated infrastructure nodes
cd infrastructure
docker compose -f docker-compose-nodes.yml down
cd ..

# 3. Destroy the shared network
docker network rm sputniq-network
```
