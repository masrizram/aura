"""AURA Engine - Cross-platform Python orchestrator for the Continuous Autonomous Engineering Audit Engine."""

import sys
import os
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .config import get_config
from .state_manager import StateManager, write_text_file, read_json_file, safe_int
from .state_machine import (
    validate_finding_state_integrity,
    validate_gate_evidence_integrity,
    test_valid_classification_transition,
    validate_gate_findings_crosscheck,
    GATE_NAMES,
)
from .cycle_prompt import generate_cycle_prompt, load_locale, get_l10n, get_findings_summary
from .git_controller import get_git_context, invoke_engine_push
from .tooling import (
    execute_tooling_and_save,
    get_project_tooling,
    get_tooling_commands,
    invoke_project_tooling,
    format_tooling_report,
)
from .cli import (
    resolve_repo_root,
    write_banner,
    ModuleLoader,
    load_all_modules,
    MODULE_ORDER,
    bootstrap_dirs,
    action_status,
    action_validate_state,
    action_promote_state,
)

__version__ = "2.1.2"