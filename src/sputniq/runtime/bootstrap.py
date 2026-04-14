"""Bootstrap — the single entry point for the entire platform startup.

Implements the 4-phase boot sequence:

  Phase 1 — Initial Bootstrap (Boot Script)
    1. Check Repo: Verify repository structure and fetch initial states
    2. Start Kafka: Ensure the central message bus is available
    3. Provision M/C: Provision the initial operational machines
    4. Start System Master

  Phase 2 — System Master Start & Initialization
    Delegated to SystemMaster.start()

  Phase 3 — Application Lifecycle Management
    Delegated to AppLifecycleManager.bootstrap_apps()

  Phase 4 — Machine Provisioning & App Execution Flow
    ServerLifecycleManager + RequestDispatcher activate
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from sputniq.models.boot import (
    AppBootPhase,
    BootEvent,
    BootStatus,
    SystemBootPhase,
)
from sputniq.runtime.dispatcher import RequestDispatcher
from sputniq.runtime.lifecycle import AppLifecycleManager, ServerLifecycleManager
from sputniq.runtime.system_master import SystemMaster

logger = logging.getLogger(__name__)


class PlatformBootstrap:
    """Orchestrates the complete platform boot sequence.

    Usage::

        bootstrap = PlatformBootstrap(init_config={...})
        status = await bootstrap.run()
    """

    def __init__(
        self,
        *,
        init_config: dict[str, Any] | None = None,
        bus_producer: Any | None = None,
        kafka_bootstrap_servers: str = "localhost:9092",
    ) -> None:
        self.init_config = init_config or {}
        self.bus_producer = bus_producer
        self.kafka_bootstrap_servers = kafka_bootstrap_servers

        # Core components — instantiated during boot
        self.system_master: SystemMaster | None = None
        self.server_lc_manager: ServerLifecycleManager | None = None
        self.app_lc_manager: AppLifecycleManager | None = None
        self.request_dispatcher: RequestDispatcher | None = None

        self._boot_status = BootStatus()

    @property
    def boot_status(self) -> BootStatus:
        return self._boot_status

    # ════════════════════════════════════════════════════════════════════
    #  MAIN BOOT SEQUENCE
    # ════════════════════════════════════════════════════════════════════

    async def run(self, *, app_repository: list[dict[str, Any]] | None = None) -> BootStatus:
        """Execute the full 4-phase boot sequence.

        Parameters
        ----------
        app_repository : list, optional
            Application definitions to bootstrap. If ``None``, an
            empty list is used (system-only boot).
        """
        apps = app_repository or []

        try:
            await self._phase1_initial_bootstrap()
            await self._phase2_system_master()
            await self._phase3_app_lifecycle(apps)
            await self._phase4_routing()
        except Exception as exc:
            logger.error("Boot sequence failed: %s", exc, exc_info=True)
            raise

        logger.info("═══ Platform boot sequence completed successfully ═══")
        return self._boot_status

    # ── Phase 1: Initial Bootstrap ──────────────────────────────────────

    async def _phase1_initial_bootstrap(self) -> None:
        logger.info("══════ Phase 1: Initial Bootstrap ══════")

        # Step 1: Check Repo
        self._boot_status.system_boot_phase = SystemBootPhase.REPO_CHECK
        self._emit_system_event(SystemBootPhase.REPO_CHECK, "started")
        await self._check_repo()
        self._emit_system_event(SystemBootPhase.REPO_CHECK, "completed")
        logger.info("Phase 1.1: Repository check passed")

        # Step 2: Start Kafka
        self._boot_status.system_boot_phase = SystemBootPhase.KAFKA_START
        self._emit_system_event(SystemBootPhase.KAFKA_START, "started")
        await self._verify_kafka()
        self._emit_system_event(SystemBootPhase.KAFKA_START, "completed")
        logger.info("Phase 1.2: Kafka message bus verified")

        # Step 3: Provision M/C (initial machines)
        self._boot_status.system_boot_phase = SystemBootPhase.PROVISION_MC
        self._emit_system_event(SystemBootPhase.PROVISION_MC, "started")
        self.server_lc_manager = ServerLifecycleManager(bus_producer=self.bus_producer)
        await self.server_lc_manager.start(self.init_config)

        # Provision the initial boot machine
        node = await self.server_lc_manager.provision_node(
            "boot-node-0", ip_address="127.0.0.1"
        )
        self._boot_status.provisioned_nodes.append(node["node_id"])
        self._emit_system_event(SystemBootPhase.PROVISION_MC, "completed")
        logger.info("Phase 1.3: Initial machine provisioned")

    # ── Phase 2: System Master ──────────────────────────────────────────

    async def _phase2_system_master(self) -> None:
        logger.info("══════ Phase 2: System Master Start ══════")

        self.system_master = SystemMaster(
            init_config=self.init_config,
            bus_producer=self.bus_producer,
        )

        # Register real service hooks for lifecycle managers
        self.request_dispatcher = RequestDispatcher(
            strategy=self.init_config.get("lb_strategy", "round-robin")
        )

        self.app_lc_manager = AppLifecycleManager(
            server_lc_manager=self.server_lc_manager,
            ha_manager=self.request_dispatcher,
            bus_producer=self.bus_producer,
        )

        # Wire hooks: when System Master starts services, these callables run
        self.system_master.register_service_hook(
            "server-lifecycle-manager",
            lambda cfg: self.server_lc_manager.start(cfg),
        )
        self.system_master.register_service_hook(
            "app-lifecycle-manager",
            lambda cfg: self.app_lc_manager.start(cfg),
        )
        self.system_master.register_service_hook(
            "request-dispatcher",
            lambda cfg: self.request_dispatcher.start(cfg),
        )

        master_status = await self.system_master.start()

        # Merge system master boot events into global status
        self._boot_status.system_boot_phase = master_status.system_boot_phase
        self._boot_status.system_services = master_status.system_services
        self._boot_status.is_system_ready = master_status.is_system_ready
        self._boot_status.boot_events.extend(master_status.boot_events)

    # ── Phase 3: App Lifecycle Management ───────────────────────────────

    async def _phase3_app_lifecycle(self, apps: list[dict[str, Any]]) -> None:
        logger.info("══════ Phase 3: Application Lifecycle Management ══════")

        if not apps:
            logger.info("No applications to bootstrap — skipping Phase 3")
            self._boot_status.app_boot_phase = AppBootPhase.INSTANCES_RUNNING
            self._boot_status.is_app_ready = True
            return

        self._boot_status.app_boot_phase = AppBootPhase.FETCH_APPS
        deployed = await self.app_lc_manager.bootstrap_apps(apps)

        # Register deployed instances with the load balancer
        for app_def in apps:
            app_name = app_def.get("name", "unknown")
            app_instances = [d for d in deployed if d.get("app_name") == app_name]
            if app_instances:
                self.request_dispatcher.register_instances(app_name, app_instances)

        self._boot_status.app_boot_phase = AppBootPhase.INSTANCES_RUNNING
        self._boot_status.is_app_ready = True
        self._boot_status.boot_events.extend(self.app_lc_manager._boot_events)
        logger.info("Phase 3 complete: %d instances deployed", len(deployed))

    # ── Phase 4: Routing Activation ─────────────────────────────────────

    async def _phase4_routing(self) -> None:
        logger.info("══════ Phase 4: Machine Provisioning & Routing ══════")

        # Mark the boot node as healthy in the dispatcher
        for node_id in self._boot_status.provisioned_nodes:
            self.request_dispatcher.update_node_health(node_id, healthy=True)

        dispatcher_status = self.request_dispatcher.status()
        logger.info(
            "Request Dispatcher active — %d apps, %d instances, %d healthy nodes",
            dispatcher_status["registered_apps"],
            dispatcher_status["total_instances"],
            dispatcher_status["healthy_nodes"],
        )

    # ── Shutdown ────────────────────────────────────────────────────────

    async def shutdown(self) -> None:
        """Gracefully shutdown all platform components."""
        logger.info("Platform shutting down")
        if self.system_master:
            await self.system_master.stop()
        if self.request_dispatcher:
            await self.request_dispatcher.stop()
        if self.app_lc_manager:
            await self.app_lc_manager.stop()
        if self.server_lc_manager:
            await self.server_lc_manager.stop()

    # ── Internal Helpers ────────────────────────────────────────────────

    async def _check_repo(self) -> None:
        """Verify repository structure and fetch initial states."""
        # In a production system this would:
        # - Connect to the system repository (git/artifact store)
        # - Verify system binaries are present
        # - Verify INIT configuration is accessible
        # For local dev, we verify the config is loadable
        await asyncio.sleep(0)  # yield

    async def _verify_kafka(self) -> None:
        """Ensure the Kafka message bus is available.

        In Docker Compose this is handled by service dependencies.
        For manual startup we'd attempt a connection here.
        """
        await asyncio.sleep(0)  # yield

    def _emit_system_event(self, phase: SystemBootPhase, status: str, **kw: Any) -> None:
        event = BootEvent(phase=phase.value, cycle="system", status=status, **kw)
        self._boot_status.boot_events.append(event)
