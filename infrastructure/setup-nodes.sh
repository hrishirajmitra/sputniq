#!/bin/bash
set -e

echo "Generating SSH keys for test nodes..."
mkdir -p .ssh-nodes
if [ ! -f .ssh-nodes/id_rsa ]; then
    ssh-keygen -t rsa -b 4096 -N "" -f .ssh-nodes/id_rsa
fi

cat << 'DOCKERFILE' > .ssh-nodes/Dockerfile
FROM docker:24-dind
RUN apk add --no-cache openssh bash python3
RUN mkdir -p /root/.ssh && chmod 700 /root/.ssh
RUN sed -i s/#PermitRootLogin.*/PermitRootLogin\ yes/ /etc/ssh/sshd_config
RUN ssh-keygen -A
COPY id_rsa.pub /root/.ssh/authorized_keys
RUN chmod 600 /root/.ssh/authorized_keys
CMD ["sh", "-c", "dockerd-entrypoint.sh & /usr/sbin/sshd -D"]
DOCKERFILE

echo "Generating docker-compose-nodes.yml..."
cat << 'COMPOSE' > docker-compose-nodes.yml
version: '3.8'

services:
COMPOSE

for i in $(seq 1 15); do
cat << COMPOSE >> docker-compose-nodes.yml
  node-$i:
    build:
      context: .ssh-nodes
      dockerfile: Dockerfile
    privileged: true
    networks:
      - sputniq_default
COMPOSE
done

cat << 'COMPOSE' >> docker-compose-nodes.yml

networks:
  sputniq_default:
    external: true
COMPOSE

echo "Building and starting 15 DinD nodes..."
docker network create sputniq_default || true
docker compose -f docker-compose-nodes.yml up -d --build

echo "Done! Nodes are running."
