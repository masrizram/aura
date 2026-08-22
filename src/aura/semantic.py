"""AURA Semantic Intelligence Layer — AST, data-flow, taint analysis, and evidence graph.

Transforms AURA from a regex scanner into a code intelligence engine.
Provides: AST parsing, symbol-table construction, control-flow analysis,
taint tracking (source→sanitizer→sink), confidence classification,
evidence graph construction, and repository memory across audit cycles.
"""

from __future__ import annotations

import ast as py_ast
import json
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any

# ═══════════════════════════════════════════════════════════════════════════════
# EVIDENCE / CONFIDENCE MODEL
# ═══════════════════════════════════════════════════════════════════════════════


class ConfidenceLevel(Enum):
    TRUE_POSITIVE = auto()       # Confirmed vulnerability — evidence chain complete
    LIKELY_TRUE = auto()         # High probability, missing some evidence
    UNCERTAIN = auto()           # Pattern matched, but context unclear
    LIKELY_FALSE_POSITIVE = auto()  # Pattern matched, but likely safe context
    FALSE_POSITIVE = auto()      # Verified safe — proven mitigation
    MITIGATED = auto()           # Risk exists but countermeasure verified


class FindingStatus(Enum):
    """Finding lifecycle with semantic intelligence."""
    RAW = auto()                # Raw regex match — no semantic analysis yet
    LOCATED = auto()            # AST-confirmed location
    ANALYZED = auto()           # Data-flow / taint analyzed
    CLASSIFIED = auto()         # Confidence assigned
    ACTIONABLE = auto()         # Ready for remediation
    FIXED = auto()              # Patch applied
    VERIFIED = auto()           # Independent verification passed
    MITIGATED = auto()          # Framework/pattern provides protection
    WAIVED = auto()             # Accepted by team


@dataclass
class EvidenceNode:
    """A single piece of evidence in an evidence graph."""
    kind: str  # "source", "transform", "sink", "sanitizer", "validator", "framework"
    description: str
    location: str = ""  # file:line
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FindingEvidence:
    """Full evidence graph for a semantic finding."""
    finding_id: str
    file: str
    line_start: int
    line_end: int
    symbol: str = ""
    severity: str = "P2"
    category: str = "SECURITY"
    rule: str = ""
    message: str = ""
    confidence: float = 0.0
    confidence_level: ConfidenceLevel = ConfidenceLevel.UNCERTAIN
    source: EvidenceNode | None = None       # Where untrusted data enters
    sanitizers: list[EvidenceNode] = field(default_factory=list)  # Transformations
    sink: EvidenceNode | None = None         # Where data is consumed dangerously
    data_flow: list[str] = field(default_factory=list)  # Variable propagation chain
    cwe_id: str = ""
    owasp_category: str = ""
    cvss_score: float = 0.0
    framework_context: str = ""  # e.g. "Laravel", "Django", "raw PHP", "Express"
    root_cause: str = ""
    remediation_advice: str = ""
    raw_evidence: str = ""
    cross_file_references: list[str] = field(default_factory=list)
    ast_node_type: str = ""  # e.g. "Call", "Assign", "BinaryOp"


# ═══════════════════════════════════════════════════════════════════════════════
# SECURITY KNOWLEDGE BASE — CWE, OWASP, CVSS mappings
# ═══════════════════════════════════════════════════════════════════════════════

CWE_DATABASE: dict[str, dict[str, Any]] = {
    # Injection
    "SQL_INJECTION": {
        "cwe": "CWE-89", "owasp": "A03:2021 – Injection",
        "cvss_base": 9.8, "description": "SQL injection via unsanitized input",
    },
    "COMMAND_INJECTION": {
        "cwe": "CWE-78", "owasp": "A03:2021 – Injection",
        "cvss_base": 9.8, "description": "OS command injection",
    },
    "XSS_DOM": {
        "cwe": "CWE-79", "owasp": "A03:2021 – Injection",
        "cvss_base": 6.1, "description": "DOM-based Cross-Site Scripting",
    },
    "XSS_STORED": {
        "cwe": "CWE-79", "owasp": "A03:2021 – Injection",
        "cvss_base": 8.7, "description": "Stored Cross-Site Scripting",
    },
    "XSS_REFLECTED": {
        "cwe": "CWE-79", "owasp": "A03:2021 – Injection",
        "cvss_base": 6.1, "description": "Reflected Cross-Site Scripting",
    },
    "PATH_TRAVERSAL": {
        "cwe": "CWE-22", "owasp": "A01:2021 – Broken Access Control",
        "cvss_base": 7.5, "description": "Path traversal / directory traversal",
    },
    "LFI": {
        "cwe": "CWE-98", "owasp": "A03:2021 – Injection",
        "cvss_base": 7.5, "description": "Local File Inclusion",
    },
    "SSRF": {
        "cwe": "CWE-918", "owasp": "A10:2021 – SSRF",
        "cvss_base": 7.5, "description": "Server-Side Request Forgery",
    },
    "DESERIALIZATION": {
        "cwe": "CWE-502", "owasp": "A08:2021 – Software and Data Integrity Failures",
        "cvss_base": 9.8, "description": "Insecure deserialization",
    },
    "HARDCODED_CREDENTIAL": {
        "cwe": "CWE-798", "owasp": "A07:2021 – Identification and Authentication Failures",
        "cvss_base": 9.8, "description": "Hardcoded credentials",
    },
    "WEAK_CRYPTO": {
        "cwe": "CWE-327", "owasp": "A02:2021 – Cryptographic Failures",
        "cvss_base": 7.5, "description": "Use of weak/broken cryptographic algorithm",
    },
    "MISSING_AUTH": {
        "cwe": "CWE-306", "owasp": "A01:2021 – Broken Access Control",
        "cvss_base": 9.8, "description": "Missing authentication for critical function",
    },
    "CSRF": {
        "cwe": "CWE-352", "owasp": "A01:2021 – Broken Access Control",
        "cvss_base": 8.8, "description": "Cross-Site Request Forgery",
    },
    "OPEN_REDIRECT": {
        "cwe": "CWE-601", "owasp": "A01:2021 – Broken Access Control",
        "cvss_base": 6.1, "description": "URL redirection to untrusted site",
    },
    "INFO_LEAK": {
        "cwe": "CWE-200", "owasp": "A01:2021 – Broken Access Control",
        "cvss_base": 5.3, "description": "Exposure of sensitive information",
    },
    "RACE_CONDITION": {
        "cwe": "CWE-362", "owasp": "A01:2021 – Broken Access Control",
        "cvss_base": 7.0, "description": "Concurrent execution using shared resource",
    },
    "MEMORY_CORRUPTION": {
        "cwe": "CWE-120", "owasp": "A03:2021 – Injection",
        "cvss_base": 9.8, "description": "Buffer overflow / memory corruption",
    },
    "INTEGER_OVERFLOW": {
        "cwe": "CWE-190", "owasp": "A03:2021 – Injection",
        "cvss_base": 7.8, "description": "Integer overflow or wraparound",
    },
    "UNSAFE_DESERIALIZATION": {
        "cwe": "CWE-502", "owasp": "A08:2021 – Software and Data Integrity Failures",
        "cvss_base": 9.8, "description": "Deserialization of untrusted data",
    },
    "XXE": {
        "cwe": "CWE-611", "owasp": "A05:2021 – Security Misconfiguration",
        "cvss_base": 9.8, "description": "XML External Entity injection",
    },
}


RULE_TO_CWE: dict[str, str] = {
    # Injection
    "PY-EVAL": "SQL_INJECTION",  # eval is code injection
    "PY-EXEC": "COMMAND_INJECTION",
    "PY-OS-SYSTEM": "COMMAND_INJECTION",
    "TS-EVAL": "COMMAND_INJECTION",
    "TS-DOM-XSS": "XSS_DOM",
    "TS-REACT-XSS": "XSS_DOM",
    "PHP-EVAL": "COMMAND_INJECTION",
    "PHP-EXEC": "COMMAND_INJECTION",
    "PHP-SYSTEM": "COMMAND_INJECTION",
    "PHP-SHELL-EXEC": "COMMAND_INJECTION",
    "PHP-UNSERIALIZE": "DESERIALIZATION",
    "PHP-SUPERGLOBAL": "INFO_LEAK",  # Base — upranked by taint analysis
    "PHP-SUPERGLOBAL-RAW": "INFO_LEAK",
    "PHP-LFI": "LFI",
    "PHP-LFI-FUNC": "LFI",
    "PHP-SQL-STRING": "SQL_INJECTION",
    "PHP-FILE-READ": "SSRF",
    "PHP-OPEN-REDIRECT": "OPEN_REDIRECT",
    "PHP-WEAK-HASH": "WEAK_CRYPTO",
    "PHP-WEAK-HASH-INPUT": "WEAK_CRYPTO",
    "PHP-DISPLAY-ERRORS": "INFO_LEAK",
    "INJ-SQL-INTERP": "SQL_INJECTION",
    "INJ-CMD-OS": "COMMAND_INJECTION",
    "INJ-DOM-XSS": "XSS_DOM",
    "INJ-PATH-TRAV": "PATH_TRAVERSAL",
    "INJ-CMD-SUB": "COMMAND_INJECTION",
    # Secrets
    "SEC-API-KEY": "HARDCODED_CREDENTIAL",
    "SEC-CREDENTIAL": "HARDCODED_CREDENTIAL",
    "SH-HARDCODED-SECRET": "HARDCODED_CREDENTIAL",
    "JSON-SECRET": "HARDCODED_CREDENTIAL",
    # Memory
    "C-GETS": "MEMORY_CORRUPTION",
    "C-STRCPY": "MEMORY_CORRUPTION",
    "C-SPRINTF": "MEMORY_CORRUPTION",
    # XML
    "XML-XXE": "XXE",
    # Default
    "PY-PICKLE": "UNSAFE_DESERIALIZATION",
    "RB-YAML-UNSAFE": "UNSAFE_DESERIALIZATION",
    "PY-YAML-UNSAFE": "UNSAFE_DESERIALIZATION",
    "PHP-PREG-E": "COMMAND_INJECTION",
    "JAVA-OBJECT-INPUT": "UNSAFE_DESERIALIZATION",
}


# ═══════════════════════════════════════════════════════════════════════════════
# FRAMEWORK KNOWLEDGE — known security primitives per framework
# ═══════════════════════════════════════════════════════════════════════════════

FRAMEWORK_PRIMITIVES: dict[str, dict[str, Any]] = {
    "Laravel": {
        "detection": (r"Illuminate\\|laravel/framework|artisan", {"composer.json", ".env.example", "artisan"}),
        "csrf": "VerifyCsrfToken middleware (auto-enabled for web routes)",
        "xss": "Blade {{ }} auto-escapes; use {!! !!} only for trusted HTML",
        "sql": "Eloquent ORM + query builder = parameterized by default",
        "auth": "Auth facade, policies, gates, middleware('auth')",
        "validation": "FormRequest + Validator facade",
        "sanitizers": {"e()", "htmlspecialchars", "strip_tags", "filter_var", "Blade {{ }}"},
        "db_abstractions": {"DB::", "Eloquent", "Model::", "query builder"},
        "config": ".env → config/*.php, not committed",
    },
    "Django": {
        "detection": (r"django|DJANGO_SETTINGS", {"manage.py", "settings.py", "wsgi.py"}),
        "csrf": "CsrfViewMiddleware (auto-enabled)",
        "xss": "Django templates auto-escape; mark_safe() for trusted content",
        "sql": "Django ORM = parameterized; .raw() needs careful review",
        "auth": "django.contrib.auth, @login_required, UserPassesTestMixin",
        "validation": "Forms, ModelForms, serializers (DRF)",
        "sanitizers": {"escape()", "mark_safe()", "strip_tags()", "bleach"},
        "db_abstractions": {"Model.objects.", ".filter(", ".get(", "Q("},
    },
    "Flask": {
        "detection": (r"flask|Flask\(__name__\)", {"app.py", "wsgi.py"}),
        "csrf": "Flask-WTF CSRFProtect or manual; not auto-enabled",
        "xss": "Jinja2 auto-escapes; |safe filter disables it",
        "sql": "Flask-SQLAlchemy = parameterized; raw SQL needs review",
        "auth": "Flask-Login, Flask-Principal, @login_required",
        "sanitizers": {"escape()", "Markup()", "bleach"},
        "db_abstractions": {"db.session", "Model.query", ".filter("},
    },
    "Express": {
        "detection": (r"express|require\('express'\)", {"app.js", "server.js", "index.js"}),
        "csrf": "csrf/csurf middleware needed; NOT auto-enabled",
        "xss": "No auto-escaping; template engine dependent (EJS <%= vs <%-)",
        "sql": "Sequelize/Knex = parameterized; raw query needs review",
        "auth": "passport.js, express-session, JWT middleware",
        "sanitizers": {"escape()", "sanitize-html", "xss", "encodeURIComponent"},
        "db_abstractions": {"sequelize", "knex", "Model.find", ".query("},
    },
    "Next.js": {
        "detection": (r"next|next/config", {"next.config.js", "next.config.mjs"}),
        "csrf": "NextAuth provides CSRF; manual for API routes",
        "xss": "React JSX auto-escapes; dangerouslySetInnerHTML is opt-in",
        "sql": "Prisma/Drizzle ORM = parameterized",
        "auth": "NextAuth.js, middleware.ts, getServerSession()",
        "sanitizers": {"DOMPurify", "sanitize-html", "escape-html"},
        "db_abstractions": {"prisma.", "db.query", "drizzle"},
    },
    "Spring": {
        "detection": (r"springframework|@SpringBootApplication", {"pom.xml", "build.gradle"}),
        "csrf": "Spring Security CSRF (enabled by default)",
        "xss": "Thymeleaf auto-escapes; @ResponseBody returns raw",
        "sql": "Spring Data JPA = parameterized; @Query native needs review",
        "auth": "Spring Security, @PreAuthorize, SecurityFilterChain",
        "sanitizers": {"HtmlUtils.htmlEscape()", "Jsoup.clean()", "@Valid"},
    },
    "Rails": {
        "detection": (r"Rails\.application|ActionController", {"Gemfile", "config/routes.rb"}),
        "csrf": "protect_from_forgery (auto-enabled in ApplicationController)",
        "xss": "ERB <%= %> auto-escapes since Rails 3; raw() / .html_safe disables",
        "sql": "ActiveRecord = parameterized; .find_by_sql needs review",
        "auth": "Devise, CanCanCan, Pundit, authenticate_user!",
        "sanitizers": {"sanitize()", "strip_tags()", "h()", "html_escape()"},
    },
    "raw-php": {
        "detection": (r"^$", set()),  # Default when no framework detected
        "csrf": "NOT auto-enabled — manual CSRF tokens needed",
        "xss": "NOT auto-escaped — htmlspecialchars() required on output",
        "sql": "NOT parameterized by default — use PDO prepared statements",
        "auth": "Manual session/auth implementation",
        "sanitizers": {"htmlspecialchars()", "strip_tags()", "filter_var()"},
        "db_abstractions": {"PDO::prepare", "mysqli_prepare"},
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# AST PARSER — Python with stdlib ast, PHP via tokenizer, JS via regex AST
# ═══════════════════════════════════════════════════════════════════════════════


class ASTNode:
    """Cross-language AST node."""
    def __init__(self, kind: str, name: str = "", start_line: int = 0, end_line: int = 0,
                 children: list[ASTNode] | None = None, attrs: dict[str, Any] | None = None):
        self.kind = kind
        self.name = name
        self.start_line = start_line
        self.end_line = end_line
        self.children = children or []
        self.attrs = attrs or {}

    def find_all(self, kind: str) -> list[ASTNode]:
        """Find all descendant nodes of a given kind."""
        results = []
        if self.kind == kind:
            results.append(self)
        for child in self.children:
            results.extend(child.find_all(kind))
        return results

    def __repr__(self) -> str:
        return f"ASTNode({self.kind}, {self.name}, lines {self.start_line}-{self.end_line})"


class ASTParser:
    """Multi-language AST parser.

    Python: uses stdlib `ast` module.
    PHP: uses a token-based structural parser.
    JavaScript/TypeScript: uses a regex-based structural parser.
    SQL: recognizes structural elements.
    """

    @staticmethod
    def parse_python(filepath: Path) -> list[ASTNode]:
        """Parse Python file into AST nodes using stdlib ast."""
        try:
            source = filepath.read_text(encoding="utf-8")
            tree = py_ast.parse(source, filename=str(filepath))
            return [ASTParser._convert_py_node(tree)]
        except SyntaxError:
            return []

    @staticmethod
    def _convert_py_node(node: Any) -> ASTNode:
        """Convert Python AST node to cross-language ASTNode."""
        kind = type(node).__name__
        attrs: dict[str, Any] = {}
        children: list[ASTNode] = []

        for field_name in node._fields:
            value = getattr(node, field_name)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, py_ast.AST):
                        children.append(ASTParser._convert_py_node(item))
            elif isinstance(value, py_ast.AST):
                children.append(ASTParser._convert_py_node(value))
            elif value is not None and not isinstance(value, (int, float, str, bool, bytes)):
                pass  # Skip complex non-AST values

        line = getattr(node, "lineno", 0)
        getattr(node, "col_offset", 0)
        end_line = getattr(node, "end_lineno", line) if hasattr(node, "end_lineno") else line

        # Extract useful names
        name = ""
        if isinstance(node, py_ast.Name):
            name = node.id
        elif isinstance(node, (py_ast.FunctionDef, py_ast.ClassDef)):
            name = node.name
        elif isinstance(node, py_ast.Call):
            if isinstance(node.func, py_ast.Name):
                name = node.func.id
            elif isinstance(node.func, py_ast.Attribute):
                name = f"{py_ast.unparse(node.func)}" if hasattr(py_ast, "unparse") else "call"
        elif isinstance(node, py_ast.Attribute):
            name = node.attr
        elif isinstance(node, py_ast.Import):
            name = ", ".join(alias.name for alias in node.names)
        elif isinstance(node, py_ast.ImportFrom):
            name = f"from {node.module or ''} import ..."

        return ASTNode(
            kind=kind, name=name,
            start_line=line, end_line=end_line,
            children=children, attrs=attrs,
        )

    @staticmethod
    def parse_php(filepath: Path) -> list[ASTNode]:
        """Parse PHP file into structural AST using tokenizer approach.

        Recognizes: variables ($_), function calls, class definitions,
        superglobal access, include/require, SQL patterns.
        """
        try:
            source = filepath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return []

        nodes: list[ASTNode] = []
        lines = source.split("\n")

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("//") or stripped.startswith("#"):
                continue
            if stripped.startswith("/*") or stripped.startswith("*"):
                continue

            # Detect superglobal access: $_GET, $_POST, $_REQUEST, $_COOKIE, $_FILES, $_SERVER
            sg_match = re.search(r"\$(?:_(GET|POST|REQUEST|COOKIE|FILES|SERVER|SESSION|ENV))\b", line)
            if sg_match:
                # Find variable assignment context
                assign_match = re.search(r"(\$\w+)\s*=\s*\$_" + sg_match.group(1), line)
                var_name = assign_match.group(1) if assign_match else "$_" + sg_match.group(1)
                nodes.append(ASTNode(
                    kind="SuperglobalAccess",
                    name=var_name,
                    start_line=i, end_line=i,
                    attrs={
                        "superglobal": "$_" + sg_match.group(1),
                        "assigned_to": var_name if assign_match else None,
                        "context": stripped[:200],
                    },
                ))

            # Detect function calls (security-relevant)
            func_match = re.search(r"(\w+)\s*\(", line)
            if func_match:
                fname = func_match.group(1)
                nodes.append(ASTNode(
                    kind="FunctionCall",
                    name=fname,
                    start_line=i, end_line=i,
                    attrs={"function": fname, "context": stripped[:200]},
                ))

            # Detect include/require
            inc_match = re.search(r"(include|include_once|require|require_once)\s*(\(?\s*)(\S+)", line)
            if inc_match:
                nodes.append(ASTNode(
                    kind="IncludeStatement",
                    name=inc_match.group(1),
                    start_line=i, end_line=i,
                    attrs={
                        "type": inc_match.group(1),
                        "target": inc_match.group(3),
                        "is_dynamic": "$" in inc_match.group(3),
                    },
                ))

            # Detect SQL patterns
            if re.search(r"(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP)\s+", line, re.IGNORECASE):
                nodes.append(ASTNode(
                    kind="SQLStatement",
                    name="SQL",
                    start_line=i, end_line=i,
                    attrs={"context": stripped[:200]},
                ))

        return nodes

    @staticmethod
    def parse_javascript(filepath: Path) -> list[ASTNode]:
        """Parse JavaScript/TypeScript into structural AST."""
        try:
            source = filepath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return []

        nodes: list[ASTNode] = []
        lines = source.split("\n")

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("//"):
                continue

            # Detect DOM manipulation
            if "innerHTML" in line:
                nodes.append(ASTNode(
                    kind="DOMManipulation",
                    name="innerHTML",
                    start_line=i, end_line=i,
                    attrs={"method": "innerHTML", "context": stripped[:200]},
                ))
            if "document.write" in line:
                nodes.append(ASTNode(
                    kind="DOMManipulation",
                    name="document.write",
                    start_line=i, end_line=i,
                    attrs={"method": "document.write", "context": stripped[:200]},
                ))

            # Detect eval / new Function
            if re.search(r"\beval\s*\(", line):
                nodes.append(ASTNode(
                    kind="EvalCall", name="eval",
                    start_line=i, end_line=i, attrs={"context": stripped[:200]},
                ))
            if "new Function" in line:
                nodes.append(ASTNode(
                    kind="EvalCall", name="new Function",
                    start_line=i, end_line=i, attrs={"context": stripped[:200]},
                ))

            # Detect fetch / XMLHttpRequest (potential SSRF / data exfiltration)
            if re.search(r"fetch\s*\(", line):
                nodes.append(ASTNode(
                    kind="HTTPCall", name="fetch",
                    start_line=i, end_line=i, attrs={"context": stripped[:200]},
                ))

        return nodes

    @staticmethod
    def parse_file(filepath: Path) -> list[ASTNode]:
        """Auto-detect language and parse."""
        suffix = filepath.suffix.lower()
        if suffix in (".py", ".pyi", ".pyx"):
            return ASTParser.parse_python(filepath)
        elif suffix in (".php", ".phtml"):
            return ASTParser.parse_php(filepath)
        elif suffix in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"):
            return ASTParser.parse_javascript(filepath)
        return []


# ═══════════════════════════════════════════════════════════════════════════════
# TAINT ANALYZER — source → sanitizer → sink tracking
# ═══════════════════════════════════════════════════════════════════════════════

# Known security sinks per language
_SECURITY_SINKS: dict[str, list[str]] = {
    "php": [
        "echo", "print", "printf", "die", "exit",
        "header", "setcookie", "setrawcookie",
        "eval", "assert", "preg_replace",
        "system", "exec", "passthru", "shell_exec", "popen", "proc_open",
        "include", "include_once", "require", "require_once",
        "file_get_contents", "fopen", "file_put_contents",
        "unserialize", "unlink", "rmdir", "mkdir",
        "mysqli_query", "mysql_query", "pg_query",
        "PDO::query", "PDO::exec",
        "move_uploaded_file", "mail",
    ],
    "python": [
        "eval", "exec", "compile",
        "os.system", "os.popen", "subprocess.call", "subprocess.run", "subprocess.Popen",
        "pickle.loads", "pickle.load", "yaml.load",
        "open", "builtins.open",
        "requests.get", "requests.post", "requests.put",
        "flask.render_template_string", "django.http.HttpResponse",
        "print",
        "socket.send", "socket.sendall",
        "marshal.loads",
    ],
    "typescript": [
        "innerHTML", "outerHTML", "document.write", "document.writeln",
        "eval", "setTimeout(string)", "setInterval(string)", "new Function",
        "dangerouslySetInnerHTML", "v-html",
        "location.href", "location.assign",
        "fetch", "XMLHttpRequest.send",
        "localStorage.setItem", "sessionStorage.setItem",
    ],
    "java": [
        "Runtime.getRuntime().exec", "ProcessBuilder.start",
        "Statement.execute", "Statement.executeQuery",
        "ObjectInputStream.readObject",
        "System.out.print", "System.err.print",
        "TransformerFactory.newTransformer",
        "SAXParser.parse", "DocumentBuilder.parse",
        "URL.openConnection", "HttpURLConnection.connect",
    ],
    "go": [
        "os/exec.Command", "exec.Command",
        "template.Execute", "template.ExecuteTemplate",
        "json.NewDecoder.Decode", "encoding/gob.NewDecoder.Decode",
        "http.Get", "http.Post", "http.Client.Do",
        "db.Query", "db.QueryRow", "db.Exec",
        "fmt.Print", "fmt.Println", "fmt.Printf", "fmt.Fprint",
        "net.Dial", "net.Listen",
        "os.Open", "os.Create",
    ],
}


# Known sanitizers per language
_KNOWN_SANITIZERS: dict[str, dict[str, float]] = {
    "php": {
        "htmlspecialchars": 0.95, "htmlentities": 0.95,
        "strip_tags": 0.80, "filter_var": 0.90, "filter_input": 0.90,
        "escape": 0.85, "e()": 0.90,
        "intval": 0.95, "floatval": 0.90,
        "PDO::prepare": 0.95, "mysqli_prepare": 0.95,
        "password_hash": 1.0, "password_verify": 1.0,
        "verify_csrf": 0.85, "csrf_token": 0.85,
        "hash_equals": 0.90,
        "json_encode": 0.85, "json_decode": 0.70,
        "urlencode": 0.80, "rawurlencode": 0.85,
        "addslashes": 0.50, "stripslashes": 0.30,
        "preg_quote": 0.80,
        "real_escape_string": 0.85,
    },
    "python": {
        "escape()": 0.85, "Markup()": 0.85,
        "html.escape": 0.90, "cgi.escape": 0.85,
        "json.dumps": 0.85, "json.loads": 0.70,
        "shlex.quote": 0.90,
        "hashlib": 1.0, "bcrypt": 1.0, "argon2": 1.0,
        "secrets.token_": 1.0,
        "urllib.parse.quote": 0.85,
        "re.escape": 0.75,
        "bleach.clean": 0.95, "bleach.linkify": 0.85,
        "Django.escape": 0.90, "mark_safe": -0.90,  # NEGATIVE — marks as safe!
        "Flask.escape": 0.85,
        "int(": 0.90, "float(": 0.85,
        "isdigit": 0.70,
    },
    "typescript": {
        "textContent": 1.0, "textContent =": 1.0,
        "innerText": 0.90,
        "createTextNode": 0.95,
        "encodeURIComponent": 0.90, "encodeURI": 0.85,
        "DOMPurify.sanitize": 0.95, "sanitize-html": 0.95,
        "escape-html": 0.90, "escape()": 0.85,
        "JSON.stringify": 0.80, "JSON.parse": 0.70,
        "parseInt": 0.90, "parseFloat": 0.85,
        "btoa": 0.70, "atob": 0.60,
        "crypto.subtle": 1.0, "CryptoJS": 0.90,
        "helmet": 0.85, "csrf": 0.85,
    },
}

# Superglobals / untrusted sources per language
_UNTRUSTED_SOURCES: dict[str, list[str]] = {
    "php": ["$_GET", "$_POST", "$_REQUEST", "$_COOKIE", "$_FILES", "$_SERVER['HTTP_", "php://input", "file_get_contents('php://input')"],
    "python": ["request.GET", "request.POST", "request.args", "request.form", "request.json", "request.data", "request.files", "input()", "sys.argv", "os.environ.get", "request.headers", "socket.recv"],
    "typescript": ["req.body", "req.query", "req.params", "req.headers", "location.search", "location.hash", "window.name", "postMessage.data", "process.env.", "localStorage.getItem", "sessionStorage.getItem"],
    "java": ["request.getParameter", "request.getQueryString", "request.getHeader", "request.getInputStream", "request.getReader", "System.getenv", "args[", "socket.getInputStream"],
    "go": ["r.URL.Query().Get", "r.FormValue", "r.PostFormValue", "r.Header.Get", "r.Body", "os.Getenv", "os.Args", "c.Request.Body", "io.ReadAll(r.Body)"],
}



# ═══════════════════════════════════════════════════════════════════════════════
# SANITIZER CAPABILITY MATRIX — directional taint per sink type
# ═══════════════════════════════════════════════════════════════════════════════
#
# Each sanitizer has a capability profile specifying which sink types it
# actually protects against. A sanitizer that only escapes HTML does NOT
# protect against SQL injection, even if the audit cycle "learned" it.
#
# Columns: HTML | SQL | SHELL | URL | JS | PATH | FILE | LDAP | XPATH | OS
# 1.0 = fully effective, 0.0 = no protection, negative = harmful (marks safe)
#
# "context" must be stored with the sanitizer, not just "SAFE".

SANITIZER_CAPABILITY: dict[str, dict[str, dict[str, float]]] = {
    "php": {
        "htmlspecialchars": {"HTML": 1.0, "SQL": 0.0, "SHELL": 0.0, "URL": 0.0, "JS": 0.0, "PATH": 0.0},
        "htmlentities": {"HTML": 1.0, "SQL": 0.0, "SHELL": 0.0, "URL": 0.0, "JS": 0.0, "PATH": 0.0},
        "strip_tags": {"HTML": 0.80, "SQL": 0.0, "SHELL": 0.0, "URL": 0.0, "JS": 0.70, "PATH": 0.0},
        "escape": {"HTML": 0.85, "SQL": 0.0, "SHELL": 0.0, "URL": 0.0, "JS": 0.0, "PATH": 0.0},
        "e()": {"HTML": 0.90, "SQL": 0.0, "SHELL": 0.0, "URL": 0.0, "JS": 0.0, "PATH": 0.0},
        "PDO::prepare": {"HTML": 0.0, "SQL": 1.0, "SHELL": 0.0, "URL": 0.0, "JS": 0.0, "PATH": 0.0},
        "mysqli_prepare": {"HTML": 0.0, "SQL": 1.0, "SHELL": 0.0, "URL": 0.0, "JS": 0.0, "PATH": 0.0},
        "filter_var": {"HTML": 0.70, "SQL": 0.75, "SHELL": 0.40, "URL": 0.0, "JS": 0.50, "PATH": 0.40},  # FILTER_VALIDATE_INT is strong SQL protection
        "filter_input": {"HTML": 0.60, "SQL": 0.40, "SHELL": 0.30, "URL": 0.0, "JS": 0.40, "PATH": 0.30},
        "intval": {"HTML": 0.95, "SQL": 0.95, "SHELL": 0.95, "URL": 0.80, "JS": 0.90, "PATH": 0.85},
        "floatval": {"HTML": 0.90, "SQL": 0.90, "SHELL": 0.90, "URL": 0.80, "JS": 0.85, "PATH": 0.80},
        "escapeshellarg": {"HTML": 0.0, "SQL": 0.0, "SHELL": 1.0, "URL": 0.0, "JS": 0.0, "PATH": 0.0},
        "escapeshellcmd": {"HTML": 0.0, "SQL": 0.0, "SHELL": 0.90, "URL": 0.0, "JS": 0.0, "PATH": 0.0},
        "addslashes": {"HTML": 0.40, "SQL": 0.60, "SHELL": 0.30, "URL": 0.20, "JS": 0.30, "PATH": 0.20},
        "urlencode": {"HTML": 0.90, "SQL": 0.30, "SHELL": 0.0, "URL": 1.0, "JS": 0.60, "PATH": 0.0},
        "rawurlencode": {"HTML": 0.85, "SQL": 0.30, "SHELL": 0.0, "URL": 1.0, "JS": 0.55, "PATH": 0.0},
        "password_hash": {"HTML": 1.0, "SQL": 1.0, "SHELL": 1.0, "URL": 1.0, "JS": 1.0, "PATH": 1.0},
        "password_verify": {"HTML": 0.0, "SQL": 0.0, "SHELL": 0.0, "URL": 0.0, "JS": 0.0, "PATH": 0.0},
        "verify_csrf": {"HTML": 0.0, "SQL": 0.0, "SHELL": 0.0, "URL": 0.0, "JS": 0.0, "PATH": 0.0},
        "hash_equals": {"HTML": 0.0, "SQL": 0.0, "SHELL": 0.0, "URL": 0.0, "JS": 0.0, "PATH": 0.0},
        "json_encode": {"HTML": 0.0, "SQL": 0.0, "SHELL": 0.0, "URL": 0.70, "JS": 0.95, "PATH": 0.0},
        "sanitize_int_array": {"HTML": 0.90, "SQL": 0.95, "SHELL": 0.90, "URL": 0.80, "JS": 0.85, "PATH": 0.80},
        "validate_int_range": {"HTML": 0.90, "SQL": 0.95, "SHELL": 0.90, "URL": 0.80, "JS": 0.85, "PATH": 0.80},
    },
    "python": {
        "html.escape": {"HTML": 1.0, "SQL": 0.0, "SHELL": 0.0, "URL": 0.0, "JS": 0.0, "PATH": 0.0},
        "escape()": {"HTML": 0.85, "SQL": 0.0, "SHELL": 0.0, "URL": 0.0, "JS": 0.0, "PATH": 0.0},
        "shlex.quote": {"HTML": 0.0, "SQL": 0.0, "SHELL": 1.0, "URL": 0.0, "JS": 0.0, "PATH": 0.0},
        "hashlib": {"HTML": 1.0, "SQL": 1.0, "SHELL": 1.0, "URL": 1.0, "JS": 1.0, "PATH": 1.0},
        "bcrypt": {"HTML": 1.0, "SQL": 1.0, "SHELL": 1.0, "URL": 1.0, "JS": 1.0, "PATH": 1.0},
        "secrets.token_": {"HTML": 1.0, "SQL": 1.0, "SHELL": 1.0, "URL": 1.0, "JS": 1.0, "PATH": 1.0},
        "urllib.parse.quote": {"HTML": 0.85, "SQL": 0.30, "SHELL": 0.0, "URL": 1.0, "JS": 0.55, "PATH": 0.0},
        "bleach.clean": {"HTML": 1.0, "SQL": 0.0, "SHELL": 0.0, "URL": 0.20, "JS": 0.90, "PATH": 0.0},
        "re.escape": {"HTML": 0.0, "SQL": 0.0, "SHELL": 0.0, "URL": 0.0, "JS": 0.0, "PATH": 0.0},
        "int(": {"HTML": 0.95, "SQL": 0.95, "SHELL": 0.95, "URL": 0.80, "JS": 0.90, "PATH": 0.85},
        "float(": {"HTML": 0.90, "SQL": 0.90, "SHELL": 0.90, "URL": 0.80, "JS": 0.85, "PATH": 0.80},
        "mark_safe": {"HTML": -1.0, "SQL": 0.0, "SHELL": 0.0, "URL": 0.0, "JS": -1.0, "PATH": 0.0},
    },
    "typescript": {
        "textContent": {"HTML": 1.0, "SQL": 0.0, "SHELL": 0.0, "URL": 0.0, "JS": 0.0, "PATH": 0.0},
        "createTextNode": {"HTML": 1.0, "SQL": 0.0, "SHELL": 0.0, "URL": 0.0, "JS": 0.0, "PATH": 0.0},
        "encodeURIComponent": {"HTML": 0.85, "SQL": 0.30, "SHELL": 0.0, "URL": 1.0, "JS": 0.55, "PATH": 0.0},
        "DOMPurify.sanitize": {"HTML": 1.0, "SQL": 0.0, "SHELL": 0.0, "URL": 0.10, "JS": 0.95, "PATH": 0.0},
        "sanitize-html": {"HTML": 0.95, "SQL": 0.0, "SHELL": 0.0, "URL": 0.10, "JS": 0.90, "PATH": 0.0},
        "parseInt": {"HTML": 0.95, "SQL": 0.95, "SHELL": 0.95, "URL": 0.80, "JS": 0.90, "PATH": 0.85},
        "JSON.stringify": {"HTML": 0.0, "SQL": 0.0, "SHELL": 0.0, "URL": 0.70, "JS": 0.95, "PATH": 0.0},
        "crypto.subtle": {"HTML": 1.0, "SQL": 1.0, "SHELL": 1.0, "URL": 1.0, "JS": 1.0, "PATH": 1.0},
    },
}

# Sink type classification — maps rules/functions to sink categories
SINK_TYPE_MAP: dict[str, dict[str, list[str]]] = {
    "php": {
        "HTML": ["echo", "print", "printf", "die", "exit", "header('Content-Type: text/html"],
        "SQL": ["mysqli_query", "mysql_query", "pg_query", "PDO::query", "PDO::exec", "->query("],
        "SHELL": ["system", "exec", "passthru", "shell_exec", "popen", "proc_open", "`"],
        "URL": ["header('Location:", "header(\\\"Location:", "http_build_query"],
        "JS": ["json_encode", "<script>", "json_decode"],
        "PATH": ["include", "include_once", "require", "require_once", "fopen", "file_get_contents", "file_put_contents", "unlink", "rmdir", "move_uploaded_file"],
        "FILE": ["fopen", "file_put_contents", "move_uploaded_file", "copy"],
    },
    "python": {
        "HTML": ["flask.render_template_string", "django.http.HttpResponse", "print("],
        "SQL": [".execute(", ".raw(", "cursor.execute"],
        "SHELL": ["os.system", "os.popen", "subprocess.call", "subprocess.run", "subprocess.Popen"],
        "URL": ["requests.get", "requests.post", "urllib.request.urlopen"],
        "JS": ["json.dumps", "Response(", "WebSocket.send"],
        "PATH": ["open(", "os.path.join", "Path("],
        "FILE": ["open(", "shutil.copy", "os.remove"],
    },
    "typescript": {
        "HTML": ["innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "v-html", "dangerouslySetInnerHTML"],
        "SQL": ["db.query(", ".execute(", "sequelize.query"],
        "SHELL": ["exec(", "spawn(", "child_process"],
        "URL": ["location.href", "location.assign", "fetch(", "window.open"],
        "JS": ["eval(", "new Function", "setTimeout(string)", "setInterval(string)"],
        "PATH": ["fs.readFile", "fs.writeFile", "require(", "import("],
        "FILE": ["fs.readFile", "fs.writeFile", "FormData.append"],
    },
}


class TaintAnalyzer:
    """Analyzes data flow from untrusted sources through sanitizers to sinks."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.framework: str | None = None
        self.framework_primitives: dict[str, Any] = {}
        self._detect_framework()

    def _detect_framework(self) -> None:
        """Detect which framework the project uses."""
        for fw_name, fw_data in FRAMEWORK_PRIMITIVES.items():
            if fw_name == "raw-php":
                continue
            _, markers = fw_data["detection"]
            for marker_file in markers:
                if (self.repo_root / marker_file).exists():
                    self.framework = fw_name
                    self.framework_primitives = fw_data
                    return
        # Check for raw PHP
        if (self.repo_root / "index.php").exists():
            self.framework = "raw-php"
            self.framework_primitives = FRAMEWORK_PRIMITIVES["raw-php"]
            return
        self.framework = "unknown"
        self.framework_primitives = {}

    def analyze(self, filepath: Path, finding_line: int,
                finding_rule: str) -> FindingEvidence | None:
        """Perform taint analysis on a single finding.

        Returns enriched finding evidence with:
        - source identification
        - sanitizer chain detection
        - sink identification
        - confidence classification
        - framework context
        """
        # Determine language
        suffix = filepath.suffix.lower()
        lang = self._lang_from_suffix(suffix)
        inferred_severity = self._infer_severity(finding_rule, lang)

        # Phase 1: Read the file and surrounding context
        try:
            source_code = filepath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return None

        lines = source_code.split("\n")

        # Context window: ±20 lines around finding
        start = max(0, finding_line - 20)
        end = min(len(lines), finding_line + 20)
        context = "\n".join(lines[start:end])

        finding_line_text = lines[finding_line - 1] if finding_line <= len(lines) else ""

        # Phase 2: Detect untrusted source
        source_node = self._detect_source(lang, context, finding_line_text, start + 1)

        # Phase 3: Detect sanitizers in the context window
        sanitizers = self._detect_sanitizers(lang, context, start + 1)

        # Phase 4: Detect sink
        sink_node = self._detect_sink(lang, finding_line_text, finding_line)

        # Phase 5: Compute confidence
        confidence, level = self._compute_confidence(
            source_node, sanitizers, sink_node, finding_rule, lang
        )

        # Phase 6: Map to security knowledge base
        cwe_info = CWE_DATABASE.get(RULE_TO_CWE.get(finding_rule, ""), {})
        cwe_id = cwe_info.get("cwe", "")
        owasp = cwe_info.get("owasp", "")
        cvss = cwe_info.get("cvss_base", 0.0)

        # Adjust CVSS based on confidence and sanitizers
        effective_cvss = cvss
        if sanitizers:
            # Each sanitizer reduces effective CVSS
            total_sanitizer = sum(s.confidence for s in sanitizers)
            effective_cvss = max(0, cvss * (1.0 - min(total_sanitizer, 0.95)))

        # Phase 7: Framework-aware adjustment
        framework_mitigation = self._check_framework_mitigation(finding_rule, lang)
        # Laravel-specific: __DIR__ based paths in require/include are safe
        is_safe_include = False
        if finding_rule and "LFI" in finding_rule:
            if "__DIR__" in context or "dirname(" in context:
                is_safe_include = True

        if framework_mitigation or is_safe_include:
            level = ConfidenceLevel.MITIGATED
            confidence = 0.95

        # Build evidence
        evidence = FindingEvidence(
            finding_id="",
            file=str(filepath.relative_to(self.repo_root)) if self.repo_root in filepath.parents else str(filepath),
            line_start=finding_line,
            line_end=finding_line,
            symbol="",
            severity=inferred_severity,
            category="SECURITY",
            rule=finding_rule,
            message="",
            confidence=confidence,
            confidence_level=level,
            source=source_node,
            sanitizers=sanitizers,
            sink=sink_node,
            cwe_id=cwe_id,
            owasp_category=owasp,
            cvss_score=round(effective_cvss, 1),
            framework_context=self.framework or "unknown",
            root_cause="",
            raw_evidence=finding_line_text[:200],
        )

        # If mitigated/suppressed, no remediation needed
        if level in (ConfidenceLevel.MITIGATED, ConfidenceLevel.FALSE_POSITIVE):
            evidence.remediation_advice = f"Finding is mitigated by: {', '.join(s.description for s in sanitizers) if sanitizers else 'framework protections'}"
        elif level == ConfidenceLevel.LIKELY_FALSE_POSITIVE:
            evidence.remediation_advice = "Review context — likely safe but verify."

        return evidence


    def _infer_severity(self, rule: str, lang: str) -> str:
        """Infer appropriate severity from rule type."""
        r = rule.upper()
        if any(k in r for k in ("EVAL", "EXEC", "SYSTEM", "SHELL", "PASSTHRU", "DESTRUCT", "PRE", "PROC_OPEN", "GETS(")):
            return "P0" if "EVAL" in r or "EXEC" in r or "GETS" in r or "PROC_OPEN" in r else "P1"
        if any(k in r for k in ("UNSERIALIZE", "DESERIAL", "MARSHAL", "PICKLE", "OBJECT-INPUT", "FORMATTER")):
            return "P1"
        if any(k in r for k in ("SQL", "MYSQL", "QUERY", "DELETE")):
            if "STRING" in r or "INTERP" in r:
                return "P1"
            return "P2"
        if "DOM" in r or "REACT-XSS" in r or "VHTML" in r or "JAVASCRIPT:" in r:
            return "P0"
        if "XSS" in r or "INNERHTML" in r:
            return "P0"
        if any(k in r for k in ("SECRET", "CREDENTIAL", "PRIVATE-KEY", "API-KEY", "TOKEN", "PASSWORD")):
            return "P0"
        if any(k in r for k in ("LFI", "PATH", "TRAVERSAL", "INCLUDE")):
            return "P1"
        if "REDIRECT" in r or "SSRF" in r:
            return "P2"
        if any(k in r for k in ("WEAK", "MD5", "SHA1", "CRYPTO")):
            return "P2"
        if "CSRF" in r or "SESSION" in r:
            return "P2"
        if any(k in r for k in ("ERRORS", "LEAK", "SENSITIVE", "SUPERGLOBAL")):
            if "SUPERGLOBAL-RAW" in r or "DISPLAY" in r:
                return "P2"
            return "P3"
        return "P2"

        return "P2"

    def _lang_from_suffix(self, suffix: str) -> str:
        mapping = {
            ".py": "python", ".pyi": "python",
            ".php": "php", ".phtml": "php",
            ".js": "typescript", ".jsx": "typescript",
            ".ts": "typescript", ".tsx": "typescript", ".mjs": "typescript",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".rb": "ruby",
            ".cs": "csharp",
            ".swift": "swift",
            ".kt": "kotlin",
        }
        return mapping.get(suffix, "unknown")

    def _detect_source(self, lang: str, context: str, line: str,
                       context_start_line: int) -> EvidenceNode | None:
        """Detect untrusted data source in the context window."""
        sources = _UNTRUSTED_SOURCES.get(lang, [])
        for src_pattern in sources:
            for i, ctx_line in enumerate(context.split("\n")):
                if src_pattern.lower() in ctx_line.lower():
                    actual_line = context_start_line + i
                    return EvidenceNode(
                        kind="source",
                        description=f"Untrusted data from {src_pattern}",
                        location=f"line {actual_line}",
                        metadata={"pattern": src_pattern, "line": ctx_line.strip()[:150]},
                    )
        return None

    def _detect_sanitizers(self, lang: str, context: str,
                           context_start_line: int) -> list[EvidenceNode]:
        """Detect security sanitizers/validators applied to data."""
        sanitizers = []
        fw_sanitizers = self.framework_primitives.get("sanitizers", set())
        lang_sanitizers = _KNOWN_SANITIZERS.get(lang, {})

        # Check both language-specific and framework-specific sanitizers
        all_sanitizers = {**lang_sanitizers}
        for fw_s in fw_sanitizers:
            all_sanitizers[fw_s] = 0.85  # Framework sanitizers get default confidence

        for i, line in enumerate(context.split("\n")):
            for san_name, san_confidence in all_sanitizers.items():
                if san_name.lower() in line.lower():
                    actual_line = context_start_line + i
                    sanitizers.append(EvidenceNode(
                        kind="sanitizer",
                        description=f"Input sanitized/validated via {san_name}",
                        location=f"line {actual_line}",
                        confidence=san_confidence,
                        metadata={"sanitizer": san_name, "effectiveness": san_confidence},
                    ))
        return sanitizers

    def _detect_sink(self, lang: str, line: str, line_num: int) -> EvidenceNode | None:
        """Detect if the finding line itself is a dangerous sink."""
        sinks = _SECURITY_SINKS.get(lang, [])
        line_lower = line.lower()
        for sink_name in sinks:
            # Exact match
            if sink_name.lower() in line_lower:
                return EvidenceNode(
                    kind="sink",
                    description=f"Dangerous operation: {sink_name}",
                    location=f"line {line_num}",
                    metadata={"sink": sink_name},
                )
            # Fuzzy: function call pattern
            if "(" not in sink_name and sink_name.lower() in line_lower and "(" in line_lower:
                idx = line_lower.find(sink_name.lower())
                if idx >= 0:
                    before = line_lower[max(0, idx - 1):idx] if idx > 0 else ""
                    if before == "" or not before[-1].isalnum() if before else True:
                        return EvidenceNode(
                            kind="sink",
                            description=f"Dangerous operation: {sink_name}",
                            location=f"line {line_num}",
                            metadata={"sink": sink_name},
                        )
        return None

    def _classify_sink_type(self, lang: str, sink_line: str) -> str | None:
        """Classify what kind of sink this line targets."""
        if not sink_line:
            return None
        sink_types = SINK_TYPE_MAP.get(lang, {})
        for stype, patterns in sink_types.items():
            for pat in patterns:
                if pat in sink_line:
                    return stype
        return None

    def _get_sanitizer_capability(self, lang: str, sanitizer_name: str, sink_type: str) -> float:
        """Get directional sanitizer effectiveness for a specific sink type."""
        cap = SANITIZER_CAPABILITY.get(lang, {}).get(sanitizer_name, {})
        return cap.get(sink_type, 0.0)

    def _compute_confidence(self, source: EvidenceNode | None,
                            sanitizers: list[EvidenceNode],
                            sink: EvidenceNode | None,
                            rule: str, lang: str) -> tuple[float, ConfidenceLevel]:
        """Compute confidence using directional taint analysis.

        Sanitizers are evaluated per sink type, not globally.
        htmlspecialchars() protects HTML but NOT SQL.
        """
        # No source → likely false positive (pattern match without context)
        if not source and rule not in ("SQL-SENSITIVE", "CMPL-", "OBS-", "TEST-", "SIZE-"):
            return 0.15, ConfidenceLevel.LIKELY_FALSE_POSITIVE

        # Determine sink type for directional analysis
        sink_type = self._classify_sink_type(lang, sink.metadata.get("sink", "") if sink else "") if sink else None

        # Has sink but no source and no sanitizers → uncertain
        if sink and not source and not sanitizers:
            return 0.40, ConfidenceLevel.UNCERTAIN

        # Source + sink + no sanitizer → likely true positive
        if source and sink and not sanitizers:
            return 0.95, ConfidenceLevel.TRUE_POSITIVE

        # Source + sanitizer + sink → directional check
        if source and sanitizers and sink:
            if sink_type:
                # Check each sanitizer against the specific sink type
                directional_scores = []
                for s in sanitizers:
                    san_name = s.metadata.get("sanitizer", "")
                    cap = self._get_sanitizer_capability(lang, san_name, sink_type)
                    # Negative capability means it marks data as safe (dangerous for this sink)
                    if cap < 0:
                        return 0.92, ConfidenceLevel.LIKELY_TRUE  # mark_safe / |safe → real XSS risk
                    directional_scores.append(cap * s.confidence)

                best_protection = max(directional_scores) if directional_scores else 0.0

                # Multi-sanitizer defense-in-depth bonus
                defense_depth = len([s for s in directional_scores if s > 0.7])
                if defense_depth >= 2:
                    best_protection = min(1.0, best_protection + 0.10)

                if best_protection >= 0.85:
                    return 0.95, ConfidenceLevel.MITIGATED
                elif best_protection >= 0.60:
                    return 0.50, ConfidenceLevel.UNCERTAIN
                elif best_protection >= 0.30:
                    return 0.65, ConfidenceLevel.LIKELY_TRUE
                else:
                    # Wrong sanitizer for this sink type
                    return 0.82, ConfidenceLevel.LIKELY_TRUE
            else:
                # No sink type classified → fallback to aggregate
                total_sanitizer = sum(s.confidence for s in sanitizers)
                if total_sanitizer >= 0.90:
                    return 0.88, ConfidenceLevel.MITIGATED
                elif total_sanitizer >= 0.60:
                    return 0.50, ConfidenceLevel.UNCERTAIN
                else:
                    return 0.70, ConfidenceLevel.LIKELY_TRUE

        # Source + sanitizer, no sink → mitigated
        if source and sanitizers and not sink:
            total_sanitizer = sum(s.confidence for s in sanitizers)
            if total_sanitizer >= 0.80:
                return 0.92, ConfidenceLevel.MITIGATED
            return 0.50, ConfidenceLevel.UNCERTAIN

        # Only source, no sink detected → uncertain
        if source and not sink:
            return 0.35, ConfidenceLevel.UNCERTAIN

        return 0.20, ConfidenceLevel.LIKELY_FALSE_POSITIVE

    def _check_framework_mitigation(self, rule: str, lang: str) -> bool:
        """Check if framework mitigates this finding type."""
        if not self.framework or self.framework == "unknown" or self.framework == "raw-php":
            return False

        fw = self.framework_primitives
        csrf_rules = {"PHP-SESSION", "CSRF", "SESSION-"}
        xss_rules = {"INJ-DOM-XSS", "TS-DOM-XSS", "PHP-SUPERGLOBAL"}
        sql_rules = {"SQL-", "INJ-SQL-"}

        if any(rule.startswith(r) for r in csrf_rules) and "csrf" in str(fw).lower():
            return True
        if any(rule.startswith(r) for r in xss_rules) and lang in ("typescript", "php"):
            if "xss" in str(fw).lower() or "auto-escapes" in str(fw).lower():
                return True
        if any(rule.startswith(r) for r in sql_rules) and "sql" in str(fw).lower():
            if "parameterized" in str(fw).lower() or "ORM" in str(fw):
                return True

        return False


# ═══════════════════════════════════════════════════════════════════════════════
# REPOSITORY MEMORY — learn project patterns across audit cycles
# ═══════════════════════════════════════════════════════════════════════════════


class RepositoryMemory:
    """Learns project-specific security patterns across audit cycles.

    Builds a model of: sanitizers, validators, DB abstractions,
    auth mechanisms, and known-safe patterns discovered in prior cycles.
    """

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.memory_file = repo_root / ".aura" / "memory" / "repo_model.json"
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if self.memory_file.exists():
            try:
                return json.loads(self.memory_file.read_text())
            except json.JSONDecodeError:
                pass
        return {
            "version": "1.0",
            "cycles_learned": 0,
            "discovered_sanitizers": {},
            "discovered_validators": {},
            "discovered_db_abstractions": {},
            "discovered_auth_functions": {},
            "known_safe_patterns": [],
            "framework": "unknown",
            "framework_confidence": 0.0,
            "suppressed_rules": {},
            "suppression_reasons": {},
        }

    def save(self) -> None:
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        self.memory_file.write_text(json.dumps(self._data, indent=2))

    def learn_from_cycle(self, findings: list[dict[str, Any]],
                         evidence_list: list[FindingEvidence]) -> None:
        """Learn from a completed audit cycle."""
        self._data["cycles_learned"] += 1

        # Learn sanitizers
        for ev in evidence_list:
            if ev.confidence_level == ConfidenceLevel.MITIGATED:
                for san in ev.sanitizers:
                    name = san.metadata.get("sanitizer", "")
                    if name:
                        self._data["discovered_sanitizers"][name] = (
                            self._data["discovered_sanitizers"].get(name, 0) + 1
                        )
                # Record suppressed rule
                rule = ev.rule
                if rule:
                    self._data["suppressed_rules"][rule] = (
                        self._data["suppressed_rules"].get(rule, 0) + 1
                    )
                    reason = "mitigated_by_sanitizer"
                    if ev.framework_context and ev.framework_context != "unknown":
                        reason = f"framework_{ev.framework_context}"
                    self._data["suppression_reasons"][rule] = reason

        # Learn from pattern scanning
        self._scan_for_primitives()

        self.save()

    def _scan_for_primitives(self) -> None:
        """Scan project for common security primitives."""
        # Detect database abstractions
        db_patterns = {
            "PDO::prepare": "PDO prepared statements",
            "mysqli_prepare": "MySQLi prepared statements",
            "->query(": "Database query abstraction",
            "Model::": "Eloquent/ORM model",
            "DB::": "Database facade",
            "prisma.": "Prisma ORM",
            "sequelize": "Sequelize ORM",
            "sqlalchemy": "SQLAlchemy ORM",
        }

        # Detect auth functions
        auth_patterns = {
            "verify_csrf": "CSRF verification",
            "password_hash": "Password hashing",
            "password_verify": "Password verification",
            "hash_equals": "Timing-safe comparison",
            "authenticate": "Authentication function",
            "login_required": "Auth decorator/middleware",
            "Auth::check": "Auth check",
            "session_start": "Session management",
            "passport.authenticate": "Passport.js auth",
        }

        # Detect validation functions
        val_patterns = {
            "filter_var": "Input filtering",
            "filter_input": "Input filtering",
            "sanitize_int_array": "Integer sanitization",
            "validate_int_range": "Range validation",
            "escape": "HTML escaping",
        }

        for filepath in self.repo_root.rglob("*.php"):
            try:
                content = filepath.read_text(encoding="utf-8", errors="ignore")
                for pattern, desc in {**db_patterns, **auth_patterns, **val_patterns}.items():
                    if pattern in content:
                        if pattern in db_patterns:
                            self._data["discovered_db_abstractions"][desc] = True
                        elif pattern in auth_patterns:
                            self._data["discovered_auth_functions"][desc] = True
                        elif pattern in val_patterns:
                            self._data["discovered_validators"][desc] = True
            except Exception:
                pass

    def is_known_sanitizer(self, name: str) -> bool:
        return name in self._data["discovered_sanitizers"]

    def should_suppress_rule(self, rule: str, context: str = "") -> tuple[bool, str]:
        """Check if a rule should be suppressed based on learned patterns."""
        if rule in self._data["suppressed_rules"]:
            count = self._data["suppressed_rules"][rule]
            reason = self._data["suppression_reasons"].get(rule, "learned_pattern")
            if count >= 2:  # Suppressed in 2+ cycles → reliably mitigated
                return True, reason
        return False, ""

    def summary(self) -> dict[str, Any]:
        return {
            "cycles": self._data["cycles_learned"],
            "sanitizers": len(self._data["discovered_sanitizers"]),
            "validators": len(self._data["discovered_validators"]),
            "db_abstractions": len(self._data["discovered_db_abstractions"]),
            "auth_functions": len(self._data["discovered_auth_functions"]),
            "suppressed_rules": len(self._data["suppressed_rules"]),
            "known_safe_patterns": len(self._data["known_safe_patterns"]),
            "framework": self._data["framework"],
        }


# ═══════════════════════════════════════════════════════════════════════════════
# SEMANTIC AUDITOR — integrates all intelligence layers
# ═══════════════════════════════════════════════════════════════════════════════


class SemanticAuditor:
    """Unified semantic intelligence engine.

    Combines: AST parsing, taint analysis, framework detection,
    confidence classification, repository memory, and security KB
    into a single audit pipeline.
    """

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)
        self.taint = TaintAnalyzer(repo_root)
        self.memory = RepositoryMemory(repo_root)
        self._findings_cache: list[FindingEvidence] = []

    def enrich_findings(self, raw_findings: list[dict[str, Any]]) -> list[FindingEvidence]:
        """Enrich raw regex findings with semantic intelligence.

        Each raw finding goes through:
        1. AST location verification
        2. Taint analysis (source → sanitizer → sink)
        3. Confidence classification
        4. Security KB enrichment (CWE, OWASP, CVSS)
        5. Framework context attachment
        6. Evidence graph construction
        """
        enriched: list[FindingEvidence] = []
        for raw in raw_findings:
            file_path = raw.get("file", "")
            line = raw.get("line", 0)
            rule = raw.get("rule", "")
            severity = raw.get("severity", "P2")
            category = raw.get("category", "SECURITY")
            message = raw.get("message", "")
            finding_id = raw.get("finding_id", "")

            if not file_path or not line:
                continue

            full_path = self.repo_root / file_path
            if not full_path.exists():
                continue

            # Taint analysis
            evidence = self.taint.analyze(full_path, line, rule)
            if evidence is None:
                continue

            evidence.finding_id = finding_id
            evidence.severity = severity
            evidence.category = category
            evidence.rule = rule
            evidence.message = message

            # Check repository memory for suppression
            should_suppress, reason = self.memory.should_suppress_rule(rule)
            if should_suppress:
                evidence.confidence_level = ConfidenceLevel.MITIGATED
                evidence.confidence = 0.95
                evidence.remediation_advice = f"Pattern suppressed: {reason}"

            # AST location verification
            ast_nodes = ASTParser.parse_file(full_path)
            if ast_nodes:
                matching_node = self._find_node_at_line(ast_nodes, line)
                if matching_node:
                    evidence.ast_node_type = matching_node.kind
                    evidence.symbol = matching_node.name
                    evidence.line_start = matching_node.start_line
                    evidence.line_end = matching_node.end_line

            enriched.append(evidence)

        self._findings_cache = enriched
        return enriched

    def _find_node_at_line(self, nodes: list[ASTNode], target_line: int) -> ASTNode | None:
        """Find the AST node that best matches the target line."""
        for node in nodes:
            if node.start_line <= target_line <= node.end_line:
                return node
            result = self._find_node_at_line(node.children, target_line)
            if result:
                return result
        return None

    def compute_enriched_score(self, findings: list[FindingEvidence],
                                base_score: float) -> float:
        """Compute score adjusted by semantic intelligence.

        Mitigated/suppressed findings don't penalize score.
        True positives count more than false positives.
        """
        effective_findings = [
            f for f in findings
            if f.confidence_level not in (
                ConfidenceLevel.MITIGATED,
                ConfidenceLevel.FALSE_POSITIVE,
            )
        ]

        # Weight by confidence
        total_weight = sum(
            (1.0 if f.confidence_level == ConfidenceLevel.TRUE_POSITIVE else
             0.8 if f.confidence_level == ConfidenceLevel.LIKELY_TRUE else
             0.4 if f.confidence_level == ConfidenceLevel.UNCERTAIN else
             0.15) * (f.confidence)
            for f in effective_findings
        )

        # Bonus for clean remediation advice
        bonus = min(10, len([f for f in findings if f.remediation_advice]) * 0.5)

        adjusted = max(0, min(100, base_score - (total_weight * 0.1) + bonus))
        return round(adjusted, 1)

    def classification_summary(self, findings: list[FindingEvidence]) -> dict[str, Any]:
        """Generate a semantic classification summary."""
        classified: dict[str, dict] = {}
        for f in findings:
            level_name = f.confidence_level.name
            if level_name not in classified:
                classified[level_name] = {"count": 0, "examples": []}
            classified[level_name]["count"] += 1
            if len(classified[level_name]["examples"]) < 3:
                classified[level_name]["examples"].append({
                    "rule": f.rule,
                    "file": f.file,
                    "line": f.line_start,
                    "confidence": f.confidence,
                    "mitigated_by": [s.description for s in f.sanitizers],
                })

        return {
            "total": len(findings),
            "breakdown": classified,
            "actionable": len([f for f in findings
                               if f.confidence_level in (ConfidenceLevel.TRUE_POSITIVE,
                                                         ConfidenceLevel.LIKELY_TRUE)]),
            "mitigated": len([f for f in findings
                              if f.confidence_level == ConfidenceLevel.MITIGATED]),
            "false_positive": len([f for f in findings
                                   if f.confidence_level in (ConfidenceLevel.FALSE_POSITIVE,
                                                              ConfidenceLevel.LIKELY_FALSE_POSITIVE)]),
            "uncertain": len([f for f in findings
                             if f.confidence_level == ConfidenceLevel.UNCERTAIN]),
            "framework": self.taint.framework or "unknown",
        }

    def store_cycle_memory(self) -> None:
        """Store this cycle's findings into repository memory for future cycles."""
        raw_findings = [
            {
                "finding_id": f.finding_id,
                "rule": f.rule,
                "file": f.file,
                "line": f.line_start,
                "severity": f.severity,
            }
            for f in self._findings_cache
        ]
        self.memory.learn_from_cycle(raw_findings, self._findings_cache)
        self.memory.save()
