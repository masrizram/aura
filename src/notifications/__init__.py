"""AURA Notification & Alerting System.

Public API:
    BaseNotifier, AlertLevel, NotificationEvent, NotificationMessage,
    SlackNotifier, DiscordNotifier, EmailNotifier, WebhookNotifier,
    StatusBadgeGenerator, NotificationManager
"""

from .base import AlertLevel, BaseNotifier, NotificationEvent, NotificationMessage
from .slack import SlackNotifier
from .discord import DiscordNotifier
from .email import EmailNotifier
from .webhook import WebhookNotifier
from .status_badge import StatusBadgeGenerator
from .manager import NotificationManager

__all__ = [
    "AlertLevel",
    "BaseNotifier",
    "DiscordNotifier",
    "EmailNotifier",
    "NotificationEvent",
    "NotificationManager",
    "NotificationMessage",
    "SlackNotifier",
    "StatusBadgeGenerator",
    "WebhookNotifier",
]