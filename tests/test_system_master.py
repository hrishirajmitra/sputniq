"""Tests for SystemMaster."""

import pytest

from sputniq.models.boot import SystemBootPhase
from sputniq.runtime.system_master import SYSTEM_SERVICES, SystemMaster


@pytest.fixture
def system_master():
    return SystemMaster(init_config={"lb_strategy": "round-robin"})


class TestSystemMasterInit:
    def test_default_init(self):
        sm = SystemMaster()
        assert sm.init_config == {}
        assert sm.bus_producer is None
        assert not sm.is_ready

    def test_custom_init(self, system_master):
        assert system_master.init_config["lb_strategy"] == "round-robin"
        assert not system_master.is_ready


class TestSystemMasterStart:
    @pytest.mark.asyncio
    async def test_start_sequence(self, system_master):
        status = await system_master.start()

        # All system services should be running
        assert status.is_system_ready is True
        assert status.system_boot_phase == SystemBootPhase.SYSTEM_SERVICES_READY
        assert len(status.system_services) == len(SYSTEM_SERVICES)

        for svc in status.system_services:
            assert svc.status == "running"
            assert svc.started_at_ns is not None

    @pytest.mark.asyncio
    async def test_start_emits_events(self, system_master):
        status = await system_master.start()

        assert len(status.boot_events) >= 3
        phases = [e.phase for e in status.boot_events]
        assert "system_master_start" in phases
        assert "system_services_starting" in phases
        assert "system_services_ready" in phases

    @pytest.mark.asyncio
    async def test_is_ready_after_start(self, system_master):
        assert not system_master.is_ready
        await system_master.start()
        assert system_master.is_ready


class TestSystemMasterHooks:
    @pytest.mark.asyncio
    async def test_custom_hook_called(self):
        sm = SystemMaster()
        hook_called = False

        async def custom_hook(config):
            nonlocal hook_called
            hook_called = True
            return {"custom": True}

        sm.register_service_hook("server-lifecycle-manager", custom_hook)
        await sm.start()

        assert hook_called

    @pytest.mark.asyncio
    async def test_failing_hook_stops_sequence(self):
        sm = SystemMaster()

        async def failing_hook(config):
            raise RuntimeError("Service failed to start")

        sm.register_service_hook("server-lifecycle-manager", failing_hook)

        with pytest.raises(RuntimeError, match="Service failed to start"):
            await sm.start()

        # System should NOT be ready
        assert not sm.is_ready


class TestSystemMasterHealth:
    @pytest.mark.asyncio
    async def test_health_before_start(self, system_master):
        health = system_master.health()
        assert health["system_master"] == "not_ready"

    @pytest.mark.asyncio
    async def test_health_after_start(self, system_master):
        await system_master.start()
        health = system_master.health()
        assert health["system_master"] == "running"
        assert health["system_boot_phase"] == "system_services_ready"
        assert len(health["services"]) == len(SYSTEM_SERVICES)


class TestSystemMasterStop:
    @pytest.mark.asyncio
    async def test_stop_marks_not_ready(self, system_master):
        await system_master.start()
        assert system_master.is_ready

        await system_master.stop()
        assert not system_master.is_ready

        for svc in system_master.boot_status.system_services:
            assert svc.status == "stopped"
