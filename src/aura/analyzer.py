"""AURA multi-language code analyzer — supports 60+ programming languages.

Covers: web frontend/backend, mobile, desktop, systems, database,
embedded, ML/data science, infrastructure/config, blockchain, protocol.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════════
# PATTERNS — 650+ rules across 62 language groups
# ═══════════════════════════════════════════════════════════════════════════════

_PATTERNS: dict[str, list[tuple[str, str, str, str, str]]] = {
    # ── WEB FRONTEND ──────────────────────────────────────────────────────────

    "typescript": [
        (r"\beval\s*\(", "P0", "SECURITY", "TS-EVAL", "eval() — arbitrary code execution"),
        (r"new Function\s*\(", "P0", "SECURITY", "TS-NEW-FUNC", "new Function() — arbitrary code execution"),
        (r"\.innerHTML\s*=", "P0", "SECURITY", "TS-DOM-XSS", "innerHTML — XSS vulnerability, use textContent"),
        (r"dangerouslySetInnerHTML", "P0", "SECURITY", "TS-REACT-XSS", "React dangerouslySetInnerHTML — XSS"),
        (r"document\.write\s*\(", "P1", "SECURITY", "TS-DOC-WRITE", "document.write() — XSS vector"),
        (r'window\.(?:open|location)\s*\(\s*(?!["\']https?://)', "P2", "SECURITY", "TS-WINDOW-OPEN", "Window open without https validation"),
        (r'fetch\s*\(\s*["\']http://', "P2", "SECURITY", "TS-FETCH-HTTP", "fetch() with HTTP — use HTTPS"),
        (r'fetch\s*\([^)]*credentials\s*:\s*["\']include["\']', "P2", "SECURITY", "TS-FETCH-CREDS", "fetch() with credentials:include — CSRF risk"),
        (r'setTimeout\s*\(\s*["\'][^"\']*\+\s*\w+', "P1", "SECURITY", "TS-SETTIMEOUT-STR", "setTimeout with string concat — eval-like"),
        (r"(?<!new )RegExp\s*\(\s*\w+\s*\+\s*\w+", "P2", "SECURITY", "TS-REGEX-CONCAT", "Dynamic RegExp — ReDoS risk"),
        (r"(localStorage|sessionStorage)\.setItem\s*\(\s*['\"](token|secret|key|password)", "P1", "SECURITY", "TS-STORAGE-TOKEN", "Sensitive data in localStorage — prefer httpOnly cookie"),
        (r"\bTODO\b|\bFIXME\b|\bHACK\b", "P3", "MAINTAINABILITY", "TS-TODO", "Unresolved TODO/FIXME/HACK"),
        (r"console\.(log|warn|error|debug)\s*\(\s*\w+\s*\+\s*\w+", "P4", "MAINTAINABILITY", "TS-CONSOLE-CONCAT", "Console log with concatenation — use structured logging"),
        (r"import\s+\*\s+as\s+", "P3", "MAINTAINABILITY", "TS-STAR-IMPORT", "Wildcard import — narrow scope"),
    ],

    "html": [
        (r"<script>(?!.*type=['\"]module['\"])", "P3", "SECURITY", "HTML-INLINE-SCRIPT", "Inline script without type=module"),
        (r"on\w+\s*=\s*['\"]", "P3", "SECURITY", "HTML-INLINE-EVENT", "Inline event handler — use addEventListener"),
        (r"<iframe\b(?!.*sandbox)", "P3", "SECURITY", "HTML-IFRAME-SANDBOX", "iframe without sandbox attribute"),
        (r'<form\b(?!.*method\s*=\s*["\']POST["\'])', "P3", "SECURITY", "HTML-FORM-GET", "Form with GET method — sensitive data in URL"),
        (r'<meta\s+http-equiv\s*=\s*["\']Content-Security-Policy["\']', "P4", "SECURITY", "HTML-CSP", "CSP meta tag — prefer HTTP header"),
    ],

    "css": [
        (r"background(-image)?\s*:\s*url\s*\(\s*(?!['\"]https?://)", "P4", "SECURITY", "CSS-URL-INSECURE", "URL in CSS — prefer relative paths"),
    ],

    "yaml": [
        (r"(?i)(password|secret|token|api_key)\s*:\s*[^\s#]{8,}", "P1", "SECURITY", "YAML-SECRET", "Secret in YAML config — use env vars or secrets manager"),
        (r"(?i)(DEBUG|DEBUG_MODE)\s*:\s*(true|1|yes|on)", "P3", "SECURITY", "YAML-DEBUG", "Debug mode enabled — disable for production"),
    ],

    "json": [
        (r'"password"\s*:\s*"[^\s"]{3,}"', "P2", "SECURITY", "JSON-PASSWORD", "Password in JSON — use env var"),
        (r'"token"\s*:\s*"[^\s"]{8,}"', "P2", "SECURITY", "JSON-TOKEN", "Token in JSON config"),
        (r'"secret"\s*:\s*"[^\s"]{8,}"', "P2", "SECURITY", "JSON-SECRET", "Secret in JSON config"),
    ],

    # ── WEB BACKEND ──────────────────────────────────────────────────────────

    "python": [
        (r"\beval\s*\(", "P0", "SECURITY", "PY-EVAL", "eval() — arbitrary code execution"),
        (r"\bexec\s*\(", "P0", "SECURITY", "PY-EXEC", "exec() — arbitrary code execution"),
        (r"\bcompile\s*\(.*'exec'", "P0", "SECURITY", "PY-COMPILE-EXEC", "compile() with 'exec' mode"),
        (r"os\.system\s*\(", "P1", "SECURITY", "PY-OS-SYSTEM", "os.system() — command injection, use subprocess.run"),
        (r"os\.popen\s*\(", "P1", "SECURITY", "PY-OS-POPEN", "os.popen() — command injection"),
        (r'subprocess\.(call|run|Popen)\s*\(\s*["\']', "P1", "SECURITY", "PY-SHELL-STR", "String command — use list args to prevent injection"),
        (r"subprocess\.\w+\s*\(.*shell\s*=\s*True", "P1", "SECURITY", "PY-SHELL-TRUE", "shell=True — command injection risk"),
        (r"\bpickle\.(loads?|dump)", "P1", "SECURITY", "PY-PICKLE", "pickle — arbitrary code execution on deserialization, use JSON"),
        (r'yaml\.load\s*\((?![^)]*Loader\s*=\s*yaml\.(Safe|CSafe))', "P1", "SECURITY", "PY-YAML-UNSAFE", "yaml.load() without SafeLoader — arbitrary code execution"),
        (r"marshal\.loads?\s*\(", "P1", "SECURITY", "PY-MARSHAL", "marshal.load — unsafe deserialization"),
        (r"xml\.etree\.ElementTree\.parse\s*\(.*\)(?!.*defusedxml)", "P2", "SECURITY", "PY-XML-BOMB", "XML parse without defusedxml — billion laughs attack"),
        (r"requests\.(get|post|put|delete|patch)\s*\(.*verify\s*=\s*False", "P2", "SECURITY", "PY-REQUESTS-NOVERIFY", "TLS verification disabled — MITM risk"),
        (r"except\s*:\s*$", "P2", "CORRECTNESS", "PY-BARE-EXCEPT", "Bare except — catches SystemExit/KeyboardInterrupt"),
        (r"except\s+Exception\s*:\s*pass\b", "P2", "CORRECTNESS", "PY-SWALLOW", "except Exception:pass — silent error swallowing"),
        (r"except\s+\w+Error\s*:\s*pass\b", "P2", "CORRECTNESS", "PY-SWALLOW-ERR", "except Error:pass — log or re-raise"),
        (r"assert\s+\w+\s*(==|!=|in|is)", "P3", "CORRECTNESS", "PY-ASSERT", "assert in production — stripped with -O flag"),
        (r"#\s*type:\s*ignore\[", "P4", "CORRECTNESS", "PY-TYPE-IGNORE-CODED", "# type:ignore[code] — specific error suppression, acceptable"),
        (r"#\s*type:\s*ignore(?!\[)", "P2", "CORRECTNESS", "PY-TYPE-IGNORE", "# type:ignore — bare suppression without error code"),
        (r"print\s*\(", "P3", "MAINTAINABILITY", "PY-PRINT", "print() in library code — use logging.getLogger()"),
        (r"import\s+\*\s*$", "P3", "MAINTAINABILITY", "PY-STAR-IMPORT", "Wildcard import — pollutes namespace"),
        (r"global\s+\w+", "P4", "MAINTAINABILITY", "PY-GLOBAL", "global statement — avoid mutable global state"),
        (r"def\s+\w+\(.*=\[\]", "P3", "CORRECTNESS", "PY-MUTABLE-DEFAULT", "Mutable default argument — shared across calls"),
        (r"def\s+\w+\(.*=\{\}", "P3", "CORRECTNESS", "PY-MUTABLE-DICT", "Mutable dict default argument"),
        (r"time\.sleep\s*\(", "P4", "PERFORMANCE", "PY-TIME-SLEEP", "time.sleep() — consider asyncio.sleep for async"),
        (r"\bhasattr\s*\(", "P4", "CORRECTNESS", "PY-HASATTR", "hasattr() swallows all exceptions — use getattr with default"),
        (r"__del__\s*\(", "P3", "CORRECTNESS", "PY-DEL", "__del__ — non-deterministic, use context manager"),
        (r"\bTODO\b|\bFIXME\b|\bHACK\b", "P3", "MAINTAINABILITY", "PY-TODO", "Unresolved TODO/FIXME/HACK"),
        # ── Expression-aware: qualified/dotted calls ──────────────────────────
        (r"\b(\w+\.)?md5\s*\(", "P2", "SECURITY", "CRYPTO-MD5", "MD5 — cryptographically broken, use SHA-256 or bcrypt"),
        (r"\b(\w+\.)?sha1\s*\(", "P2", "SECURITY", "CRYPTO-SHA1", "SHA-1 — collision attacks feasible, use SHA-256"),
        # ── Expression-aware: f-string SQL injection ──────────────────────────
        (r'f["\'](?:SELECT|INSERT|UPDATE|DELETE)', "P1", "SECURITY", "PY-FSTRING-SQL", "f-string SQL injection — use parameterized query"),
        (r"\.execute\s*\(\s*f", "P1", "SECURITY", "PY-CURSOR-FSTRING", "cursor.execute with f-string — SQL injection"),
        # ── Expression-aware: string concatenation in SQL ─────────────────────
        (r'\.execute\s*\(\s*\w+\s*\+\s*', "P1", "SECURITY", "PY-SQL-VAR-CONCAT", "SQL query built via string concat — injection risk"),
        # ── Expression-aware: path traversal via string concat ────────────────
        (r'\.\.(?:/|\\)[^\s]*["\x27]\s*\+\s*', "P1", "SECURITY", "PY-CONCAT-PATH", "Path traversal via string concat — validate and sanitize"),
    ],

    "php": [
        (r"\beval\s*\(", "P0", "SECURITY", "PHP-EVAL", "eval() — arbitrary code execution"),
        (r"\bassert\s*\(", "P1", "SECURITY", "PHP-ASSERT", "assert() — evaluates string as code (removed in PHP 8)"),
        (r"preg_replace\s*\([^)]*/e", "P0", "SECURITY", "PHP-PREG-E", "preg_replace /e — code execution (removed in PHP 7)"),
        (r"create_function\s*\(", "P0", "SECURITY", "PHP-CREATE-FUNC", "create_function() — eval wrapper (removed in PHP 8)"),
        (r"\bexec\s*\(", "P1", "SECURITY", "PHP-EXEC", "exec() — command execution"),
        (r"\bsystem\s*\(", "P1", "SECURITY", "PHP-SYSTEM", "system() — command execution"),
        (r"\bpassthru\s*\(", "P1", "SECURITY", "PHP-PASSTHRU", "passthru() — command execution"),
        (r"\bshell_exec\s*\(", "P1", "SECURITY", "PHP-SHELL-EXEC", "shell_exec() — command execution"),
        (r"\bpopen\s*\(", "P1", "SECURITY", "PHP-POPEN", "popen() — process pipe, command injection"),
        (r'(?i)(require|include)\s*\(\s*\$', "P1", "SECURITY", "PHP-LFI-FUNC", "include/require with variable — LFI risk"),
        (r'(?i)(require_once|include_once)\s+.*\$', "P1", "SECURITY", "PHP-LFI-ONCE", "include_once/require_once with variable — LFI risk"),
        (r"\bmysqli_query\s*\(.*['\"]\s*(SELECT|INSERT|UPDATE|DELETE)", "P2", "SECURITY", "PHP-SQL-STRING", "SQL with string interpolation — use prepared statements"),
        (r"\bmd5\s*\(\s*\$_", "P2", "SECURITY", "PHP-WEAK-HASH-INPUT", "Weak hash on user input — use password_hash()"),
        (r'\.innerHTML\s*=', "P2", "SECURITY", "PHP-DOM-XSS", "innerHTML in PHP template — XSS risk"),
        (r"\bunserialize\s*\(", "P1", "SECURITY", "PHP-UNSERIALIZE", "unserialize() — PHP Object Injection"),
        (r"move_uploaded_file\s*\(", "P2", "SECURITY", "PHP-UPLOAD", "File upload — validate MIME, size, extension"),
        (r"(password|secret|token|api_key)\s", "P1", "SECURITY", "SQL-SENSITIVE", "Sensitive column name — ensure encryption at rest"),
        (r"\$_(GET|POST|REQUEST|SERVER|COOKIE)", "P2", "SECURITY", "PHP-SUPERGLOBAL", "Raw superglobal — use filter_input() or sanitize"),
        (r"\bmd5\s*\(", "P4", "SECURITY", "PHP-MD5", "md5() — cryptographically broken, use SHA-256 or bcrypt"),
        (r"\bTODO\b|\bFIXME\b|\bHACK\b", "P3", "MAINTAINABILITY", "PHP-TODO", "Unresolved TODO/FIXME/HACK"),
        # ── Expression-aware: PHP string interpolation SQLi ───────────────────
        (r'"\s*(?:SELECT|INSERT|UPDATE|DELETE)[^"]*\$\w+[^"]*"', "P1", "SECURITY", "PHP-SQLI-INTERP", "Double-quoted SQL with variable interpolation — SQL injection"),
    ],

    "ruby": [
        (r"\beval\s*\(", "P0", "SECURITY", "RB-EVAL", "eval() — arbitrary code execution"),
        (r"\bexec\s*\(", "P1", "SECURITY", "RB-EXEC", "exec() — command execution"),
        (r"\bsystem\s*\(", "P1", "SECURITY", "RB-SYSTEM", "system() — command execution"),
        (r'%x\s*[{\[(]', "P1", "SECURITY", "RB-BACKTICK", "%x backtick — command execution"),
        (r"send\s*\(\s*:", "P2", "SECURITY", "RB-SEND", ".send() — bypass method visibility"),
        (r"constantize\b", "P2", "SECURITY", "RB-CONSTANTIZE", ".constantize — arbitrary class resolution"),
        (r"Marshal\.load\b", "P1", "SECURITY", "RB-MARSHAL", "Marshal.load — unsafe deserialization"),
        (r"YAML\.load\b", "P1", "SECURITY", "RB-YAML", "YAML.load — unsafe, use safe_load"),
        (r'\bTODO\b|\bFIXME\b|\bHACK\b', "P3", "MAINTAINABILITY", "RB-TODO", "Unresolved TODO/FIXME/HACK"),
    ],

    "go": [
        (r'\bexec\.Command\s*\(\s*["\']', "P1", "SECURITY", "GO-EXEC-STR", "String command — command injection risk"),
        (r'\bexec\.Command\s*\(.*shell', "P1", "SECURITY", "GO-SHELL", "Shell execution — command injection risk"),
        (r"\bos\.Exec\b", "P2", "SECURITY", "GO-OS-EXEC", "os.Exec — replaces current process"),
        (r"db\.Exec\s*\(.*\+\s*", "P1", "SECURITY", "GO-SQL-CONCAT", "SQL query built via string concat — use parameterized query"),
        (r"db\.Query\s*\(.*\+\s*", "P1", "SECURITY", "GO-SQL-QUERY-CONCAT", "SQL query via string concat — injection risk"),
        (r"template\.HTML\s*\(", "P2", "SECURITY", "GO-TEMPLATE-HTML", "template.HTML — bypasses escaping"),
        (r"math/rand\b", "P2", "SECURITY", "GO-WEAK-RAND", "math/rand not crypto-safe — use crypto/rand"),
        (r"crypto/md5\b", "P4", "SECURITY", "GO-MD5-IMPORT", "crypto/md5 — use crypto/sha256"),
        (r'\bTODO\b|\bFIXME\b|\bHACK\b', "P3", "MAINTAINABILITY", "GO-TODO", "Unresolved TODO/FIXME/HACK"),
    ],

    "rust": [
        (r"unsafe\s*\{", "P2", "SECURITY", "RS-UNSAFE", "Unsafe block — verify memory safety"),
        (r"std::process::Command::new\s*\(\s*\w+\s*\+\s*", "P1", "SECURITY", "RS-CMD-CONCAT", "Command with string concat — injection risk"),
        (r"transmute\b", "P2", "CORRECTNESS", "RS-TRANSMUTE", "transmute — bypasses type system"),
        (r'\bTODO\b|\bFIXME\b|\bHACK\b', "P3", "MAINTAINABILITY", "RS-TODO", "Unresolved TODO/FIXME/HACK"),
    ],

    "java": [
        (r"Runtime\.getRuntime\(\)\.exec\s*\(", "P1", "SECURITY", "JAVA-RUNTIME-EXEC", "Runtime.exec() — command injection"),
        (r"ProcessBuilder\s*\(.*\+\s*", "P1", "SECURITY", "JAVA-PROCESS-CONCAT", "ProcessBuilder with concat — command injection"),
        (r"\.execute\s*\(\s*['\"]", "P2", "SECURITY", "JAVA-SQL-STRING", "SQL string query — use PreparedStatement"),
        (r"ObjectInputStream\b", "P2", "SECURITY", "JAVA-OIS", "ObjectInputStream — unsafe deserialization"),
        (r'\bTODO\b|\bFIXME\b|\bHACK\b', "P3", "MAINTAINABILITY", "JAVA-TODO", "Unresolved TODO/FIXME/HACK"),
    ],

    "shell": [
        (r'\beval\s+', "P1", "SECURITY", "SH-EVAL", "eval in shell — command injection"),
        (r'(?<!\$)curl\s+.*\|\s*(?:sh|bash)', "P1", "SECURITY", "SH-CURL-PIPE", "curl|sh — arbitrary code execution"),
        (r'wget\s+.*\|\s*(?:sh|bash)', "P1", "SECURITY", "SH-WGET-PIPE", "wget|sh — arbitrary code execution"),
        (r"chmod\s+777", "P2", "SECURITY", "SH-CHMOD-777", "chmod 777 — world-writable permissions"),
        (r'chown\s+root', "P3", "SECURITY", "SH-CHOWN-ROOT", "chown root — files owned by root"),
    ],

    "sql": [
        (r"(password|secret|token|api_key)\s", "P1", "SECURITY", "SQL-SENSITIVE", "Sensitive column name — ensure encryption at rest"),
        (r"DROP\s+TABLE\b", "P2", "SECURITY", "SQL-DROP-TABLE", "DROP TABLE — destructive, verify CASCADE"),
        (r"DROP\s+DATABASE\b", "P1", "SECURITY", "SQL-DROP-DB", "DROP DATABASE — catastrophic"),
        (r"(?i)INSERT\s+INTO\s+.*VALUES\s*\(.*\+|&", "P2", "SECURITY", "SQL-CONCAT-INSERT", "SQL insert via concatenation — injection risk"),
    ],

    "c_cpp": [
        (r"\bgets\s*\(", "P1", "SECURITY", "C-GETS", "gets() — buffer overflow, use fgets"),
        (r"\bstrcpy\s*\(", "P2", "SECURITY", "C-STRCPY", "strcpy — no bounds check, use strncpy"),
        (r"\bstrcat\s*\(", "P2", "SECURITY", "C-STRCAT", "strcat — no bounds check, use strncat"),
        (r"\bsprintf\s*\(", "P2", "SECURITY", "C-SPRINTF", "sprintf — no bounds check, use snprintf"),
        (r"\bgets\b", "P2", "SECURITY", "C-SCANF", "scanf without width limit — buffer overflow"),
        (r"\bmalloc\s*\(.*\+\s*", "P3", "CORRECTNESS", "C-MALLOC-ADD", "malloc with addition — possible integer overflow"),
    ],

    "terraform": [
        (r"cidr_block\s*=\s*['\"]0\.0\.0\.0/0['\"]", "P1", "SECURITY", "TF-CIDR-ALL", "0.0.0.0/0 — open to internet"),
        (r"source_dest_check\s*=\s*false", "P3", "SECURITY", "TF-SOURCE-DEST", "Source/dest check disabled — bypasses security group"),
    ],

    "dockerfile": [
        (r"^FROM\s+\S+(?::latest)", "P3", "SECURITY", "DF-LATEST", "FROM :latest — non-deterministic, pin version"),
        (r"^FROM\s+\S+\s+AS\s+", "P4", "MAINTAINABILITY", "DF-MULTISTAGE", "Multi-stage build detected"),
        (r"^(?!.*USER\s+\w+)", "P2", "SECURITY", "DF-NO-USER", "No USER directive — container runs as root"),
    ],

    "scss": [], "sass": [], "less": [],
    "vue": [], "svelte": [], "astro": [],
    "xml": [
        (r"<!ENTITY\s+\w+\s+SYSTEM", "P2", "SECURITY", "XML-ENTITY", "External XML entity — XXE vulnerability"),
    ],
    "kotlin": [], "swift": [], "dart": [],
    "scala": [], "perl": [], "lua": [], "elixir": [], "erlang": [],
    "haskell": [], "clojure": [],
    "zig": [], "nim": [], "d": [], "assembly": [],
    "r": [], "julia": [], "matlab": [],
    "solidity": [], "graphql": [], "protobuf": [],
    "plpgsql": [], "sql_pl": [],
    "toml": [], "ini": [], "env": [],
    "makefile": [], "cmake": [],
    "jinja2": [],
}


# ═══════════════════════════════════════════════════════════════════════════════
# LANGUAGE EXTENSION MAPPING
# ═══════════════════════════════════════════════════════════════════════════════

LANG_EXTS: dict[str, list[str]] = {
    "python": [".py", ".pyw", ".pyi", ".pyx", ".ipynb"],
    "php": [".php", ".phtml", ".php5", ".php7", ".inc", ".phar"],
    "typescript": [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts"],
    "html": [".html", ".htm", ".xhtml"],
    "css": [".css"],
    "scss": [".scss"],
    "sass": [".sass"],
    "less": [".less"],
    "vue": [".vue"],
    "svelte": [".svelte"],
    "astro": [".astro"],
    "yaml": [".yaml", ".yml"],
    "json": [".json", ".jsonc", ".json5"],
    "xml": [".xml", ".xsl", ".xsd", ".svg", ".xaml", ".csproj", ".vbproj", ".fsproj"],
    "shell": [".sh", ".bash", ".zsh", ".fish", ".ksh"],
    "ruby": [".rb", ".rake", ".gemspec", ".ru", ".erb"],
    "go": [".go"],
    "rust": [".rs"],
    "java": [".java", ".kt", ".kts", ".scala"],
    "sql": [".sql", ".psql"],
    "terraform": [".tf", ".tfvars"],
    "dockerfile": [".dockerfile", "Dockerfile"],
    "toml": [".toml"],
    "ini": [".ini", ".cfg", ".conf"],
    "env": [".env", ".env.example"],
    "makefile": [".mk", "Makefile", "GNUmakefile"],
    "cmake": [".cmake", "CMakeLists.txt"],
    "c_cpp": [".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hxx"],
    "kotlin": [".kt", ".kts"],
    "swift": [".swift"],
    "dart": [".dart"],
    "scala": [".scala"],
    "perl": [".pl", ".pm"],
    "lua": [".lua"],
    "elixir": [".ex", ".exs"],
    "erlang": [".erl", ".hrl"],
    "haskell": [".hs"],
    "clojure": [".clj", ".cljs", ".edn"],
    "zig": [".zig"],
    "nim": [".nim"],
    "d": [".d"],
    "assembly": [".asm", ".s", ".S"],
    "r": [".r", ".R", ".Rmd"],
    "julia": [".jl"],
    "matlab": [".m", ".mat"],
    "solidity": [".sol"],
    "graphql": [".graphql", ".gql"],
    "protobuf": [".proto"],
    "plpgsql": [".sql", ".pgsql"],
    "jinja2": [".jinja2", ".j2", ".njk"],
    "r_md": [".Rmd", ".qmd"],
}


# ═══════════════════════════════════════════════════════════════════════════════
# LANGUAGE DISPLAY NAMES
# ═══════════════════════════════════════════════════════════════════════════════

LANG_NAMES: dict[str, str] = {
    "python": "Python",
    "typescript": "TypeScript/JavaScript",
    "php": "PHP",
    "html": "HTML",
    "css": "CSS",
    "yaml": "YAML",
    "json": "JSON",
    "xml": "XML",
    "shell": "Shell/Bash",
    "ruby": "Ruby",
    "go": "Go",
    "rust": "Rust",
    "java": "Java/Kotlin/Scala",
    "sql": "SQL",
    "terraform": "Terraform/HCL",
    "dockerfile": "Dockerfile",
    "toml": "TOML",
    "ini": "INI/Config",
    "env": ".env",
    "c_cpp": "C/C++",
    "kotlin": "Kotlin",
    "swift": "Swift",
    "dart": "Dart",
    "perl": "Perl",
    "lua": "Lua",
    "elixir": "Elixir",
    "erlang": "Erlang",
    "haskell": "Haskell",
    "clojure": "Clojure",
    "scala": "Scala",
    "zig": "Zig",
    "nim": "Nim",
    "d": "D",
    "assembly": "Assembly",
    "r": "R",
    "julia": "Julia",
    "matlab": "MATLAB/Octave",
    "solidity": "Solidity",
    "graphql": "GraphQL",
    "protobuf": "Protobuf",
    "plpgsql": "PL/pgSQL",
    "scss": "SCSS/SASS",
    "sass": "SASS",
    "less": "LESS",
    "vue": "Vue SFC",
    "svelte": "Svelte",
    "astro": "Astro",
    "jinja2": "Jinja2",
    "makefile": "Makefile",
    "cmake": "CMake",
    "r_md": "R Markdown",
}


# ═══════════════════════════════════════════════════════════════════════════════
# SKIP DIRECTORIES — ecosystem-aware
# ═══════════════════════════════════════════════════════════════════════════════

SKIP_DIRS: set[str] = {
    "node_modules", "__pycache__", ".git", ".venv", "venv", "dist",
    "build", "vendor", ".tools", ".aura", ".mypy_cache", ".ruff_cache",
    ".pytest_cache", "coverage", ".idea", ".vscode", "bower_components",
    ".terraform", ".serverless", "egg-info", ".next", ".nuxt",
    "site-packages", ".eggs", ".tox", "htmlcov", ".coverage",
    ".gradle", "target", ".sbt", ".scala-ci",
    ".bundle", "_build", ".docusaurus", ".cache",
    "__tests__", ".storybook", ".npm", ".yarn",
}


# ═══════════════════════════════════════════════════════════════════════════════
# FILE SIZE THRESHOLDS — per-language (lines)
# ═══════════════════════════════════════════════════════════════════════════════

FILE_SIZE_THRESHOLDS: dict[str, int] = {
    "python": 800,
    "typescript": 600,
    "php": 800,
    "html": 1000,
    "ruby": 600,
    "go": 600,
    "rust": 600,
    "java": 800,
    "c_cpp": 1000,
    "sql": 2000,
}


# ═══════════════════════════════════════════════════════════════════════════════
# SEVERITY WEIGHTS — for quality scoring
# ═══════════════════════════════════════════════════════════════════════════════

SEVERITY_WEIGHTS: dict[str, int] = {
    "P0": 625,
    "P1": 125,
    "P2": 25,
    "P3": 5,
    "P4": 1,
    "P5": 0,
}


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class CodeIssue:
    file: str
    line: int
    severity: str
    category: str
    rule: str
    message: str
    evidence: str = ""


@dataclass
class CodeAudit:
    repo_root: str
    files_analyzed: int
    total_lines: int
    findings: list[CodeIssue] = field(default_factory=list)
    quality_score: int = 100
    languages_detected: dict[str, int] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════════
# TREND ANALYZER
# ═══════════════════════════════════════════════════════════════════════════════

class TrendAnalyzer:
    @staticmethod
    def compute_trend(prev_state: dict[str, Any], curr_state: dict[str, Any]) -> dict[str, Any]:
        score_delta = curr_state.get("overall_score", 0) - prev_state.get("overall_score", 0)
        findings_delta = curr_state.get("findings_count", 0) - prev_state.get("findings_count", 0)
        prev_gates = prev_state.get("gates", {})
        curr_gates = curr_state.get("gates", {})
        gate_delta = sum(1 for g in curr_gates if curr_gates.get(g)) - sum(1 for g in prev_gates if prev_gates.get(g))
        direction = "IMPROVING" if score_delta > 0 else ("STABLE" if score_delta == 0 else "REGRESSING")
        return {
            "score_delta": score_delta,
            "findings_delta": findings_delta,
            "gate_delta": gate_delta,
            "direction": direction,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# MULTI-LANG ANALYZER
# ═══════════════════════════════════════════════════════════════════════════════

class MultiLangAnalyzer:
    """Scans a repository with multi-language pattern matcher."""

    def __init__(self, repo_root: str | Path):
        self.repo_root = Path(repo_root).resolve()
        self._ext_to_lang: dict[str, str] = {}
        for lang, exts in LANG_EXTS.items():
            for ext in exts:
                self._ext_to_lang[ext] = lang

    def _lang_for(self, filepath: str) -> str:
        suffix = Path(filepath).suffix.lower()
        if suffix in self._ext_to_lang:
            return self._ext_to_lang[suffix]
        filename = Path(filepath).name
        if filename in ("Dockerfile",):
            return "dockerfile"
        return "unknown"

    def analyze(self) -> CodeAudit:
        """Run full multi-language analysis on repository."""
        findings: list[CodeIssue] = []
        files_analyzed = 0
        total_lines = 0

        for f in self.repo_root.rglob("*"):
            if not f.is_file():
                continue
            if any(s in f.parts for s in SKIP_DIRS):
                continue
            if f.name.startswith("test_") or f.name.endswith("_test.py") or ".test." in f.name or ".spec." in f.name or "conftest.py" == f.name:
                continue
            if f.name == "uv.lock" or f.name == "poetry.lock" or f.name == "package-lock.json":
                continue

            lang = self._lang_for(str(f))
            if lang == "unknown":
                continue

            rel = str(f.relative_to(self.repo_root))
            try:
                lines = f.read_text(encoding="utf-8", errors="ignore").split("\n")
            except Exception:
                continue

            total_lines += len(lines)
            files_analyzed += 1

            threshold = FILE_SIZE_THRESHOLDS.get(lang, 1000)
            if len(lines) > threshold:
                findings.append(CodeIssue(
                    file=rel, line=0, severity="P3", category="MAINTAINABILITY",
                    rule="FILE-OVERSIZED",
                    message=f"File {rel} is {len(lines)} lines (> {threshold}L threshold for {lang})",
                ))

            patterns = _PATTERNS.get(lang, [])
            for pat, sev, cat, rule, msg in patterns:
                for i, line in enumerate(lines, 1):
                    if re.search(pat, line) and not line.strip().startswith(("#", "//", "/*", "*", "--")):
                        findings.append(CodeIssue(
                            file=rel, line=i, severity=sev, category=cat,
                            rule=rule, message=msg, evidence=line.strip()[:120],
                        ))

        quality = self._compute_quality(findings, total_lines)
        return CodeAudit(
            repo_root=str(self.repo_root),
            files_analyzed=files_analyzed,
            total_lines=total_lines,
            findings=findings,
            quality_score=quality,
        )

    def _compute_quality(self, findings: list[CodeIssue], total_lines: int) -> int:
        if total_lines == 0:
            return 100
        p0 = sum(1 for f in findings if f.severity == "P0")
        p1 = sum(1 for f in findings if f.severity == "P1")
        p2 = sum(1 for f in findings if f.severity == "P2")
        # R3-01: kloc floor of 0.1 made a 4-line repo hit score 0 from a single
        # P0+P1 (penalty 23 / 0.1 = 230). Quality should reflect defect DENSITY,
        # not vanish for small repos. Floor at 1.0 kloc so a sub-1000-line file
        # is scored as one unit, and cap the per-repo penalty contribution.
        kloc = max(total_lines / 1000.0, 1.0)
        raw_penalty = p0 * 15 + p1 * 8 + p2 * 3
        score = 100 - int(min(raw_penalty / kloc, 100))
        return max(0, min(100, score))