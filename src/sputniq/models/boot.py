"""Boot cycle definitions — System Boot and App Boot phases."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from sputniq.models.messages import _nano_ts, _uuid


# ── System Boot Cycle Phases ────────────────────────────────────────────────


class SystemBootPhase(str, Enum):
    """Phases of the system (infrastructure) boot cycle."""

    REPO_CHECK = "repo_check"
    KAFKA_START = "kafka_start"
    PROVISION_MC = "provision_mc"
    SYSTEM_MASTER_START = "system_master_start"
    SYSTEM_SERVICES_STARTING = "system_services_starting"
    SYSTEM_SERVICES_READY = "system_services_ready"


# ── App Boot Cycle Phases ───────────────────────────────────────────────────


class AppBootPhase(str, Enum):
    """Phases of the application bootstrap cycle."""

    FETCH_APPS = "fetch_apps"
    READ_CONFIG = "read_config"
    LOAD_CONFIG = "load_config"
    PLACE_INSTANCES = "place_instances"
    INSTANCES_RUNNING = "instances_running"


# ── Boot Events ─────────────────────────────────────────────────────────────


class BootEvent(BaseModel):
    """A single event emitted during the boot sequence."""

    event_id: str = Field(default_factory=_uuid)
    phase: str = Field(..., description="Current boot phase identifier")
    cycle: str = Field(..., description="'system' or 'app'")
    status: str = Field(default="started", description="started | completed | failed")
    timestamp_ns: int = Field(default_factory=_nano_ts)
    details: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


# ── Boot Status Snapshot ────────────────────────────────────────────────────


class SystemServiceStatus(BaseModel):
    """Status of a single system service managed by the System Master."""

    service_name: str
    status: str = "stopped"  # stopped | starting | running | failed
    started_at_ns: int | None = None
    error: str | None = None


class BootStatus(BaseModel):
    """Aggregate snapshot of the current boot state."""

    system_boot_phase: SystemBootPhase = SystemBootPhase.REPO_CHECK
    app_boot_phase: AppBootPhase | None = None
    system_services: list[SystemServiceStatus] = Field(default_factory=list)
    boot_events: list[BootEvent] = Field(default_factory=list)
    is_system_ready: bool = False
    is_app_ready: bool = False
    provisioned_nodes: list[str] = Field(default_factory=list)
