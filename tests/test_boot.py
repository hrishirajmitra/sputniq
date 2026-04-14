"""Tests for boot cycle models."""

import pytest

from sputniq.models.boot import (
    AppBootPhase,
    BootEvent,
    BootStatus,
    SystemBootPhase,
    SystemServiceStatus,
)


class TestSystemBootPhase:
    def test_all_phases_defined(self):
        phases = list(SystemBootPhase)
        assert len(phases) == 6
        assert SystemBootPhase.REPO_CHECK in phases
        assert SystemBootPhase.KAFKA_START in phases
        assert SystemBootPhase.PROVISION_MC in phases
        assert SystemBootPhase.SYSTEM_MASTER_START in phases
        assert SystemBootPhase.SYSTEM_SERVICES_STARTING in phases
        assert SystemBootPhase.SYSTEM_SERVICES_READY in phases

    def test_phase_values(self):
        assert SystemBootPhase.REPO_CHECK.value == "repo_check"
        assert SystemBootPhase.KAFKA_START.value == "kafka_start"
        assert SystemBootPhase.SYSTEM_SERVICES_READY.value == "system_services_ready"


class TestAppBootPhase:
    def test_all_phases_defined(self):
        phases = list(AppBootPhase)
        assert len(phases) == 5
        assert AppBootPhase.FETCH_APPS in phases
        assert AppBootPhase.LOAD_CONFIG in phases
        assert AppBootPhase.PLACE_INSTANCES in phases
        assert AppBootPhase.INSTANCES_RUNNING in phases


class TestBootEvent:
    def test_creation_defaults(self):
        event = BootEvent(phase="repo_check", cycle="system")
        assert event.phase == "repo_check"
        assert event.cycle == "system"
        assert event.status == "started"
        assert event.event_id  # auto-generated UUID
        assert event.timestamp_ns > 0
        assert event.details == {}
        assert event.error is None

    def test_creation_with_details(self):
        event = BootEvent(
            phase="kafka_start",
            cycle="system",
            status="completed",
            details={"server": "localhost:9092"},
        )
        assert event.status == "completed"
        assert event.details["server"] == "localhost:9092"

    def test_creation_with_error(self):
        event = BootEvent(
            phase="provision_mc",
            cycle="system",
            status="failed",
            error="Connection refused",
        )
        assert event.status == "failed"
        assert event.error == "Connection refused"


class TestSystemServiceStatus:
    def test_defaults(self):
        svc = SystemServiceStatus(service_name="test-service")
        assert svc.service_name == "test-service"
        assert svc.status == "stopped"
        assert svc.started_at_ns is None
        assert svc.error is None

    def test_running_service(self):
        svc = SystemServiceStatus(
            service_name="server-lifecycle-manager",
            status="running",
            started_at_ns=1234567890,
        )
        assert svc.status == "running"


class TestBootStatus:
    def test_defaults(self):
        status = BootStatus()
        assert status.system_boot_phase == SystemBootPhase.REPO_CHECK
        assert status.app_boot_phase is None
        assert status.system_services == []
        assert status.boot_events == []
        assert status.is_system_ready is False
        assert status.is_app_ready is False
        assert status.provisioned_nodes == []

    def test_with_services(self):
        status = BootStatus(
            system_services=[
                SystemServiceStatus(service_name="svc-1", status="running"),
                SystemServiceStatus(service_name="svc-2", status="starting"),
            ],
            is_system_ready=True,
        )
        assert len(status.system_services) == 2
        assert status.is_system_ready is True

    def test_serialization(self):
        status = BootStatus(provisioned_nodes=["node-0", "node-1"])
        data = status.model_dump()
        assert data["provisioned_nodes"] == ["node-0", "node-1"]
        assert data["system_boot_phase"] == "repo_check"
