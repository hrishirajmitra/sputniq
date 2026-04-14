"""System Master — Phase 2 of the boot sequence.

Reads the System INIT config and launches all required core system services:
  1. Server Lifecycle Manager
  2. App Lifecycle Manager
  3. Security Service
  4. Logging Service
  5. Deployment Manager
  6. Request Dispatcher / HA Manager / Load Balancer

All services communicate via the centralized Kafka message bus.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

from sputniq.models.boot import (
    AppBootPhase,
    BootEvent,
    BootStatus,
    SystemBootPhase,
    SystemServiceStatus,
)

logger = logging.getLogger(__name__)

# ── System Service Descriptors ──────────────────────────────────────────────

SYSTEM_SERVICES = [
    "server-lifecycle-manager",
    "app-lifecycle-manager",
    "security-service",
    "logging-service",
    "deployment-manager",
    "request-dispatcher",
]


class SystemMaster:
    """Core control plane process.

    The System Master is started by the boot script (Phase 1) and drives
    Phase 2 of the platform boot sequence.  It reads the System INIT
    configuration and launches every core system service in order.
    """

    def __init__(
        self,
        *,
        init_config: dict[str, Any] | None = None,
        bus_producer: Any | None = None,
    ) -> None:
        self.init_config = init_config or {}
        self.bus_producer = bus_producer
        self._boot_status = BootStatus()
        self._service_instances: dict[str, Any] = {}
        self._service_start_hooks: dict[str, Callable] = {}

    # ── Public properties ───────────────────────────────────────────────

    @property
    def boot_status(self) -> BootStatus:
        return self._boot_status

    @property
    def is_ready(self) -> bool:
        return self._boot_status.is_system_ready

    # ── Hook Registration ───────────────────────────────────────────────

    def register_service_hook(self, service_name: str, hook: Callable) -> None:
        """Register an async callable that starts a service.

        In production every service is a separate container.  For local
        development the hooks spin up in-process tasks.
        """
        self._service_start_hooks[service_name] = hook

    # ── Phase 2: Start Sequence ─────────────────────────────────────────

    async def start(self) -> BootStatus:
        """Execute the System Master start sequence (Phase 2).

        1. Update boot phase to SYSTEM_MASTER_START
        2. Iterate through SYSTEM_SERVICES and launch each one
        3. Mark system ready when all services are running
        """
        logger.info("System Master starting — reading INIT config")
        self._emit_event(SystemBootPhase.SYSTEM_MASTER_START, "started")
        self._boot_status.system_boot_phase = SystemBootPhase.SYSTEM_MASTER_START

        # ── Launch system services sequentially ─────────────────────────
        self._boot_status.system_boot_phase = SystemBootPhase.SYSTEM_SERVICES_STARTING
        self._emit_event(SystemBootPhase.SYSTEM_SERVICES_STARTING, "started")

        for service_name in SYSTEM_SERVICES:
            svc_status = SystemServiceStatus(service_name=service_name, status="starting")
            self._boot_status.system_services.append(svc_status)

            try:
                await self._start_service(service_name, svc_status)
                svc_status.status = "running"
                svc_status.started_at_ns = time.time_ns()
                logger.info("System service '%s' is running", service_name)
            except Exception as exc:
                svc_status.status = "failed"
                svc_status.error = str(exc)
                logger.error("Failed to start system service '%s': %s", service_name, exc)
                self._emit_event(
                    SystemBootPhase.SYSTEM_SERVICES_STARTING,
                    "failed",
                    details={"service": service_name, "error": str(exc)},
                )
                raise

        # ── All services started ────────────────────────────────────────
        self._boot_status.system_boot_phase = SystemBootPhase.SYSTEM_SERVICES_READY
        self._boot_status.is_system_ready = True
        self._emit_event(SystemBootPhase.SYSTEM_SERVICES_READY, "completed")
        logger.info("System Master — all system services are ready")

        return self._boot_status

    async def stop(self) -> None:
        """Gracefully stop all system services."""
        logger.info("System Master shutting down")
        for service_name in reversed(SYSTEM_SERVICES):
            instance = self._service_instances.get(service_name)
            if instance and hasattr(instance, "stop"):
                try:
                    await instance.stop()
                    logger.info("Stopped system service '%s'", service_name)
                except Exception as exc:
                    logger.warning("Error stopping '%s': %s", service_name, exc)

        self._boot_status.is_system_ready = False
        for svc in self._boot_status.system_services:
            svc.status = "stopped"

    # ── Health ──────────────────────────────────────────────────────────

    def health(self) -> dict[str, Any]:
        """Return aggregated health across all managed system services."""
        services = {
            svc.service_name: svc.status
            for svc in self._boot_status.system_services
        }
        return {
            "system_master": "running" if self.is_ready else "not_ready",
            "system_boot_phase": self._boot_status.system_boot_phase.value,
            "services": services,
        }

    # ── Internals ───────────────────────────────────────────────────────

    async def _start_service(self, service_name: str, svc_status: SystemServiceStatus) -> None:
        hook = self._service_start_hooks.get(service_name)
        if hook:
            instance = await hook(self.init_config)
            self._service_instances[service_name] = instance
        else:
            # Default stub: simulate service readiness
            logger.info("No hook for '%s' — using default stub", service_name)
            await asyncio.sleep(0)  # yield to event loop
            self._service_instances[service_name] = {"stub": True}

    def _emit_event(
        self,
        phase: SystemBootPhase,
        status: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        event = BootEvent(
            phase=phase.value,
            cycle="system",
            status=status,
            details=details or {},
        )
        self._boot_status.boot_events.append(event)

        if self.bus_producer:
            # Fire-and-forget publish (non-blocking)
            try:
                asyncio.get_event_loop().create_task(
                    self.bus_producer.publish("sputniq.boot.events", event.model_dump())
                )
            except RuntimeError:
                pass  # no running loop yet — safe to skip
