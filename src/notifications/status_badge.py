"""Status badge generator for README / CI embedding."""

import json
from pathlib import Path
from typing import Optional

from .base import NotificationMessage

_CLASSIFICATION_COLORS = {
    "PRODUCTION_READY": "brightgreen",
    "CONDITIONALLY_READY": "yellow",
    "NOT_READY": "red",
    "HUMAN_BLOCKED": "orange",
}

_CLASSIFICATION_HEX = {
    "PRODUCTION_READY": "#4c1",
    "CONDITIONALLY_READY": "#dfb317",
    "NOT_READY": "#e05d44",
    "HUMAN_BLOCKED": "#fe7d37",
}


class StatusBadgeGenerator:

    def __init__(self, engine_root: str):
        self.engine_root = Path(engine_root)

    def _read_classification(self) -> str:
        conv_path = self.engine_root / "state" / "convergence.json"
        if not conv_path.exists():
            return "NOT_READY"
        try:
            data = json.loads(conv_path.read_text(encoding="utf-8"))
            return data.get("classification", "NOT_READY")
        except (json.JSONDecodeError, OSError):
            return "NOT_READY"

    def _read_score(self) -> Optional[int]:
        conv_path = self.engine_root / "state" / "convergence.json"
        if not conv_path.exists():
            return None
        try:
            data = json.loads(conv_path.read_text(encoding="utf-8"))
            return data.get("overall_score")
        except (json.JSONDecodeError, OSError):
            return None

    def generate_badge_url(self) -> str:
        classification = self._read_classification()
        color = _CLASSIFICATION_COLORS.get(classification, "lightgrey")
        score = self._read_score()
        label = "AURA"
        message = classification.replace("_", " ")
        if score is not None:
            message = "{} ({})".format(message, score)
        return "https://img.shields.io/badge/{}-{}-{}".format(
            label, message.replace(" ", "_"), color
        )

    def generate_badge_markdown(self) -> str:
        url = self.generate_badge_url()
        return "![{}]({})".format("AURA", url)

    def generate_badge_svg(self) -> str:
        classification = self._read_classification()
        color = _CLASSIFICATION_HEX.get(classification, "#9f9f9f")
        score = self._read_score()
        label = "AURA"
        message = classification.replace("_", " ")
        if score is not None:
            message = "{} ({})".format(message, score)

        label_width = 42
        msg_width = len(message) * 7 + 20 + (12 if score is not None else 0)
        total_width = label_width + msg_width

        return """\
<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="20" role="img">
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r">
    <rect width="{total_width}" height="20" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#r)">
    <rect width="{label_width}" height="20" fill="#555"/>
    <rect x="{label_width}" width="{msg_width}" height="20" fill="{color}"/>
    <rect width="{total_width}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,DejaVu Sans,sans-serif"
     font-size="11">
    <text x="{label_x}" y="14">{label}</text>
    <text x="{msg_x}" y="14">{message}</text>
  </g>
</svg>""".format(
            total_width=total_width,
            label_width=label_width,
            msg_width=msg_width,
            color=color,
            label_x=label_width // 2,
            msg_x=label_width + msg_width // 2,
            label=label,
            message=message,
        )