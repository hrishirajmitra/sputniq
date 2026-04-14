"""Request Dispatcher / HA Manager / Load Balancer.

Unified service handling:
  - Request routing to appropriate app instances
  - Round-robin and weighted load balancing
  - Node health monitoring and failover
  - Integration with the Gateway service
"""

from __future__ import annotations

import itertools
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class RequestDispatcher:
    """Routes external/internal requests through the Load Balancer
    to the correct application instances, interfacing with the
    HA/Nodes Manager for node selection.
    """

    def __init__(self, *, strategy: str = "round-robin") -> None:
        self.strategy = strategy
        self._app_instances: dict[str, list[dict[str, Any]]] = {}
        self._rr_iterators: dict[str, itertools.cycle] = {}
        self._node_health: dict[str, dict[str, Any]] = {}

    async def start(self, init_config: dict[str, Any] | None = None) -> "RequestDispatcher":
        logger.info("Request Dispatcher (strategy=%s) started", self.strategy)
        return self

    async def stop(self) -> None:
        logger.info("Request Dispatcher stopped")

    # ── Instance Registration ───────────────────────────────────────────

    def register_instances(self, app_name: str, instances: list[dict[str, Any]]) -> None:
        """Register application instances for load balancing."""
        self._app_instances[app_name] = instances
        self._rr_iterators[app_name] = itertools.cycle(instances)
        logger.info(
            "Registered %d instance(s) for app '%s'",
            len(instances),
            app_name,
        )

    def deregister_app(self, app_name: str) -> None:
        """Remove all instances for an application."""
        self._app_instances.pop(app_name, None)
        self._rr_iterators.pop(app_name, None)

    # ── Request Routing ─────────────────────────────────────────────────

    def dispatch(self, app_name: str, request: dict[str, Any]) -> dict[str, Any]:
        """Select a target instance for the given app using the LB strategy.

        Returns a routing envelope with the selected target and the
        original request payload.
        """
        instances = self._app_instances.get(app_name)
        if not instances:
            return {
                "status": "error",
                "error": f"No instances registered for app '{app_name}'",
            }

        target = self._select_target(app_name, instances)

        return {
            "status": "routed",
            "app_name": app_name,
            "target_instance": target.get("instance_id"),
            "target_node": target.get("node_id"),
            "target_ip": target.get("node_ip"),
            "request": request,
            "dispatched_at_ns": time.time_ns(),
        }

    def _select_target(self, app_name: str, instances: list[dict[str, Any]]) -> dict[str, Any]:
        """Select a target instance using the configured strategy."""
        if self.strategy == "round-robin":
            rr = self._rr_iterators.get(app_name)
            if rr:
                return next(rr)
            return instances[0]
        elif self.strategy == "weighted":
            # Weighted: pick the instance with fewest active connections
            # (simplified — in production this tracks connection counts)
            healthy = [i for i in instances if i.get("status") == "running"]
            return healthy[0] if healthy else instances[0]
        else:
            return instances[0]

    # ── HA / Node Management ────────────────────────────────────────────

    def update_node_health(self, node_id: str, healthy: bool) -> None:
        """Record node health for failover decisions."""
        self._node_health[node_id] = {
            "node_id": node_id,
            "healthy": healthy,
            "last_check_ns": time.time_ns(),
        }

        if not healthy:
            logger.warning("Node '%s' marked unhealthy — triggering failover", node_id)
            self._failover_node(node_id)

    def _failover_node(self, failed_node_id: str) -> None:
        """Remove instances on the failed node from active rotation."""
        for app_name, instances in self._app_instances.items():
            remaining = [i for i in instances if i.get("node_id") != failed_node_id]
            if len(remaining) < len(instances):
                logger.info(
                    "Failed-over %d instance(s) of '%s' away from node '%s'",
                    len(instances) - len(remaining),
                    app_name,
                    failed_node_id,
                )
                self._app_instances[app_name] = remaining
                self._rr_iterators[app_name] = itertools.cycle(remaining)

    def get_available_nodes(self) -> list[dict[str, Any]]:
        """Return nodes that are currently healthy."""
        return [
            info for info in self._node_health.values()
            if info.get("healthy", False)
        ]

    # ── Status ──────────────────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "registered_apps": len(self._app_instances),
            "total_instances": sum(len(v) for v in self._app_instances.values()),
            "healthy_nodes": len(self.get_available_nodes()),
            "apps": {
                app: len(instances) for app, instances in self._app_instances.items()
            },
        }
