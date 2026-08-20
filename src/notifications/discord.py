"""Discord notifier using webhook transport with embed formatting."""

import json
import os
import ssl
from typing import Dict, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from .base import AlertLevel, BaseNotifier, NotificationEvent, NotificationMessage

_TIMEOUT_SECONDS = 15

_DISCORD_COLORS = {
    AlertLevel.CRITICAL: 0xD00000,
    AlertLevel.WARNING: 0xFFA000,
    AlertLevel.INFO: 0x1D9BD1,
    AlertLevel.SUCCESS: 0x2EB67D,
}


class DiscordNotifier(BaseNotifier):

    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.getenv("AURA_DISCORD_WEBHOOK_URL", "")

    def get_name(self) -> str:
        return "Discord"

    def is_configured(self) -> bool:
        return bool(self.webhook_url)

    def send(self, message: NotificationMessage) -> bool:
        if not self.is_configured():
            return False

        payload = {"embeds": [self.build_embed(message)]}
        return self._post(self.webhook_url, payload)

    def _post(self, url: str, payload: dict) -> bool:
        data = json.dumps(payload).encode("utf-8")
        req = Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        ctx = ssl.create_default_context()
        try:
            resp = urlopen(req, timeout=_TIMEOUT_SECONDS, context=ctx)
            return 200 <= resp.getcode() < 300
        except (URLError, OSError, TimeoutError, ssl.SSLError):
            return False

    def build_embed(self, message: NotificationMessage) -> Dict:
        embed = {
            "title": message.title,
            "color": _DISCORD_COLORS.get(message.level, 0x808080),
            "description": message.body[:2048],
            "timestamp": message.metadata.get("timestamp", ""),
        }

        fields = []
        fields.append({
            "name": "Cycle",
            "value": str(message.cycle),
            "inline": True,
        })
        fields.append({
            "name": "Classification",
            "value": message.classification,
            "inline": True,
        })
        fields.append({
            "name": "Level",
            "value": message.level.value.upper(),
            "inline": True,
        })

        if message.findings_count:
            summary_parts = []
            for sev, count in sorted(message.findings_count.items()):
                summary_parts.append("{}: {}".format(sev, count))
            fields.append({
                "name": "Open Findings",
                "value": " | ".join(summary_parts),
                "inline": False,
            })

        if message.metadata.get("overall_score") is not None:
            fields.append({
                "name": "Overall Score",
                "value": "{}/100".format(message.metadata["overall_score"]),
                "inline": True,
            })

        embed["fields"] = fields

        footer_text = "AURA Audit Engine v2.1.2"
        embed.setdefault("footer", {})["text"] = footer_text

        return embed