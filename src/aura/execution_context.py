"""Execution Context Layer — classifies every file by runtime context.

Used by ALL 40 domain auditors to suppress false positives based on
where code executes, not just what it contains.

CONTEXT:
    PRODUCTION_CODE  — runtime application logic
    TEST_CODE        — unit/integration/E2E tests
    MIGRATION_CODE   — database migration/schema
    CONFIGURATION    — config files, env, settings
    DOCUMENTATION    — docs, README, architecture
    GENERATED_CODE   — auto-generated (migrations, stubs)
    BUILD_SCRIPT     — build/CI/CD scripts
    THIRD_PARTY      — vendor, node_modules, .tools
    INFRASTRUCTURE   — Docker, Terraform, K8s manifests
    UNKNOWN          — fallback

CONFIDENCE MODIFIERS per context:
    PRODUCTION_CODE  → 1.0x  (full severity)
    CONFIGURATION    → 1.0x  (full severity)
    INFRASTRUCTURE   → 0.9x
    BUILD_SCRIPT     → 0.7x
    MIGRATION_CODE   → 0.4x  (schema code, not runtime flow)
    TEST_CODE        → 0.3x  (controlled environment)
    GENERATED_CODE   → 0.2x  (auto-generated)
    DOCUMENTATION    → 0.1x  (prose, not code)
    THIRD_PARTY      → 0.0x  (not our code)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path


class ExecutionContext(Enum):
    PRODUCTION_CODE = auto()
    TEST_CODE = auto()
    MIGRATION_CODE = auto()
    CONFIGURATION = auto()
    DOCUMENTATION = auto()
    GENERATED_CODE = auto()
    BUILD_SCRIPT = auto()
    THIRD_PARTY = auto()
    INFRASTRUCTURE = auto()
    UNKNOWN = auto()


# Confidence modifiers per context
CONTEXT_CONFIDENCE: dict[ExecutionContext, float] = {
    ExecutionContext.PRODUCTION_CODE: 1.0,
    ExecutionContext.CONFIGURATION: 1.0,
    ExecutionContext.INFRASTRUCTURE: 0.9,
    ExecutionContext.BUILD_SCRIPT: 0.7,
    ExecutionContext.MIGRATION_CODE: 0.4,
    ExecutionContext.TEST_CODE: 0.3,
    ExecutionContext.GENERATED_CODE: 0.2,
    ExecutionContext.DOCUMENTATION: 0.1,
    ExecutionContext.THIRD_PARTY: 0.0,
    ExecutionContext.UNKNOWN: 0.8,
}


# Directory patterns that define context
_CONTEXT_DIRS: dict[str, ExecutionContext] = {
    "tests/": ExecutionContext.TEST_CODE,
    "test/": ExecutionContext.TEST_CODE,
    "__tests__/": ExecutionContext.TEST_CODE,
    "spec/": ExecutionContext.TEST_CODE,
    "migrations/": ExecutionContext.MIGRATION_CODE,
    "alembic/": ExecutionContext.MIGRATION_CODE,
    "docs/": ExecutionContext.DOCUMENTATION,
    "documentation/": ExecutionContext.DOCUMENTATION,
    "examples/": ExecutionContext.DOCUMENTATION,
    "config/": ExecutionContext.CONFIGURATION,
    "node_modules/": ExecutionContext.THIRD_PARTY,
    "vendor/": ExecutionContext.THIRD_PARTY,
    "bower_components/": ExecutionContext.THIRD_PARTY,
    ".tools/": ExecutionContext.THIRD_PARTY,
    "site-packages/": ExecutionContext.THIRD_PARTY,
    ".venv/": ExecutionContext.THIRD_PARTY,
    "venv/": ExecutionContext.THIRD_PARTY,
    ".terraform/": ExecutionContext.THIRD_PARTY,
    "__pycache__/": ExecutionContext.GENERATED_CODE,
    ".mypy_cache/": ExecutionContext.GENERATED_CODE,
    ".ruff_cache/": ExecutionContext.GENERATED_CODE,
    ".pytest_cache/": ExecutionContext.GENERATED_CODE,
    ".next/": ExecutionContext.GENERATED_CODE,
    "dist/": ExecutionContext.GENERATED_CODE,
    "build/": ExecutionContext.GENERATED_CODE,
    "target/": ExecutionContext.GENERATED_CODE,
    "coverage/": ExecutionContext.GENERATED_CODE,
    "lcov-report/": ExecutionContext.GENERATED_CODE,
    ".nyc_output/": ExecutionContext.GENERATED_CODE,
    ".github/workflows/": ExecutionContext.BUILD_SCRIPT,
    ".gitlab-ci.yml": ExecutionContext.BUILD_SCRIPT,
    "Jenkinsfile": ExecutionContext.BUILD_SCRIPT,
    "Dockerfile": ExecutionContext.INFRASTRUCTURE,
    "docker-compose": ExecutionContext.INFRASTRUCTURE,
    "terraform/": ExecutionContext.INFRASTRUCTURE,
    ".tf": ExecutionContext.INFRASTRUCTURE,
    "kubernetes/": ExecutionContext.INFRASTRUCTURE,
}


# File name patterns that define context
_CONTEXT_FILES: dict[str, ExecutionContext] = {
    "Dockerfile": ExecutionContext.INFRASTRUCTURE,
    "docker-compose.yml": ExecutionContext.INFRASTRUCTURE,
    "docker-compose.yaml": ExecutionContext.INFRASTRUCTURE,
    "Makefile": ExecutionContext.BUILD_SCRIPT,
    "GNUmakefile": ExecutionContext.BUILD_SCRIPT,
    "CMakeLists.txt": ExecutionContext.BUILD_SCRIPT,
    "Jenkinsfile": ExecutionContext.BUILD_SCRIPT,
    "README.md": ExecutionContext.DOCUMENTATION,
    "CHANGELOG.md": ExecutionContext.DOCUMENTATION,
    "CONTRIBUTING.md": ExecutionContext.DOCUMENTATION,
    "LICENSE": ExecutionContext.DOCUMENTATION,
    "SECURITY.md": ExecutionContext.DOCUMENTATION,
    "LIMITATIONS.md": ExecutionContext.DOCUMENTATION,
}


# File suffix contexts
_CONTEXT_SUFFIXES: dict[str, ExecutionContext] = {
    ".md": ExecutionContext.DOCUMENTATION,
    ".rst": ExecutionContext.DOCUMENTATION,
    ".txt": ExecutionContext.DOCUMENTATION,
    ".lock": ExecutionContext.GENERATED_CODE,
    ".svg": ExecutionContext.DOCUMENTATION,
    ".png": ExecutionContext.DOCUMENTATION,
    ".jpg": ExecutionContext.DOCUMENTATION,
    ".gif": ExecutionContext.DOCUMENTATION,
    ".ico": ExecutionContext.DOCUMENTATION,
    ".woff": ExecutionContext.THIRD_PARTY,
    ".woff2": ExecutionContext.THIRD_PARTY,
    ".ttf": ExecutionContext.THIRD_PARTY,
    ".eot": ExecutionContext.THIRD_PARTY,
    ".pdf": ExecutionContext.DOCUMENTATION,
    ".csv": ExecutionContext.DOCUMENTATION,
}


@dataclass
class FileContext:
    path: str
    context: ExecutionContext
    confidence_modifier: float
    is_production: bool
    is_test: bool
    is_migration: bool
    is_documentation: bool
    is_generated: bool
    is_third_party: bool


class ExecutionContextClassifier:
    """Classifies every file in a repository by its execution context."""

    def __init__(self, repo_root: str | Path):
        self.repo_root = Path(repo_root)
        self._cache: dict[str, FileContext] = {}

    def classify(self, file_path: str) -> FileContext:
        """Classify a file path into its execution context."""
        if file_path in self._cache:
            return self._cache[file_path]

        ctx = self._determine_context(file_path)
        fc = FileContext(
            path=file_path,
            context=ctx,
            confidence_modifier=CONTEXT_CONFIDENCE[ctx],
            is_production=(ctx == ExecutionContext.PRODUCTION_CODE),
            is_test=(ctx == ExecutionContext.TEST_CODE),
            is_migration=(ctx == ExecutionContext.MIGRATION_CODE),
            is_documentation=(ctx == ExecutionContext.DOCUMENTATION),
            is_generated=(ctx == ExecutionContext.GENERATED_CODE),
            is_third_party=(ctx == ExecutionContext.THIRD_PARTY),
        )
        self._cache[file_path] = fc
        return fc

    def _determine_context(self, file_path: str) -> ExecutionContext:
        """Determine execution context from file path patterns."""
        path_lower = file_path.lower().replace("\\", "/")

        # 1. Check directory path segments
        for dir_pattern, ctx in sorted(_CONTEXT_DIRS.items(),
                                        key=lambda x: -len(x[0])):  # longest match first
            if dir_pattern.rstrip("/") + "/" in path_lower or path_lower.startswith(dir_pattern):
                return ctx

        # 2. Check exact file name
        file_name = Path(file_path).name
        if file_name in _CONTEXT_FILES:
            return _CONTEXT_FILES[file_name]

        # 3. Check suffix
        suffix = Path(file_path).suffix.lower()
        if suffix in _CONTEXT_SUFFIXES:
            return _CONTEXT_SUFFIXES[suffix]

        # 4. Test file patterns
        if any(p in file_name for p in ("test_", "_test.", ".test.", ".spec.",
                                         "Test.php", "TestCase", "conftest.py")):
            return ExecutionContext.TEST_CODE
        if "/tests/" in path_lower or "/test/" in path_lower or "/__tests__/" in path_lower:
            return ExecutionContext.TEST_CODE

        # 5. Migration patterns
        if "migration" in path_lower.lower() or "alembic" in path_lower:
            return ExecutionContext.MIGRATION_CODE

        # 6. Documentation patterns
        if path_lower.startswith("docs/") or "/docs/" in path_lower:
            return ExecutionContext.DOCUMENTATION
        if file_name in ("README.md", "CHANGELOG.md", "CONTRIBUTING.md",
                         "LICENSE", "SECURITY.md", "LIMITATIONS.md"):
            return ExecutionContext.DOCUMENTATION

        # 7. Build/CI patterns
        if any(p in path_lower for p in (".github/workflows/", ".gitlab-ci.yml",
                                          "Jenkinsfile", "Makefile", "bitbucket-pipelines.yml")):
            return ExecutionContext.BUILD_SCRIPT

        # 8. Infrastructure
        if any(p in path_lower for p in ("Dockerfile", "docker-compose",
                                          "terraform", ".tf", "kubernetes", "helm")):
            return ExecutionContext.INFRASTRUCTURE

        # 9. Configuration
        if any(p in path_lower for p in ("config/", ".env", "settings.py",
                                          "pyproject.toml", "package.json",
                                          "composer.json", "tsconfig.json")):
            return ExecutionContext.CONFIGURATION

        # 10. Third-party signals
        if any(p in path_lower for p in (".tools/", "vendor/", "node_modules/",
                                          "site-packages/", "bower_components/")):
            return ExecutionContext.THIRD_PARTY

        # Default: production code
        return ExecutionContext.PRODUCTION_CODE

    def should_suppress_finding(self, file_path: str, rule: str,
                                 severity: str) -> tuple[bool, str]:
        """Determine if a finding should be suppressed based on execution context.

        Returns (should_suppress, reason).
        """
        fc = self.classify(file_path)

        # Test code — suppress unless it's a P0 finding
        if fc.is_test:
            if severity == "P0":
                return False, ""  # P0 is always relevant, even in tests
            return True, "Finding in TEST_CODE context — controlled environment"

        # Documentation — suppress all security findings
        if fc.is_documentation:
            if severity == "P0":
                return False, ""
            return True, "Finding in DOCUMENTATION context — not executable code"

        # Migration code — suppress runtime findings
        if fc.is_migration:
            # Match any rule that starts with these patterns
            if any(rule.startswith(prefix) for prefix in ("PATH-TRAVERSAL", "INJ-", "AUTHZ", "AUTH-", "SESS-", "INPUT-")):
                return True, "Finding in MIGRATION_CODE context — schema code, not runtime"
            return False, ""

        # Third-party — always suppress
        if fc.is_third_party:
            return True, "Finding in THIRD_PARTY code — not our codebase"

        # Generated code — suppress unless P0
        if fc.is_generated:
            if severity == "P0":
                return False, ""
            return True, "Finding in GENERATED_CODE context"

        # Production — never suppress
        return False, ""

    def get_confidence_multiplier(self, file_path: str) -> float:
        """Get the confidence modifier for a file's context."""
        return self.classify(file_path).confidence_modifier


# Singleton instance for shared use
_context_instance: ExecutionContextClassifier | None = None


def get_context_classifier(repo_root: str | Path) -> ExecutionContextClassifier:
    """Get or create the execution context classifier for a repository."""
    global _context_instance
    if _context_instance is None or str(_context_instance.repo_root) != str(repo_root):
        _context_instance = ExecutionContextClassifier(repo_root)
    return _context_instance
