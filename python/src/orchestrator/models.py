from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class ContainerState(Enum):
    UNKNOWN = "UNKNOWN"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    CHECKPOINTING = "CHECKPOINTING"
    PRE_DUMPED = "PRE_DUMPED"
    MIGRATING = "MIGRATING"
    RESTORING = "RESTORING"
    RESTORED = "RESTORED"
    FAILED = "FAILED"


class NodeStatus(Enum):
    UNKNOWN = "UNKNOWN"
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"


@dataclass
class Container:
    id: str
    name: str
    pod_id: str
    state: ContainerState
    image: str
    node_ip: str
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)


@dataclass
class Node:
    ip: str
    status: NodeStatus = NodeStatus.UNKNOWN
    containers: Dict[str, Container] = field(default_factory=dict)
    hostname: Optional[str] = None
    error_msg: Optional[str] = None


@dataclass
class MigrationJob:
    job_id: str
    container_id: str
    source_ip: str
    target_ip: str
    status: str  # "PENDING", "IN_PROGRESS", "COMPLETED", "FAILED"
    step: str = ""
    start_time: float = 0.0
    end_time: Optional[float] = None
    error_msg: Optional[str] = None
    is_interactive: bool = False
    interactive_iterations: list = field(default_factory=list)
    transferred_iterations: list = field(default_factory=list)
    pod_config_local_path: Optional[str] = None
    container_restore_local_path: Optional[str] = None
    dummy_checkpoint_tar: Optional[str] = None
    final_checkpoint_tar: Optional[str] = None
