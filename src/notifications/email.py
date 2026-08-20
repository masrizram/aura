"""Email notifier using SMTP with HTML formatting."""

import os
import smtplib
import socket
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional

from .base import AlertLevel, BaseNotifier, NotificationEvent, NotificationMessage

_BADGE_COLORS = {
    AlertLevel.CRITICAL: "#D00000",
    AlertLevel.WARNING: "#FFA000",
    AlertLevel.INFO: "#1D9BD1",
    AlertLevel.SUCCESS: "#2EB67D",
}

_LEVEL_LABELS = {
    AlertLevel.CRITICAL: "CRITICAL",
    AlertLevel.WARNING: "WARNING",
    AlertLevel.INFO: "INFO",
    AlertLevel.SUCCESS: "SUCCESS",
}


class EmailNotifier(BaseNotifier):

    def __init__(self, smtp_config: Optional[Dict] = None):
        cfg = smtp_config or {}
        self.smtp_host = os.getenv("AURA_SMTP_HOST", cfg.get("smtp_host", "localhost"))
        self.smtp_port = int(os.getenv("AURA_SMTP_PORT", str(cfg.get("smtp_port", 587))))
        self.from_addr = os.getenv("AURA_EMAIL_FROM", cfg.get("from", "aura@localhost"))
        self.username = os.getenv("AURA_SMTP_USER", cfg.get("username", ""))
        self.password = os.getenv("AURA_SMTP_PASS", cfg.get("password", ""))
        self.tls = cfg.get("tls", True)

    def get_name(self) -> str:
        return "Email"

    def is_configured(self) -> bool:
        return bool(self.smtp_host and self.from_addr)

    def send(self, message: NotificationMessage) -> bool:
        return False

    def send_to(self, message: NotificationMessage, to_addrs_str: str) -> bool:
        if not self.is_configured():
            return False

        to_addrs = [a.strip() for a in to_addrs_str.split(",") if a.strip()]
        if not to_addrs:
            return False

        html_body = self.build_html(message)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = message.title
        msg["From"] = self.from_addr
        msg["To"] = to_addrs_str

        part = MIMEText(html_body, "html", "utf-8")
        msg.attach(part)

        try:
            return self._smtp_send(self.from_addr, to_addrs, msg.as_string())
        except (smtplib.SMTPException, socket.error, OSError, ConnectionError):
            return False

    def _smtp_send(self, from_addr: str, to_addrs: List[str], msg_string: str) -> bool:
        if self.tls:
            server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15)
            server.starttls()
        else:
            server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15)

        if self.username and self.password:
            server.login(self.username, self.password)

        server.sendmail(from_addr, to_addrs, msg_string.encode("utf-8"))
        server.quit()
        return True

    def build_html(self, message: NotificationMessage) -> str:
        color = _BADGE_COLORS[message.level]
        label = _LEVEL_LABELS[message.level]

        finding_rows = ""
        if message.findings_count:
            rows = []
            for sev, count in sorted(message.findings_count.items()):
                rows.append(
                    '<tr><td style="padding:4px 12px;border:1px solid #ddd;">'
                    "<strong>{}</strong></td>"
                    '<td style="padding:4px 12px;border:1px solid #ddd;">{}</td></tr>'.format(
                        sev, count
                    )
                )
            finding_rows = "\n".join(rows)

        score_html = ""
        if message.metadata.get("overall_score") is not None:
            score_html = '<p><strong>Overall Score:</strong> {}/100</p>'.format(
                message.metadata["overall_score"]
            )

        return """\
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
             max-width:640px;margin:0 auto;padding:20px;color:#333;">
  <div style="background:{};color:#fff;padding:16px 24px;border-radius:8px 8px 0 0;
              margin-bottom:0;">
    <span style="display:inline-block;background:rgba(255,255,255,0.2);
                 padding:2px 10px;border-radius:4px;font-size:12px;text-transform:uppercase;">
      {}</span>
    <h1 style="margin:8px 0 0;font-size:20px;">{title}</h1>
  </div>
  <div style="border:1px solid #ddd;border-top:none;border-radius:0 0 8px 8px;
              padding:24px;">
    <table style="width:100%;margin-bottom:16px;">
      <tr>
        <td style="padding:4px 0;"><strong>Cycle:</strong></td>
        <td style="padding:4px 0;">{cycle}</td>
        <td style="padding:4px 0;"><strong>Classification:</strong></td>
        <td style="padding:4px 0;">{classification}</td>
      </tr>
    </table>
    {score_html}
    <p style="line-height:1.6;white-space:pre-wrap;">{body}</p>
{findings_section}
    <hr style="border:none;border-top:1px solid #eee;margin:16px 0;">
    <p style="font-size:12px;color:#888;">AURA Audit Engine v2.1.2 — {cycle_title}</p>
  </div>
</body>
</html>""".format(
            color,
            label,
            title=message.title,
            cycle=message.cycle,
            classification=message.classification,
            score_html=score_html,
            body=message.body,
            findings_section=(
                '<h3 style="margin-top:20px;">Open Findings</h3>'
                '<table style="width:100%;border-collapse:collapse;margin-top:8px;">'
                "{}</table>".format(finding_rows)
                if finding_rows
                else ""
            ),
            cycle_title=message.event.value.replace("_", " ").title(),
        )