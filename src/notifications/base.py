from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


class AlertLevel(Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"
    SUCCESS = "success"


class NotificationEvent(Enum):
    CRITICAL_FINDING = "critical_finding"
    NEW_P0_FINDING = "new_p0_finding"
    NEW_P1_FINDING = "new_p1_finding"
    CYCLE_COMPLETE = "cycle_complete"
    CONVERGENCE_ACHIEVED = "convergence_achieved"
    CONVERGENCE_LOST = "convergence_lost"
    STALL_WARNING = "stall_warning"
    MAX_CYCLES_REACHED = "max_cycles_reached"
    GATE_FLIP = "gate_flip"
    SCORE_CHANGE = "score_change"
    PROMOTION_REJECTED = "promotion_rejected"
    PUSH_COMPLETE = "push_complete"


@dataclass
class NotificationMessage:
    event: NotificationEvent
    level: AlertLevel
    title: str
    body: str
    cycle: int
    classification: str
    findings_count: Dict[str, int]
    metadata: Dict = field(default_factory=dict)


class BaseNotifier(ABC):

    @abstractmethod
    def send(self, message: NotificationMessage) -> bool:
        ...

    @abstractmethod
    def get_name(self) -> str:
        ...

    @abstractmethod
    def is_configured(self) -> bool:
        ...

    def format_message(self, message: NotificationMessage) -> str:
        parts = [
            "[{}] {}".format(message.cycle, message.title),
            "Level: {}".format(message.level.value.upper()),
            "Classification: {}".format(message.classification),
            "",
            message.body,
        ]
        return "\n".join(parts)