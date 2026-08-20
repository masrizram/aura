"""
Trend analysis for audit data.
Identifies patterns, predicts convergence, and generates insights.

Capabilities:
    - Score trend analysis (improving/stable/worsening)
    - Finding density tracking
    - Convergence prediction
    - Plateau detection
    - MTTR trend analysis
    - Pattern identification (recurring vulnerabilities, hardest-to-fix categories)
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .database import AnalyticsDB


@dataclass
class Trend:
    metric: str
    direction: str
    current_value: float
    previous_value: float
    change_pct: float
    projection: Optional[float] = None
    cycles_to_converge: Optional[int] = None
    confidence: float = 0.0


class TrendAnalyzer:
    def __init__(self, db: AnalyticsDB):
        self.db = db

    def analyze_score_trend(self) -> Trend:
        scores = self.db.get_score_trend(limit=5)
        if len(scores) < 2:
            current = scores[-1]["overall_score"] if scores else 0
            return Trend(
                metric="overall_score",
                direction="stable",
                current_value=float(current),
                previous_value=float(current),
                change_pct=0.0,
                confidence=0.0,
            )

        current = float(scores[-1]["overall_score"])
        previous = float(scores[-2]["overall_score"])
        change_pct = ((current - previous) / max(previous, 1)) * 100

        if change_pct > 2:
            direction = "improving"
        elif change_pct < -2:
            direction = "worsening"
        else:
            direction = "stable"

        if len(scores) >= 3:
            values = [float(s["overall_score"]) for s in scores]
            cycles = list(range(len(values)))
            projection = self._linear_projection(cycles, values, 2)
        else:
            projection = None

        return Trend(
            metric="overall_score",
            direction=direction,
            current_value=current,
            previous_value=previous,
            change_pct=round(change_pct, 1),
            projection=projection,
            confidence=min(len(scores) / 5.0, 1.0),
        )

    def analyze_finding_density(self) -> Trend:
        histories = self.db.get_cycle_history(limit=10)
        if len(histories) < 2:
            return Trend(
                metric="finding_density",
                direction="stable",
                current_value=0.0,
                previous_value=0.0,
                change_pct=0.0,
                confidence=0.0,
            )

        densities = []
        for h in histories:
            fc = h.get("files_audited", 0) or 1
            fn = h.get("findings_new", 0)
            densities.append(fn / max(fc, 1))

        current = densities[-1] if densities else 0
        previous = densities[-2] if len(densities) >= 2 else current
        change_pct = ((current - previous) / max(previous, 0.001)) * 100

        if change_pct < -10:
            direction = "improving"
        elif change_pct > 10:
            direction = "worsening"
        else:
            direction = "stable"

        return Trend(
            metric="finding_density",
            direction=direction,
            current_value=round(current, 4),
            previous_value=round(previous, 4),
            change_pct=round(change_pct, 1),
            confidence=min(len(histories) / 10.0, 1.0),
        )

    def predict_convergence(self) -> Dict[str, Any]:
        scores = self.db.get_score_trend(limit=20)
        status_counts = self.db.get_finding_counts_by_status()

        if len(scores) < 2:
            return {
                "cycles_remaining": None,
                "confidence": 0.0,
                "projected_date": None,
                "is_plateau": False,
                "status": "INSUFFICIENT_DATA",
            }

        open_count = status_counts.get("OPEN", 0) + status_counts.get("IN_PROGRESS", 0)
        values = [float(s["overall_score"]) for s in scores]
        cycles = list(range(len(values)))

        close_rate = 0
        for i in range(2, len(scores)):
            close_rate += (values[i] - values[i - 1])
        close_rate = close_rate / max(len(scores) - 2, 1)

        if close_rate <= 0:
            return {
                "cycles_remaining": None,
                "confidence": 0.0,
                "projected_date": None,
                "is_plateau": True,
                "status": "STALLED",
            }

        target = 100
        gap = target - values[-1]
        if gap <= 0:
            return {
                "cycles_remaining": 0,
                "confidence": 1.0,
                "projected_date": datetime.now(timezone.utc).isoformat(),
                "is_plateau": False,
                "status": "ACHIEVED",
            }

        cycles_remaining = math.ceil(gap / close_rate)
        cycles_remaining = min(cycles_remaining, 200)

        confidence = min(len(scores) / 10.0, 0.9)
        if close_rate < 1:
            confidence *= 0.5

        projected_date = None
        if cycles_remaining > 0:
            projected_date = datetime.now(timezone.utc).isoformat()

        return {
            "cycles_remaining": cycles_remaining,
            "confidence": round(confidence, 2),
            "projected_date": projected_date,
            "is_plateau": False,
            "status": "IN_PROGRESS",
            "close_rate_per_cycle": round(close_rate, 2),
            "current_gap": round(gap, 1),
        }

    def detect_plateau(self) -> bool:
        scores = self.db.get_score_trend(limit=10)
        if len(scores) < 4:
            return False

        recent_values = [float(s["overall_score"]) for s in scores[-4:]]
        variance = max(recent_values) - min(recent_values)
        return variance < 3

    def analyze_mttr(self) -> Trend:
        mttr_data = self.db.get_mttr_data(limit=50)
        if len(mttr_data) < 2:
            return Trend(
                metric="mttr_hours",
                direction="stable",
                current_value=0.0,
                previous_value=0.0,
                change_pct=0.0,
                confidence=0.0,
            )

        recent = mttr_data[:len(mttr_data)//2] if len(mttr_data) > 4 else mttr_data
        older = mttr_data[len(mttr_data)//2:] if len(mttr_data) > 4 else mttr_data

        recent_avg = sum(r["time_to_fix_hours"] for r in recent) / max(len(recent), 1)
        older_avg = sum(r["time_to_fix_hours"] for r in older) / max(len(older), 1)

        if older_avg > 0:
            change_pct = ((recent_avg - older_avg) / older_avg) * 100
        else:
            change_pct = 0.0

        if change_pct < -10:
            direction = "improving"
        elif change_pct > 10:
            direction = "worsening"
        else:
            direction = "stable"

        return Trend(
            metric="mttr_hours",
            direction=direction,
            current_value=round(recent_avg, 1),
            previous_value=round(older_avg, 1),
            change_pct=round(change_pct, 1),
            confidence=min(len(mttr_data) / 20.0, 1.0),
        )

    def identify_patterns(self) -> List[Dict[str, Any]]:
        patterns: List[Dict[str, Any]] = []

        categories = self.db.get_category_counts()
        if categories:
            sorted_cats = sorted(categories.items(), key=lambda x: x[1], reverse=True)
            patterns.append({
                "type": "most_common_categories",
                "description": "Most common finding categories",
                "data": [{"category": c, "count": n} for c, n in sorted_cats[:5]],
            })

        recurring = self.db.get_recurring_findings(min_occurrences=2)
        if recurring:
            patterns.append({
                "type": "recurring_findings",
                "description": "Findings appearing across multiple cycles",
                "data": [{"finding_id": r["finding_id"], "occurrences": r["occurrences"],
                          "severity": r["severity"], "category": r["category"]}
                         for r in recurring[:10]],
            })

        gate_flips = self.db.get_gate_flip_history()
        if gate_flips:
            flips_by_gate: Dict[str, int] = {}
            for gf in gate_flips:
                gname = gf["gate_name"]
                flips_by_gate[gname] = flips_by_gate.get(gname, 0) + 1
            hardest = sorted(flips_by_gate.items(), key=lambda x: x[1], reverse=True)
            patterns.append({
                "type": "hardest_gates",
                "description": "Most frequently flipping convergence gates",
                "data": [{"gate": g, "flips": n} for g, n in hardest[:5]],
            })

        return patterns

    def generate_trend_report(self) -> str:
        score_trend = self.analyze_score_trend()
        density_trend = self.analyze_finding_density()
        mttr_trend = self.analyze_mttr()
        convergence = self.predict_convergence()
        is_plateau = self.detect_plateau()
        patterns = self.identify_patterns()

        lines = [
            "# Trend Analysis Report",
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            "",
            "## Score Trend",
            f"- Direction: **{score_trend.direction}**",
            f"- Current: {score_trend.current_value:.1f}",
            f"- Previous: {score_trend.previous_value:.1f}",
            f"- Change: {score_trend.change_pct:+.1f}%",
            f"- Confidence: {score_trend.confidence:.0%}",
        ]

        if score_trend.projection is not None:
            lines.append(f"- Next cycle projection: {score_trend.projection:.1f}")

        lines.extend([
            "",
            "## Finding Density",
            f"- Direction: **{density_trend.direction}**",
            f"- Current: {density_trend.current_value:.4f} findings/file",
            f"- Change: {density_trend.change_pct:+.1f}%",
            "",
            "## MTTR (Mean Time To Remediate)",
            f"- Direction: **{mttr_trend.direction}**",
            f"- Current average: {mttr_trend.current_value:.1f}h",
            f"- Previous average: {mttr_trend.previous_value:.1f}h",
            f"- Change: {mttr_trend.change_pct:+.1f}%",
            "",
            "## Convergence Prediction",
            f"- Status: **{convergence.get('status', 'UNKNOWN')}**",
            f"- Cycles remaining: {convergence.get('cycles_remaining', 'N/A')}",
            f"- Confidence: {convergence.get('confidence', 0):.0%}",
            f"- Rate: {convergence.get('close_rate_per_cycle', 0):.2f} points/cycle",
            f"- Plateau detected: **{'YES' if is_plateau else 'No'}**",
            "",
            "## Patterns",
        ])

        for p in patterns:
            lines.append(f"### {p['type'].replace('_', ' ').title()}")
            lines.append(f"{p['description']}")
            for item in p.get("data", []):
                lines.append(f"- {item}")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _linear_projection(x: List[int], y: List[float], steps_ahead: int) -> Optional[float]:
        n = len(x)
        if n < 2:
            return None
        x_mean = sum(x) / n
        y_mean = sum(y) / n
        num = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
        den = sum((xi - x_mean) ** 2 for xi in x)
        if abs(den) < 1e-10:
            return y_mean
        slope = num / den
        intercept = y_mean - slope * x_mean
        future_x = x[-1] + steps_ahead
        return intercept + slope * future_x