"""Tests for the full platform bootstrap sequence."""

import pytest

from sputniq.models.boot import AppBootPhase, SystemBootPhase
from sputniq.runtime.bootstrap import PlatformBootstrap


@pytest.fixture
def bootstrap():
    return PlatformBootstrap(init_config={"lb_strategy": "round-robin", "initial_nodes": 1})


class TestBootstrapSystemOnly:
    @pytest.mark.asyncio
    async def test_system_only_boot(self, bootstrap):
        """Boot with no applications — only system services start."""
        status = await bootstrap.run(app_repository=[])

        assert status.is_system_ready is True
        assert status.is_app_ready is True  # vacuously true when no apps
        assert status.system_boot_phase == SystemBootPhase.SYSTEM_SERVICES_READY
        assert len(status.provisioned_nodes) >= 1

    @pytest.mark.asyncio
    async def test_system_services_launched(self, bootstrap):
        status = await bootstrap.run()
        assert len(status.system_services) == 6

        service_names = [s.service_name for s in status.system_services]
        assert "server-lifecycle-manager" in service_names
        assert "app-lifecycle-manager" in service_names
        assert "security-service" in service_names
        assert "logging-service" in service_names
        assert "deployment-manager" in service_names
        assert "request-dispatcher" in service_names

    @pytest.mark.asyncio
    async def test_boot_events_emitted(self, bootstrap):
        status = await bootstrap.run()

        # Should have events from Phase 1 and Phase 2
        assert len(status.boot_events) > 0
        phases = [e.phase for e in status.boot_events]
        assert "repo_check" in phases
        assert "kafka_start" in phases
        assert "provision_mc" in phases


class TestBootstrapWithApps:
    @pytest.mark.asyncio
    async def test_single_app_bootstrap(self, bootstrap):
        apps = [{"name": "test-app", "config_path": "config.json"}]
        status = await bootstrap.run(app_repository=apps)

        assert status.is_system_ready is True
        assert status.is_app_ready is True
        assert status.app_boot_phase == AppBootPhase.INSTANCES_RUNNING

    @pytest.mark.asyncio
    async def test_multi_app_bootstrap(self, bootstrap):
        apps = [
            {"name": "app-1"},
            {"name": "app-2"},
            {"name": "app-3"},
        ]
        status = await bootstrap.run(app_repository=apps)

        assert status.is_app_ready is True

    @pytest.mark.asyncio
    async def test_app_with_instances(self, bootstrap):
        apps = [
            {
                "name": "replicated-app",
                "instances": [
                    {"instance_id": "rep-0"},
                    {"instance_id": "rep-1"},
                ],
            }
        ]
        status = await bootstrap.run(app_repository=apps)
        assert status.is_app_ready is True


class TestBootstrapComponents:
    @pytest.mark.asyncio
    async def test_system_master_created(self, bootstrap):
        await bootstrap.run()
        assert bootstrap.system_master is not None
        assert bootstrap.system_master.is_ready

    @pytest.mark.asyncio
    async def test_server_lc_manager_created(self, bootstrap):
        await bootstrap.run()
        assert bootstrap.server_lc_manager is not None
        nodes = bootstrap.server_lc_manager.list_nodes()
        assert len(nodes) >= 1

    @pytest.mark.asyncio
    async def test_app_lc_manager_created(self, bootstrap):
        await bootstrap.run()
        assert bootstrap.app_lc_manager is not None

    @pytest.mark.asyncio
    async def test_request_dispatcher_created(self, bootstrap):
        apps = [{"name": "test-app"}]
        await bootstrap.run(app_repository=apps)
        assert bootstrap.request_dispatcher is not None

        status = bootstrap.request_dispatcher.status()
        assert status["registered_apps"] == 1


class TestBootstrapShutdown:
    @pytest.mark.asyncio
    async def test_shutdown(self, bootstrap):
        await bootstrap.run()
        assert bootstrap.system_master.is_ready

        await bootstrap.shutdown()
        assert not bootstrap.system_master.is_ready


class TestBootstrapEndToEnd:
    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        """Test complete: boot → verify → dispatch → shutdown."""
        bs = PlatformBootstrap(init_config={"lb_strategy": "round-robin"})

        # Boot with an app
        apps = [{"name": "e2e-app", "instances": [{"instance_id": "e2e-0"}, {"instance_id": "e2e-1"}]}]
        status = await bs.run(app_repository=apps)

        # Verify system is ready
        assert status.is_system_ready
        assert status.is_app_ready

        # Verify routing works
        result = bs.request_dispatcher.dispatch("e2e-app", {"query": "hello"})
        assert result["status"] == "routed"
        assert result["app_name"] == "e2e-app"

        # Shutdown
        await bs.shutdown()
        assert not bs.system_master.is_ready
