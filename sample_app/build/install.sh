#!/bin/bash
set -e

echo "Ensuring Linux Pre-requisites for Sputniq Deployment..."

if [ -x "$(command -v apt-get)" ]; then
    sudo apt-get update
    sudo apt-get install -y python3.11 python3.11-venv curl docker.io docker-compose-v2
elif [ -x "$(command -v yum)" ]; then
    sudo yum update -y
    sudo yum install -y python3 curl docker
    # Amazon Linux / CentOS specifics omitted for brevity
fi

echo "Pre-requisites installed successfully."
