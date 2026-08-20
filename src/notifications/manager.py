"""Central notification manager with event routing and rate limiting."""

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import AlertLevel, BaseNotifier, NotificationEvent, NotificationMessage


class NotificationManager:

    def __init__(self, config_path: Optional[str] = None):
        self.notifiers: List[BaseNotifier] = []
        self.notifier_events: Dict[str, List[NotificationEvent]] = {}
        self.rate_limits: Dict[str, int] = {}
        self._last_sent: Dict[str, float] = {}
        self.config_path = config_path
        self._load_config()

    def _load_config(self):
        path = self.config_path
        if not path:
            return

        config_file = Path(path)
        if not config_file.exists():
            return

        try:
            cfg = json.loads(config_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return

        if not cfg.get("enabled", True):
            return

        self.rate_limits = cfg.get("rate_limit", {})
        global_limit = cfg.get("rate_limit_seconds", 300)
        if global_limit and "default" not in self.rate_limits:
            self.rate_limits["default"] = global_limit

        from .slack import SlackNotifier
        from .discord import DiscordNotifier
        from .email import EmailNotifier
        from .webhook import WebhookNotifier

        notifiers_cfg = cfg.get("notifiers", {})

        slack_cfg = notifiers_cfg.get("slack", {})
        if slack_cfg.get("enabled"):
            notifier = SlackNotifier(
                webhook_url=slack_cfg.get("webhook_url"),
                channel=slack_cfg.get("channel"),
            )
            events = self._parse_events(slack_cfg.get("events", []))
            self.register(notifier, events)

        discord_cfg = notifiers_cfg.get("discord", {})
        if discord_cfg.get("enabled"):
            notifier = DiscordNotifier(
                webhook_url=discord_cfg.get("webhook_url"),
            )
            events = self._parse_events(discord_cfg.get("events", []))
            self.register(notifier, events)

        email_cfg = notifiers_cfg.get("email", {})
        if email_cfg.get("enabled"):
            notifier = EmailNotifier(smtp_config=email_cfg)
            events = self._parse_events(email_cfg.get("events", []))
            self.register(notifier, events)

        webhook_cfg = notifiers_cfg.get("webhook", {})
        if webhook_cfg.get("enabled"):
            notifier = WebhookNotifier(url=webhook_cfg.get("url"))
            events = self._parse_events(webhook_cfg.get("events", []))
            self.register(notifier, events)

    @staticmethod
    def _parse_events(raw: list) -> List[NotificationEvent]:
        events: List[NotificationEvent] = []
        for name in raw:
            try:
                events.append(NotificationEvent(name))
            except ValueError:
                pass
        return events

    def register(
        self,
        notifier: BaseNotifier,
        events: Optional[List[NotificationEvent]] = None,
    ):
        self.notifiers.append(notifier)
        if events:
            self.notifier_events[notifier.get_name()] = events

    def _check_rate_limit(self, event_key: str) -> bool:
        limit = self.rate_limits.get(
            event_key, self.rate_limits.get("default", 0)
        )
        if limit <= 0:
            return True
        now = time.time()
        last = self._last_sent.get(event_key, 0)
        if now - last >= limit:
            self._last_sent[event_key] = now
            return True
        return False

    def notify(self, event: NotificationEvent, **context) -> List[bool]:
        rate_key = event.value
        if not self._check_rate_limit(rate_key):
            return []

        message = self._build_message(event, context)
        if message is None:
            message = NotificationMessage(
                event=event,
                level=AlertLevel.INFO,
                title=event.value.replace("_", " ").title(),
                body="",
                cycle=context.get("cycle", 0),
                classification=context.get("classification", "NOT_READY"),
                findings_count=context.get("findings_count", {}),
                metadata=context,
            )

        results = []
        for notifier in self.notifiers:
            allowed = self.notifier_events.get(notifier.get_name())
            if allowed is not None and event not in allowed:
                continue
            results.append(notifier.send(message))

        return results

    def _build_message(
        self, event: NotificationEvent, context: dict
    ) -> Optional[NotificationMessage]:
        cycle = context.get("cycle", 0)
        classification = context.get("classification", "NOT_READY")
        findings_count = context.get("findings_count", {})
        metadata = {k: v for k, v in context.items() if k not in {
            "cycle", "classification", "findings_count",
        }}

        event_config = {
            NotificationEvent.CRITICAL_FINDING: (
                AlertLevel.CRITICAL,
                "Critical Finding Detected",
                context.get("detail", "A P0 finding was discovered."),
            ),
            NotificationEvent.NEW_P0_FINDING: (
                AlertLevel.CRITICAL,
                "New P0 Finding",
                context.get("detail", "A new P0 finding has been filed."),
            ),
            NotificationEvent.NEW_P1_FINDING: (
                AlertLevel.WARNING,
                "New P1 Finding",
                context.get("detail", "A new P1 finding has been filed."),
            ),
            NotificationEvent.CYCLE_COMPLETE: (
                AlertLevel.INFO,
                "Cycle {} Complete".format(cycle),
                context.get("detail", "Audit cycle completed."),
            ),
            NotificationEvent.CONVERGENCE_ACHIEVED: (
                AlertLevel.SUCCESS,
                "Convergence Achieved",
                context.get(
                    "detail",
                    "All gates pass. Classification: {}.".format(classification),
                ),
            ),
            NotificationEvent.CONVERGENCE_LOST: (
                AlertLevel.WARNING,
                "Convergence Lost",
                context.get(
                    "detail",
                    "Previously passing gates now fail. Classification: {}.".format(
                        classification
                    ),
                ),
            ),
            NotificationEvent.STALL_WARNING: (
                AlertLevel.WARNING,
                "Stall Warning",
                "No progress for {} cycles.".format(
                    context.get("stall_cycles", "?")
                ),
            ),
            NotificationEvent.MAX_CYCLES_REACHED: (
                AlertLevel.WARNING,
                "Max Cycles Reached",
                "Maximum cycle count reached without convergence.",
            ),
            NotificationEvent.GATE_FLIP: (
                AlertLevel.INFO,
                "Gate Status Change",
                context.get("detail", "A convergence gate changed state."),
            ),
            NotificationEvent.SCORE_CHANGE: (
                AlertLevel.INFO,
                "Score Change",
                context.get("detail", "Overall score has changed."),
            ),
            NotificationEvent.PROMOTION_REJECTED: (
                AlertLevel.WARNING,
                "Promotion Rejected",
                context.get("detail", "State promotion was rejected."),
            ),
            NotificationEvent.PUSH_COMPLETE: (
                AlertLevel.INFO,
                "Push Complete",
                context.get("detail", "Changes pushed to remote."),
            ),
        }

        config = event_config.get(event)
        if config is None:
            return None

        level, title, body = config
        return NotificationMessage(
            event=event,
            level=level,
            title=title,
            body=body,
            cycle=cycle,
            classification=classification,
            findings_count=findings_count,
            metadata=metadata,
        )

    def notify_critical_finding(self, finding: dict, cycle: int):
        severity = finding.get("severity", "P0")
        event = NotificationEvent.CRITICAL_FINDING
        if severity == "P0":
            event = NotificationEvent.NEW_P0_FINDING
        elif severity == "P1":
            event = NotificationEvent.NEW_P1_FINDING

        detail = "[{}] {}: {}".format(
            severity, finding.get("id", "?"), finding.get("title", finding.get("description", ""))
        )
        context = {
            "cycle": cycle,
            "classification": finding.get("classification", "NOT_READY"),
            "detail": detail,
            "finding": finding,
        }
        return self.notify(event, **context)

    def notify_cycle_complete(
        self, state: dict, findings_data: dict, convergence: dict
    ):
        cycle = state.get("current_cycle", 0)
        classification = convergence.get("classification", "NOT_READY")

        findings_count = {"P0": 0, "P1": 0, "P2": 0, "P3": 0, "P4": 0, "P5": 0}
        if findings_data and "findings" in findings_data:
            for f in findings_data["findings"]:
                sev = f.get("severity", "P5")
                findings_count[sev] = findings_count.get(sev, 0) + 1

        score = convergence.get("overall_score", "N/A")
        conv = convergence.get("converged", False)
        detail = "Cycle {} complete. Score: {}. Converged: {}.".format(
            cycle, score, conv
        )

        context = {
            "cycle": cycle,
            "classification": classification,
            "findings_count": findings_count,
            "detail": detail,
            "overall_score": convergence.get("overall_score"),
            "converged": conv,
            "gate_status": convergence.get("gates"),
            "state": state,
        }
        return self.notify(NotificationEvent.CYCLE_COMPLETE, **context)

    def notify_convergence(self, classification: str, gates: dict):
        is_converged = classification in ("PRODUCTION_READY", "CONDITIONALLY_READY")
        event = (
            NotificationEvent.CONVERGENCE_ACHIEVED
            if is_converged
            else NotificationEvent.CONVERGENCE_LOST
        )
        detail = "Classification changed to {}.".format(classification)
        context = {
            "classification": classification,
            "detail": detail,
            "gate_status": gates,
        }
        return self.notify(event, **context)

    def send_digest(self, cycle: int) -> bool:
        return len(self.notify(
            NotificationEvent.CYCLE_COMPLETE,
            cycle=cycle,
            classification="DIGEST",
            detail="Digest for cycle {}.".format(cycle),
            findings_count={},
        )) > 0