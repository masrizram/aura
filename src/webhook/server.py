"""AURA Autonomous Audit — Webhook HTTP Server.

Accepts webhook calls from GitHub, GitLab, Bitbucket, and generic sources
to trigger autonomous audit cycles. Designed for CI/CD integration where
a push-based trigger is preferred over polling.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import flask
from flask import Flask, Response, jsonify, request

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_CONFIG_PATH = Path("config/aura.json")
DEFAULT_AUDIT_SCRIPT = Path("src/engine/run-audit.ps1")
DEFAULT_PORT = int(os.environ.get("AURA_WEBHOOK_PORT", "9090"))
DEFAULT_BIND = os.environ.get("AURA_WEBHOOK_BIND", "0.0.0.0")
DEFAULT_SECRET = os.environ.get("AURA_WEBHOOK_SECRET", "")
DEFAULT_LOG_LEVEL = os.environ.get("AURA_WEBHOOK_LOG_LEVEL", "INFO")


class EventSource(str, Enum):
    GITHUB = "github"
    GITLAB = "gitlab"
    BITBUCKET = "bitbucket"
    GENERIC = "generic"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class WebhookRequest:
    source: EventSource
    event: str
    payload: Dict[str, Any]
    signature: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AuditResult:
    success: bool
    exit_code: int
    convergence_score: int = 0
    p0_count: int = 0
    p1_count: int = 0
    p2_count: int = 0
    cycle: int = 0
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(
    config_path: Path = DEFAULT_CONFIG_PATH,
    audit_script: Path = DEFAULT_AUDIT_SCRIPT,
    webhook_secret: str = DEFAULT_SECRET,
) -> Flask:
    app = Flask(__name__)
    app.config["AURA_CONFIG_PATH"] = config_path
    app.config["AURA_AUDIT_SCRIPT"] = audit_script
    app.config["AURA_WEBHOOK_SECRET"] = webhook_secret

    logging.basicConfig(
        level=getattr(logging, DEFAULT_LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger("aura.webhook")

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _load_ci_config() -> Dict[str, Any]:
        if not config_path.exists():
            return {}
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            return cfg.get("ci", {})
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load config: %s", exc)
            return {}

    def _verify_github_signature(payload_body: bytes, signature_header: str) -> bool:
        secret = app.config["AURA_WEBHOOK_SECRET"] or _load_ci_config().get(
            "webhook", {}
        ).get("secret", "")
        if not secret:
            logger.warning("No webhook secret configured — skipping signature verification")
            return True
        if not signature_header.startswith("sha256="):
            logger.warning("Signature header missing sha256= prefix")
            return False
        expected = signature_header[len("sha256="):]
        computed = hmac.new(
            secret.encode("utf-8"), payload_body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(computed, expected)

    def _verify_gitlab_token(token_header: str) -> bool:
        secret = app.config["AURA_WEBHOOK_SECRET"] or _load_ci_config().get(
            "webhook", {}
        ).get("secret", "")
        if not secret:
            logger.warning("No webhook secret configured — skipping token verification")
            return True
        return hmac.compare_digest(token_header, secret)

    def _parse_webhook() -> Optional[WebhookRequest]:
        content_type = request.content_type or ""
        event_header = (
            request.headers.get("X-GitHub-Event", "")
            or request.headers.get("X-Gitlab-Event", "")
            or request.headers.get("X-Event-Key", "")
            or request.headers.get("X-AURA-Event", "ping")
        )

        if "X-GitHub-Event" in request.headers:
            source = EventSource.GITHUB
            signature = request.headers.get("X-Hub-Signature-256", "")
            if not _verify_github_signature(request.get_data(), signature):
                return None
        elif "X-Gitlab-Event" in request.headers:
            source = EventSource.GITLAB
            token = request.headers.get("X-Gitlab-Token", "")
            if not _verify_gitlab_token(token):
                return None
        elif "X-Event-Key" in request.headers:
            source = EventSource.BITBUCKET
        else:
            source = EventSource.GENERIC

        try:
            payload = request.get_json(force=True) if request.data else {}
        except Exception:
            payload = {}

        return WebhookRequest(source=source, event=event_header, payload=payload)

    def _run_audit(action: str = "run", language: str = "en") -> AuditResult:
        script = app.config["AURA_AUDIT_SCRIPT"]
        if not script.exists():
            logger.error("Audit script not found: %s", script)
            return AuditResult(success=False, exit_code=-1, stderr=f"Script not found: {script}")

        cmd = [
            "pwsh",
            "-NoProfile",
            "-File",
            str(script),
            "-Action",
            action,
            "-Language",
            language,
        ]

        logger.info("Running: %s", " ".join(cmd))
        start = time.monotonic()

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1800,
                cwd=str(script.parent.parent.parent),
            )
        except subprocess.TimeoutExpired:
            return AuditResult(
                success=False,
                exit_code=-1,
                stderr="Audit timed out after 30 minutes",
                duration_seconds=time.monotonic() - start,
            )

        duration = time.monotonic() - start

        findings = _read_findings()
        convergence = _read_convergence()

        return AuditResult(
            success=proc.returncode == 0,
            exit_code=proc.returncode,
            convergence_score=convergence.get("overall_score", 0),
            p0_count=findings.get("p0", 0),
            p1_count=findings.get("p1", 0),
            p2_count=findings.get("p2", 0),
            cycle=convergence.get("cycle", 0),
            stdout=proc.stdout[-2000:] if proc.stdout else "",
            stderr=proc.stderr[-2000:] if proc.stderr else "",
            duration_seconds=duration,
        )

    def _read_findings() -> Dict[str, int]:
        findings_path = Path(".aura/state/findings.json")
        if not findings_path.exists():
            return {"p0": 0, "p1": 0, "p2": 0, "total": 0}
        try:
            data = json.loads(findings_path.read_text(encoding="utf-8"))
            arr = data if isinstance(data, list) else data.get("findings", [])
            open_findings = [
                f for f in arr if f.get("state") in ("OPEN", "IN_PROGRESS")
            ]
            return {
                "p0": sum(1 for f in open_findings if f.get("severity") == "P0"),
                "p1": sum(1 for f in open_findings if f.get("severity") == "P1"),
                "p2": sum(1 for f in open_findings if f.get("severity") == "P2"),
                "total": len(open_findings),
            }
        except (json.JSONDecodeError, OSError):
            return {"p0": 0, "p1": 0, "p2": 0, "total": 0}

    def _read_convergence() -> Dict[str, Any]:
        conv_path = Path(".aura/state/convergence.json")
        if not conv_path.exists():
            return {}
        try:
            return json.loads(conv_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    # -----------------------------------------------------------------------
    # Routes
    # -----------------------------------------------------------------------

    @app.route("/health", methods=["GET"])
    def health() -> Response:
        return jsonify(
            {
                "status": "healthy",
                "service": "aura-webhook",
                "version": "2.1.0",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "pwsh_available": _check_pwsh(),
            }
        )

    @app.route("/webhook/audit", methods=["POST"])
    def webhook_audit() -> Response:
        parsed = _parse_webhook()
        if parsed is None:
            logger.warning("Signature verification failed from %s", request.remote_addr)
            return jsonify({"error": "signature_verification_failed"}), 401

        logger.info(
            "Webhook received: source=%s event=%s",
            parsed.source.value,
            parsed.event,
        )

        ci_config = _load_ci_config()
        webhook_cfg = ci_config.get("webhook", {})

        if not webhook_cfg.get("enabled", False):
            return jsonify({"error": "webhook_disabled", "message": "Webhook trigger is disabled in config"}), 403

        full_audit = parsed.payload.get("full_audit", False)
        language = parsed.payload.get("language", "en")
        action = "run" if not full_audit else "run"

        if full_audit:
            logger.info("Full audit requested — forcing full cycle")

        result = _run_audit(action=action, language=language)

        gate_passed = result.p0_count == 0 and result.p1_count == 0 and result.p2_count == 0

        response_payload = {
            "success": result.success,
            "gate_passed": gate_passed,
            "exit_code": result.exit_code,
            "convergence_score": result.convergence_score,
            "findings": {
                "p0": result.p0_count,
                "p1": result.p1_count,
                "p2": result.p2_count,
            },
            "cycle": result.cycle,
            "duration_seconds": round(result.duration_seconds, 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        status_code = 200 if gate_passed else 422
        return jsonify(response_payload), status_code

    @app.route("/webhook/audit/status", methods=["GET"])
    def webhook_status() -> Response:
        findings = _read_findings()
        convergence = _read_convergence()
        return jsonify(
            {
                "findings": findings,
                "convergence": {
                    "score": convergence.get("overall_score", 0),
                    "achieved": convergence.get("convergence_achieved", False),
                    "cycle": convergence.get("cycle", 0),
                },
                "state_dir_exists": Path(".aura/state").exists(),
                "reports_dir_exists": Path(".aura/reports").exists(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    @app.route("/webhook/audit/validate", methods=["POST"])
    def webhook_validate() -> Response:
        parsed = _parse_webhook()
        if parsed is None:
            return jsonify({"error": "signature_verification_failed"}), 401

        result = _run_audit(action="validate-state", language="en")
        return jsonify(
            {
                "success": result.success,
                "convergence_score": result.convergence_score,
                "duration_seconds": round(result.duration_seconds, 2),
            }
        ), 200 if result.success else 422

    @app.errorhandler(400)
    def bad_request(_error: Any) -> Response:
        return jsonify({"error": "bad_request"}), 400

    @app.errorhandler(500)
    def internal_error(_error: Any) -> Response:
        return jsonify({"error": "internal_server_error"}), 500

    return app


# ---------------------------------------------------------------------------
# Helpers (module-level)
# ---------------------------------------------------------------------------


def _check_pwsh() -> bool:
    try:
        subprocess.run(
            ["pwsh", "-NoProfile", "-Command", "Write-Host 'ok'"],
            capture_output=True,
            timeout=10,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="AURA Webhook Server")
    parser.add_argument(
        "--host",
        default=DEFAULT_BIND,
        help=f"Bind address (default: {DEFAULT_BIND})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Listen port (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--secret",
        default=DEFAULT_SECRET,
        help="Webhook secret for HMAC verification",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable Flask debug mode (NOT for production)",
    )
    args = parser.parse_args()

    app = create_app(webhook_secret=args.secret)

    logger = logging.getLogger("aura.webhook")
    logger.info(
        "Starting AURA webhook server on %s:%s", args.host, args.port
    )

    if args.debug:
        logger.warning("Debug mode enabled — do not use in production")

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()