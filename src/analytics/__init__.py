"""
AURA Analytics Package.

Provides persistent storage, trend analysis, and report generation
for the AURA audit engine's historical data.

Exports:
    AnalyticsDB       - SQLite-backed persistent storage
    TrendAnalyzer     - Trend analysis and convergence prediction
    ReportGenerator   - Multi-format report generation (HTML, Markdown)
"""

from .database import AnalyticsDB
from .trends import TrendAnalyzer, Trend
from .reporter import ReportGenerator

__all__ = [
    "AnalyticsDB",
    "TrendAnalyzer",
    "Trend",
    "ReportGenerator",
]