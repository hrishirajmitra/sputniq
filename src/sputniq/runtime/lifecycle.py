"""Lifecycle Managers — Server L/C Manager and App L/C Manager.

Server Lifecycle Manager
    Manages machine/container lifecycle: provisioning, health-checking,
    and decommissioning of nodes.

App Lifecycle Manager
    Manages application bootstrap:
    1. Retrieve list of apps from the repository
    2. Read per-instance configuration
    3. Load configuration (LDAP / external system integration point)
    4. Coordinate with HA/Nodes Manager for placement
    5. Trigger deployment
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from sputniq.models.boot import AppBootPhase, BootEvent

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
#  Server Lifecycle Manager
# ═══════════════════════════════════════════════════════════════════════════


class ServerLifecycleManager:
    """Manages the lifecycle of machines/nodes.

    Provisioning workflow:
      Get IP → Connect to Repo → Run Agent
    """

    def __init__(self, *, bus_producer: Any | None = None) -> None:
        self.bus_producer = bus_producer
        self._nodes: dict[str, dict[str, Any]] = {}

    async def start(self, init_config: dict[str, Any] | None = None) -> "ServerLifecycleManager":
        logger.info("Server Lifecycle Manager started")
        return self

    async def stop(self) -> None:
        logger.info("Server Lifecycle Manager stopped")

    # ── Node Management ─────────────────────────────────────────────────

    async def provision_node(self, node_id: str, *, ip_address: str | None = None) -> dict[str, Any]:
        """Provision a new machine node.

        Flow: Get IP → Connect to Repo → Run Agent
        """
        ip = ip_address or f"10.0.0.{len(self._nodes) + 10}"
        node = {
            "node_id": node_id,
            "ip_address": ip,
            "status": "provisioning",
            "provisioned_at_ns": time.time_ns(),
            "containers": [],
        }

        logger.info("Provisioning node '%s' at %s", node_id, ip)

        # Step 1: Get IP (already done above)
        # Step 2: Connect to Repo
        node["repo_connected"] = True
        logger.info("Node '%s' connected to repository", node_id)

        # Step 3: Run Agent (node agent — manages containers on this node)
        node["agent_running"] = True
        node["status"] = "ready"
        logger.info("Node '%s' agent running — node is ready", node_id)

        self._nodes[node_id] = node
        return node

    async def decommission_node(self, node_id: str) -> None:
        """Decommission a node, stopping all containers."""
        if node_id in self._nodes:
            self._nodes[node_id]["status"] = "decommissioned"
            logger.info("Node '%s' decommissioned", node_id)

    async def health_check(self, node_id: str) -> dict[str, Any]:
        """Check the health of a provisioned node."""
        node = self._nodes.get(node_id)
        if not node:
            return {"node_id": node_id, "status": "unknown"}
        return {
            "node_id": node_id,
            "status": node["status"],
            "ip_address": node["ip_address"],
            "containers": len(node.get("containers", [])),
        }

    def list_nodes(self) -> list[dict[str, Any]]:
        """Return all provisioned nodes."""
        return list(self._nodes.values())

    def get_available_nodes(self) -> list[dict[str, Any]]:
        """Return nodes that are ready to accept workloads."""
        return [n for n in self._nodes.values() if n["status"] == "ready"]


# ═══════════════════════════════════════════════════════════════════════════
#  App Lifecycle Manager
# ═══════════════════════════════════════════════════════════════════════════


class AppLifecycleManager:
    """Manages the application bootstrap sequence (Phase 3).

    Steps:
      1. Execute startup sequence
      2. Retrieve list of apps from the repository
      3. Read configuration for specific instances
      4. Load instance configuration (LDAP integration point)
      5. Coordinate with HA/Nodes Manager to place instances
    """

    def __init__(
        self,
        *,
        server_lc_manager: ServerLifecycleManager | None = None,
        ha_manager: Any | None = None,
        bus_producer: Any | None = None,
    ) -> None:
        self.server_lc_manager = server_lc_manager
        self.ha_manager = ha_manager
        self.bus_producer = bus_producer
        self._apps: dict[str, dict[str, Any]] = {}
        self._instances: dict[str, list[dict[str, Any]]] = {}
        self._boot_events: list[BootEvent] = []

    async def start(self, init_config: dict[str, Any] | None = None) -> "AppLifecycleManager":
        logger.info("App Lifecycle Manager started")
        return self

    async def stop(self) -> None:
        logger.info("App Lifecycle Manager stopped")

    # ── App Bootstrap Sequence ──────────────────────────────────────────

    async def bootstrap_apps(
        self,
        app_repository: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Execute the full application bootstrap sequence.

        Parameters
        ----------
        app_repository : list
            List of app definitions from the repository, each containing
            at minimum ``name``, ``config_path``, and optionally
            ``instances`` configuration.
        """
        deployed: list[dict[str, Any]] = []

        # Phase 3, Step 1: Execute startup sequence
        self._emit_event(AppBootPhase.FETCH_APPS, "started")
        logger.info("App L/C Manager: fetching %d apps from repository", len(app_repository))

        for app_def in app_repository:
            app_name = app_def.get("name", "unknown")

            # Step 2: Read configuration for specific instances
            self._emit_event(AppBootPhase.READ_CONFIG, "started", details={"app": app_name})
            instance_configs = app_def.get("instances", [{"instance_id": f"{app_name}-0"}])
            logger.info("App '%s': %d instance(s) configured", app_name, len(instance_configs))

            # Step 3: Load instance configuration (LDAP integration point)
            self._emit_event(AppBootPhase.LOAD_CONFIG, "started", details={"app": app_name})
            for inst in instance_configs:
                inst["loaded"] = True
                # LDAP integration stub: in production this would resolve
                # user/group bindings, security policies, etc.
                inst["ldap_resolved"] = inst.get("ldap_group") is not None
            logger.info("App '%s': instance configs loaded", app_name)

            # Step 4: Coordinate with HA/Nodes Manager for placement
            self._emit_event(AppBootPhase.PLACE_INSTANCES, "started", details={"app": app_name})
            placements = await self._place_instances(app_name, instance_configs)

            self._apps[app_name] = app_def
            self._instances[app_name] = placements
            deployed.extend(placements)

            logger.info("App '%s': %d instance(s) placed", app_name, len(placements))

        self._emit_event(AppBootPhase.INSTANCES_RUNNING, "completed")
        return deployed

    async def get_app_status(self, app_name: str) -> dict[str, Any]:
        """Return the status of a bootstrapped application."""
        if app_name not in self._apps:
            return {"app": app_name, "status": "not_found"}
        return {
            "app": app_name,
            "status": "running",
            "instances": self._instances.get(app_name, []),
        }

    def list_apps(self) -> list[dict[str, Any]]:
        """Return all managed applications and their instance counts."""
        return [
            {
                "name": name,
                "instance_count": len(self._instances.get(name, [])),
                "status": "running",
            }
            for name in self._apps
        ]

    # ── Internal Helpers ────────────────────────────────────────────────

    async def _place_instances(
        self, app_name: str, instance_configs: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Assign instances to nodes using HA/Nodes Manager if available."""
        placements: list[dict[str, Any]] = []

        if self.ha_manager:
            available_nodes = self.ha_manager.get_available_nodes()
        elif self.server_lc_manager:
            available_nodes = self.server_lc_manager.get_available_nodes()
        else:
            available_nodes = [{"node_id": "local-node", "ip_address": "127.0.0.1"}]

        for i, inst_cfg in enumerate(instance_configs):
            node = available_nodes[i % len(available_nodes)] if available_nodes else {"node_id": "local-node"}
            placement = {
                "instance_id": inst_cfg.get("instance_id", f"{app_name}-{i}"),
                "app_name": app_name,
                "node_id": node.get("node_id", "local-node"),
                "node_ip": node.get("ip_address", "127.0.0.1"),
                "status": "running",
                "placed_at_ns": time.time_ns(),
            }
            placements.append(placement)

        return placements

    def _emit_event(
        self,
        phase: AppBootPhase,
        status: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        event = BootEvent(
            phase=phase.value,
            cycle="app",
            status=status,
            details=details or {},
        )
        self._boot_events.append(event)
