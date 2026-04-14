"""Tests for Server Lifecycle Manager and App Lifecycle Manager."""

import pytest

from sputniq.runtime.lifecycle import AppLifecycleManager, ServerLifecycleManager


# ═══════════════════════════════════════════════════════════════════════════
#  Server Lifecycle Manager
# ═══════════════════════════════════════════════════════════════════════════


class TestServerLifecycleManager:
    @pytest.fixture
    def slc(self):
        return ServerLifecycleManager()

    @pytest.mark.asyncio
    async def test_start(self, slc):
        result = await slc.start()
        assert result is slc

    @pytest.mark.asyncio
    async def test_provision_node(self, slc):
        node = await slc.provision_node("node-1", ip_address="10.0.0.11")
        assert node["node_id"] == "node-1"
        assert node["ip_address"] == "10.0.0.11"
        assert node["status"] == "ready"
        assert node["repo_connected"] is True
        assert node["agent_running"] is True

    @pytest.mark.asyncio
    async def test_provision_auto_ip(self, slc):
        node = await slc.provision_node("node-auto")
        assert node["ip_address"] == "10.0.0.10"

    @pytest.mark.asyncio
    async def test_provision_multiple_nodes(self, slc):
        n1 = await slc.provision_node("node-1")
        n2 = await slc.provision_node("node-2")
        assert n1["ip_address"] != n2["ip_address"]

    @pytest.mark.asyncio
    async def test_list_nodes(self, slc):
        await slc.provision_node("node-1")
        await slc.provision_node("node-2")
        nodes = slc.list_nodes()
        assert len(nodes) == 2

    @pytest.mark.asyncio
    async def test_get_available_nodes(self, slc):
        await slc.provision_node("node-1")
        await slc.provision_node("node-2")
        available = slc.get_available_nodes()
        assert len(available) == 2

    @pytest.mark.asyncio
    async def test_decommission_node(self, slc):
        await slc.provision_node("node-1")
        await slc.decommission_node("node-1")
        available = slc.get_available_nodes()
        assert len(available) == 0

    @pytest.mark.asyncio
    async def test_health_check(self, slc):
        await slc.provision_node("node-1")
        health = await slc.health_check("node-1")
        assert health["status"] == "ready"
        assert health["node_id"] == "node-1"

    @pytest.mark.asyncio
    async def test_health_check_unknown(self, slc):
        health = await slc.health_check("nonexistent")
        assert health["status"] == "unknown"


# ═══════════════════════════════════════════════════════════════════════════
#  App Lifecycle Manager
# ═══════════════════════════════════════════════════════════════════════════


class TestAppLifecycleManager:
    @pytest.fixture
    def slc(self):
        return ServerLifecycleManager()

    @pytest.fixture
    def alc(self, slc):
        return AppLifecycleManager(server_lc_manager=slc)

    @pytest.mark.asyncio
    async def test_start(self, alc):
        result = await alc.start()
        assert result is alc

    @pytest.mark.asyncio
    async def test_bootstrap_empty(self, alc):
        deployed = await alc.bootstrap_apps([])
        assert deployed == []

    @pytest.mark.asyncio
    async def test_bootstrap_single_app(self, alc, slc):
        await slc.provision_node("node-1")
        apps = [{"name": "test-app", "config_path": "config.json"}]
        deployed = await alc.bootstrap_apps(apps)
        assert len(deployed) == 1
        assert deployed[0]["app_name"] == "test-app"
        assert deployed[0]["status"] == "running"

    @pytest.mark.asyncio
    async def test_bootstrap_with_instances(self, alc, slc):
        await slc.provision_node("node-1")
        apps = [
            {
                "name": "multi-app",
                "instances": [
                    {"instance_id": "inst-0"},
                    {"instance_id": "inst-1"},
                    {"instance_id": "inst-2"},
                ],
            }
        ]
        deployed = await alc.bootstrap_apps(apps)
        assert len(deployed) == 3
        ids = [d["instance_id"] for d in deployed]
        assert "inst-0" in ids
        assert "inst-1" in ids
        assert "inst-2" in ids

    @pytest.mark.asyncio
    async def test_bootstrap_ldap_stub(self, alc, slc):
        await slc.provision_node("node-1")
        apps = [
            {
                "name": "ldap-app",
                "instances": [{"instance_id": "inst-0", "ldap_group": "cn=admins"}],
            }
        ]
        deployed = await alc.bootstrap_apps(apps)
        assert len(deployed) == 1

    @pytest.mark.asyncio
    async def test_list_apps(self, alc, slc):
        await slc.provision_node("node-1")
        await alc.bootstrap_apps([{"name": "app-1"}, {"name": "app-2"}])
        apps = alc.list_apps()
        assert len(apps) == 2
        names = [a["name"] for a in apps]
        assert "app-1" in names
        assert "app-2" in names

    @pytest.mark.asyncio
    async def test_get_app_status(self, alc, slc):
        await slc.provision_node("node-1")
        await alc.bootstrap_apps([{"name": "test-app"}])
        status = await alc.get_app_status("test-app")
        assert status["status"] == "running"

    @pytest.mark.asyncio
    async def test_get_app_status_not_found(self, alc):
        status = await alc.get_app_status("nonexistent")
        assert status["status"] == "not_found"
