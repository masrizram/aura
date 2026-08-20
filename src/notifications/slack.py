"""Slack notifier supporting webhook and bot token transport."""

import json
import os
import ssl
from typing import Dict, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from .base import AlertLevel, BaseNotifier, NotificationEvent, NotificationMessage

_TIMEOUT_SECONDS = 15

_LEVEL_COLOR = {
    AlertLevel.CRITICAL: "#D00000",
    AlertLevel.WARNING: "#FFA000",
    AlertLevel.INFO: "#1D9BD1",
    AlertLevel.SUCCESS: "#2EB67D",
}


class SlackNotifier(BaseNotifier):

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        bot_token: Optional[str] = None,
        channel: Optional[str] = None,
    ):
        self.webhook_url = webhook_url or os.getenv("AURA_SLACK_WEBHOOK_URL", "")
        self.bot_token = bot_token or os.getenv("AURA_SLACK_BOT_TOKEN", "")
        self.channel = channel or os.getenv("AURA_SLACK_CHANNEL", "#aura-audit")

    def get_name(self) -> str:
        return "Slack"

    def is_configured(self) -> bool:
        return bool(self.webhook_url or (self.bot_token and self.channel))

    def send(self, message: NotificationMessage) -> bool:
        if not self.is_configured():
            return False

        payload = {"text": message.title, "blocks": self.format_blocks(message)}
        if self.channel and not self.channel.startswith("#"):
            payload["channel"] = self.channel

        if self.webhook_url:
            return self._send_webhook(self.webhook_url, payload)
        return False

    def _send_webhook(self, url: str, payload: dict) -> bool:
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

    def format_blocks(self, message: NotificationMessage) -> List[Dict]:
        blocks = []

        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": message.title,
                "emoji": True,
            },
        })

        blocks.append({"type": "divider"})

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": self._build_section_text(message),
            },
        })

        if message.findings_count:
            blocks.append({
                "type": "section",
                "fields": self._build_finding_fields(message),
            })

        if message.metadata.get("gate_status"):
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "```{}```".format(
                        json.dumps(message.metadata["gate_status"], indent=2)
                    ),
                },
            })

        blocks.append({"type": "divider"})

        ctx_text = "Cycle {} | Classification: {}".format(
            message.cycle, message.classification
        )
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": ctx_text}],
        })

        return blocks

    def _build_section_text(self, message: NotificationMessage) -> str:
        indicator = {
            AlertLevel.CRITICAL: ":red_circle:",
            AlertLevel.WARNING: ":warning:",
            AlertLevel.INFO: ":information_source:",
            AlertLevel.SUCCESS: ":white_check_mark:",
        }.get(message.level, ":bell:")

        text = "{} *{}* - Cycle {} (`{}`)\n{}".format(
            indicator,
            message.event.value.replace("_", " ").title(),
            message.cycle,
            message.classification,
            message.body,
        )
        if len(text) > 2900:
            text = text[:2896] + "..."
        return text

    def _build_finding_fields(self, message: NotificationMessage) -> List[Dict]:
        fields = []
        for sev, count in sorted(message.findings_count.items()):
            fields.append({
                "type": "mrkdwn",
                "text": "*{}*: {}".format(sev, count),
            })
        return fields

    def format_convergence_blocks(self, message: NotificationMessage) -> List[Dict]:
        blocks = []

        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": ":tada: CONVERGENCE ACHIEVED :tada:",
                "emoji": True,
            },
        })

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "Classification: *{}*".format(message.classification),
            },
        })

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": message.body,
            },
        })

        if message.metadata.get("overall_score") is not None:
            blocks.append({
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": "*Score*: {}/100".format(
                        message.metadata["overall_score"]
                    )},
                    {"type": "mrkdwn", "text": "*Cycle*: {}".format(message.cycle)},
                ],
            })

        return blocks