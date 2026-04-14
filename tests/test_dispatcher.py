"""Tests for Request Dispatcher / HA Manager / Load Balancer."""

import pytest

from sputniq.runtime.dispatcher import RequestDispatcher


@pytest.fixture
def dispatcher():
    return RequestDispatcher(strategy="round-robin")


@pytest.fixture
def populated_dispatcher(dispatcher):
    instances = [
        {"instance_id": "inst-0", "node_id": "node-0", "node_ip": "10.0.0.10", "status": "running"},
        {"instance_id": "inst-1", "node_id": "node-1", "node_ip": "10.0.0.11", "status": "running"},
        {"instance_id": "inst-2", "node_id": "node-2", "node_ip": "10.0.0.12", "status": "running"},
    ]
    dispatcher.register_instances("test-app", instances)
    return dispatcher


class TestRequestDispatcherInit:
    @pytest.mark.asyncio
    async def test_start(self, dispatcher):
        result = await dispatcher.start()
        assert result is dispatcher

    def test_default_strategy(self):
        rd = RequestDispatcher()
        assert rd.strategy == "round-robin"

    def test_custom_strategy(self):
        rd = RequestDispatcher(strategy="weighted")
        assert rd.strategy == "weighted"


class TestInstanceRegistration:
    def test_register_instances(self, dispatcher):
        instances = [{"instance_id": "inst-0"}, {"instance_id": "inst-1"}]
        dispatcher.register_instances("my-app", instances)
        status = dispatcher.status()
        assert status["registered_apps"] == 1
        assert status["total_instances"] == 2

    def test_deregister_app(self, populated_dispatcher):
        populated_dispatcher.deregister_app("test-app")
        status = populated_dispatcher.status()
        assert status["registered_apps"] == 0


class TestRoundRobinDispatch:
    def test_dispatch_success(self, populated_dispatcher):
        result = populated_dispatcher.dispatch("test-app", {"query": "test"})
        assert result["status"] == "routed"
        assert result["app_name"] == "test-app"
        assert result["target_instance"] is not None
        assert result["request"]["query"] == "test"

    def test_dispatch_round_robin(self, populated_dispatcher):
        targets = []
        for _ in range(6):
            result = populated_dispatcher.dispatch("test-app", {"query": "test"})
            targets.append(result["target_instance"])

        # Round-robin should cycle through all 3 instances twice
        assert targets[0] == targets[3]
        assert targets[1] == targets[4]
        assert targets[2] == targets[5]

    def test_dispatch_unknown_app(self, dispatcher):
        result = dispatcher.dispatch("unknown-app", {"query": "test"})
        assert result["status"] == "error"
        assert "No instances" in result["error"]


class TestWeightedDispatch:
    def test_weighted_dispatch(self):
        rd = RequestDispatcher(strategy="weighted")
        instances = [
            {"instance_id": "inst-0", "status": "running"},
            {"instance_id": "inst-1", "status": "running"},
        ]
        rd.register_instances("app", instances)
        result = rd.dispatch("app", {"q": "test"})
        assert result["status"] == "routed"


class TestHAFailover:
    def test_node_health_tracking(self, dispatcher):
        dispatcher.update_node_health("node-0", healthy=True)
        dispatcher.update_node_health("node-1", healthy=True)
        available = dispatcher.get_available_nodes()
        assert len(available) == 2

    def test_unhealthy_node_failover(self, populated_dispatcher):
        # Mark node-0 as unhealthy — instances on that node should be removed
        populated_dispatcher.update_node_health("node-0", healthy=False)

        status = populated_dispatcher.status()
        assert status["apps"]["test-app"] == 2  # 3 - 1 on failed node

    def test_dispatch_after_failover(self, populated_dispatcher):
        populated_dispatcher.update_node_health("node-0", healthy=False)
        result = populated_dispatcher.dispatch("test-app", {"q": "test"})
        assert result["status"] == "routed"
        assert result["target_instance"] != "inst-0"  # failed node's instance


class TestDispatcherStatus:
    def test_status_empty(self, dispatcher):
        status = dispatcher.status()
        assert status["registered_apps"] == 0
        assert status["total_instances"] == 0
        assert status["healthy_nodes"] == 0

    def test_status_populated(self, populated_dispatcher):
        populated_dispatcher.update_node_health("node-0", True)
        status = populated_dispatcher.status()
        assert status["registered_apps"] == 1
        assert status["total_instances"] == 3
        assert status["healthy_nodes"] == 1
