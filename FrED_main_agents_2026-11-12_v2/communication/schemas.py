from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional
from datetime import datetime, timezone
import uuid
import time


class MessageType(Enum):
    OBSERVATION = "observation"
    COMMAND = "command"
    RESPONSE = "response"
    ALERT = "alert"
    STATUS = "status"
    REQUEST = "request"


class AgentState(Enum):
    INITIALIZED = "initialized"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


class MessagePriority(Enum):
    LOW = 1
    NORMAL = 5
    HIGH = 8
    CRITICAL = 10


@dataclass
class Message:
    sender: str
    receiver: str
    message_type: MessageType
    payload: Dict[str, Any]

    priority: int = MessagePriority.NORMAL.value

    message_id: str = field(
        default_factory=lambda: str(uuid.uuid4())
    )

    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    correlation_id: Optional[str] = None
    created_monotonic_ns: int = field(default_factory=time.perf_counter_ns, repr=False)
    trace_started_ns: Optional[int] = field(default=None, repr=False)

    def __post_init__(self):
        if self.trace_started_ns is None:
            self.trace_started_ns = self.created_monotonic_ns
