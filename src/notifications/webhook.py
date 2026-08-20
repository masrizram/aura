"""Generic webhook notifier for custom integrations (Zapier, etc.)."""

import json
import os
import ssl
from typing import Dict, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from .base import BaseNotifier, NotificationEvent, NotificationMessage

_TIMEOUT_SECONDS = 15


class WebhookNotifier(BaseNotifier):

    def __init__(self, url: Optional[str] = None, headers: Optional[Dict] = None):
        self.url = url or os.getenv("AURA_WEBHOOK_URL", "")
        self.headers = headers or {"Content-Type": "application/json"}

    def get_name(self) -> str:
        return "Webhook"

    def is_configured(self) -> bool:
        return bool(self.url)

    def send(self, message: NotificationMessage) -> bool:
        if not self.is_configured():
            return False

        payload = {
            "event": message.event.value,
            "level": message.level.value,
            "title": message.title,
            "body": message.body,
            "cycle": message.cycle,
            "classification": message.classification,
            "findings_count": message.findings_count,
            "metadata": message.metadata,
        }

        data = json.dumps(payload).encode("utf-8")
        req = Request(
            self.url,
            data=data,
            headers=self.headers,
            method="POST",
        )
        ctx = ssl.create_default_context()
        try:
            resp = urlopen(req, timeout=_TIMEOUT_SECONDS, context=ctx)
            return 200 <= resp.getcode() < 300
        except (URLError, OSError, TimeoutError, ssl.SSLError):
            return False