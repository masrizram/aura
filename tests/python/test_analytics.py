"""Tests for analytics database and trend analysis."""

import json
import os
from pathlib import Path

import pytest

from src.analytics.database import AnalyticsDB
from src.analytics.trends import TrendAnalyzer, Trend


class TestAnalyticsDB:
    def test_init_creates_db(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = AnalyticsDB(str(db_path))
        assert db_path.exists()

    def test_record_and_retrieve_cycle(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = AnalyticsDB(str(db_path))
        db.record_cycle({
            "cycle_number": 1,
            "classification": "NOT_READY",
            "overall_score": 55,
            "convergence_status": False,
        })
        history = db.get_cycle_history()
        assert len(history) == 1
        assert history[0]["classification"] == "NOT_READY"
        assert history[0]["overall_score"] == 55

    def test_record_multiple_cycles(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = AnalyticsDB(str(db_path))
        for i in range(1, 6):
            db.record_cycle({
                "cycle_number": i,
                "classification": "NOT_READY" if i < 5 else "CONDITIONALLY_READY",
                "overall_score": 40 + i * 10,
            })
        history = db.get_cycle_history()
        assert len(history) == 5

    def test_record_finding(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = AnalyticsDB(str(db_path))
        db.record_finding({
            "id": "F001",
            "severity": "P0",
            "status": "OPEN",
            "category": "SECURITY",
            "risk_score": 500,
            "problem": "Test finding",
        }, cycle=1)
        db.record_finding({
            "id": "F001",
            "severity": "P0",
            "status": "FIXED",
            "category": "SECURITY",
            "problem": "Test finding",
        }, cycle=2)
        timeline = db.get_finding_timeline("F001")
        assert len(timeline) == 2
        assert timeline[0]["status"] == "OPEN"
        assert timeline[1]["status"] == "FIXED"

    def test_record_gates(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = AnalyticsDB(str(db_path))
        gates = {"P0_zero": True, "P1_zero": False, "data_integrity": True}
        db.record_gates(1, gates)
        summary = db.get_cycle_summary(1)
        assert summary is not None
        assert summary["gates"]["P0_zero"] is True
        assert summary["gates"]["P1_zero"] is False

    def test_record_dimension_scores(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = AnalyticsDB(str(db_path))
        scores = {"Security": 52.0, "Correctness": 68.0, "Architecture": 60.0}
        db.record_dimension_scores(1, scores)
        trend = db.get_dimension_trend("Security")
        assert len(trend) == 1
        assert trend[0]["score"] == 52.0

    def test_record_tooling(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = AnalyticsDB(str(db_path))
        results = {
            "npm test": {"exit_code": 0, "success": True, "output": "All pass"},
            "npm run lint": {"exit_code": 1, "success": False, "output": "Error"},
        }
        db.record_tooling(1, results)
        summary = db.get_cycle_summary(1)
        assert summary is not None

    def test_finding_counts_by_severity(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = AnalyticsDB(str(db_path))
        findings = [
            {"id": "F001", "severity": "P0", "status": "OPEN", "category": "SECURITY"},
            {"id": "F002", "severity": "P1", "status": "OPEN", "category": "CORRECTNESS"},
            {"id": "F003", "severity": "P2", "status": "FIXED", "category": "SECURITY"},
            {"id": "F004", "severity": "P2", "status": "OPEN", "category": "DOCUMENTATION"},
        ]
        for f in findings:
            db.record_finding(f, cycle=1)
        counts = db.get_finding_counts_by_severity()
        assert counts.get("P0") == 1
        assert counts.get("P1") == 1
        assert counts.get("P2") == 2

    def test_finding_counts_by_status(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = AnalyticsDB(str(db_path))
        findings = [
            {"id": "F001", "severity": "P0", "status": "OPEN", "category": "SECURITY"},
            {"id": "F002", "severity": "P1", "status": "FIXED", "category": "CORRECTNESS"},
        ]
        for f in findings:
            db.record_finding(f, cycle=1)
        counts = db.get_finding_counts_by_status()
        assert counts.get("OPEN") == 1
        assert counts.get("FIXED") == 1

    def test_last_cycle_number(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = AnalyticsDB(str(db_path))
        assert db.get_last_cycle_number() == 0
        db.record_cycle({"cycle_number": 3, "overall_score": 70})
        assert db.get_last_cycle_number() == 3

    def test_recurring_findings(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = AnalyticsDB(str(db_path))
        for cycle in [1, 2, 3]:
            db.record_finding({
                "id": "F_RECUR",
                "severity": "P1",
                "status": "OPEN",
                "category": "SECURITY",
            }, cycle=cycle)
        db.record_finding({
            "id": "F_ONCE",
            "severity": "P2",
            "status": "OPEN",
            "category": "DOCS",
        }, cycle=1)
        recurring = db.get_recurring_findings(min_occurrences=2)
        assert any(r["finding_id"] == "F_RECUR" for r in recurring)
        assert not any(r["finding_id"] == "F_ONCE" for r in recurring)

    def test_category_counts(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = AnalyticsDB(str(db_path))
        db.record_finding({"id": "F1", "severity": "P0", "status": "OPEN", "category": "SECURITY"}, cycle=1)
        db.record_finding({"id": "F2", "severity": "P0", "status": "OPEN", "category": "SECURITY"}, cycle=1)
        db.record_finding({"id": "F3", "severity": "P1", "status": "OPEN", "category": "CORRECTNESS"}, cycle=1)
        counts = db.get_category_counts()
        assert counts.get("SECURITY") >= 2
        assert counts.get("CORRECTNESS") >= 1

    def test_score_trend(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = AnalyticsDB(str(db_path))
        for i, score in enumerate([40, 45, 50, 55, 60], start=1):
            db.record_cycle({"cycle_number": i, "overall_score": score})
        trend = db.get_score_trend(limit=10)
        assert len(trend) == 5
        assert trend[-1]["overall_score"] == 60

    def test_migrate_from_json(self, tmp_path):
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        conv = {
            "cycle": 6,
            "converged": False,
            "overall_score": 55,
            "classification": "NOT_READY",
            "confidence": "HIGH",
            "reason": "Test cycle",
            "gates": {"P0_zero": False, "P1_zero": False},
            "dimension_scores": {"Security": 52, "Correctness": 68},
        }
        (state_dir / "convergence.json").write_text(json.dumps(conv))

        findings = {
            "findings": [
                {"id": "F001", "severity": "P0", "status": "OPEN", "category": "SECURITY"},
                {"id": "F002", "severity": "P1", "status": "FIXED", "category": "CORRECTNESS"},
            ]
        }
        (state_dir / "findings.json").write_text(json.dumps(findings))

        db_path = tmp_path / "analytics.db"
        db = AnalyticsDB(str(db_path))
        count = db.migrate_from_json(str(state_dir))
        assert count > 0
        history = db.get_cycle_history()
        assert len(history) >= 1

    def test_evidence_chain_recording(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = AnalyticsDB(str(db_path))
        entry = {
            "evidence_id": "ev_abc123",
            "content_hash": "a" * 64,
            "signature": "b" * 128,
            "signer": "test-signer",
            "timestamp": "2024-01-01T00:00:00",
            "chain_index": 0,
            "previous_hash": "0" * 64,
            "verified": True,
        }
        db.record_evidence_entry(entry)


class TestTrendAnalyzer:
    def _populate_db(self, db: AnalyticsDB, cycles: int = 5) -> None:
        base_score = 40
        for i in range(1, cycles + 1):
            score = base_score + i * 10
            db.record_cycle({
                "cycle_number": i,
                "overall_score": score,
                "classification": "NOT_READY",
            })
            db.record_finding({
                "id": f"F_{i:03d}",
                "severity": "P1",
                "status": "OPEN" if i % 2 == 1 else "FIXED",
                "category": "SECURITY",
                "time_to_fix_hours": 4.0 + i,
            }, cycle=i)

    def test_analyze_score_trend_improving(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = AnalyticsDB(str(db_path))
        self._populate_db(db)
        analyzer = TrendAnalyzer(db)
        trend = analyzer.analyze_score_trend()
        assert trend.metric == "overall_score"
        assert trend.direction in ("improving", "stable")
        assert trend.current_value > trend.previous_value

    def test_analyze_score_trend_single_cycle(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = AnalyticsDB(str(db_path))
        db.record_cycle({"cycle_number": 1, "overall_score": 50})
        analyzer = TrendAnalyzer(db)
        trend = analyzer.analyze_score_trend()
        assert trend.direction == "stable"
        assert trend.confidence == 0.0

    def test_predict_convergence(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = AnalyticsDB(str(db_path))
        self._populate_db(db, cycles=8)
        analyzer = TrendAnalyzer(db)
        pred = analyzer.predict_convergence()
        assert "cycles_remaining" in pred
        assert "confidence" in pred
        assert "status" in pred

    def test_predict_convergence_achieved(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = AnalyticsDB(str(db_path))
        db.record_cycle({"cycle_number": 1, "overall_score": 100})
        db.record_cycle({"cycle_number": 2, "overall_score": 100})
        analyzer = TrendAnalyzer(db)
        pred = analyzer.predict_convergence()
        assert pred["status"] == "ACHIEVED"

    def test_predict_convergence_stalled(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = AnalyticsDB(str(db_path))
        db.record_cycle({"cycle_number": 1, "overall_score": 40})
        db.record_cycle({"cycle_number": 2, "overall_score": 40})
        db.record_cycle({"cycle_number": 3, "overall_score": 40})
        analyzer = TrendAnalyzer(db)
        pred = analyzer.predict_convergence()
        assert pred.get("is_plateau") is True

    def test_detect_plateau(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = AnalyticsDB(str(db_path))
        for i in range(1, 6):
            db.record_cycle({"cycle_number": i, "overall_score": 50})
        analyzer = TrendAnalyzer(db)
        assert analyzer.detect_plateau() is True

    def test_detect_plateau_false_with_change(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = AnalyticsDB(str(db_path))
        for i, score in enumerate([40, 45, 50, 55, 60], start=1):
            db.record_cycle({"cycle_number": i, "overall_score": score})
        analyzer = TrendAnalyzer(db)
        assert analyzer.detect_plateau() is False

    def test_analyze_mttr(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = AnalyticsDB(str(db_path))
        for i in range(1, 6):
            db.record_finding({
                "id": f"F_{i}",
                "severity": "P1",
                "status": "FIXED",
                "category": "CORRECTNESS",
                "time_to_fix_hours": float(i * 2),
            }, cycle=i)
        analyzer = TrendAnalyzer(db)
        trend = analyzer.analyze_mttr()
        assert trend.metric == "mttr_hours"

    def test_identify_patterns(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = AnalyticsDB(str(db_path))
        self._populate_db(db)
        analyzer = TrendAnalyzer(db)
        patterns = analyzer.identify_patterns()
        assert len(patterns) > 0
        assert any(p["type"] == "most_common_categories" for p in patterns)

    def test_generate_trend_report(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = AnalyticsDB(str(db_path))
        self._populate_db(db)
        analyzer = TrendAnalyzer(db)
        report = analyzer.generate_trend_report()
        assert "# Trend Analysis Report" in report
        assert "Score Trend" in report
        assert "Convergence Prediction" in report


class TestTrend:
    def test_trend_dataclass(self):
        t = Trend(
            metric="test",
            direction="improving",
            current_value=75.0,
            previous_value=50.0,
            change_pct=50.0,
            projection=80.0,
            cycles_to_converge=3,
            confidence=0.8,
        )
        assert t.metric == "test"
        assert t.direction == "improving"
        assert t.projection == 80.0