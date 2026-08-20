"""
Software Bill of Materials generation.
Produces CycloneDX or SPDX format SBOM for dependency transparency.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple
from pathlib import Path
import json
import uuid
from datetime import datetime, timezone
import subprocess
import shutil
import re


@dataclass
class SBOMComponent:
    name: str
    version: str
    type: str = "library"
    scope: str = "required"
    purl: str = ""
    licenses: List[str] = field(default_factory=list)
    checksums: Dict[str, str] = field(default_factory=dict)


class SBOMGenerator:
    def __init__(self, project_path: str):
        self.project_path = Path(project_path).resolve()
        self._syft_available = shutil.which("syft") is not None

    def generate_cyclonedx(self, output_path: str = None) -> Dict:
        if self._syft_available:
            return self._generate_with_syft("cyclonedx-json", output_path)
        return self._generate_cyclonedx_manual(output_path)

    def generate_spdx(self, output_path: str = None) -> Dict:
        if self._syft_available:
            return self._generate_with_syft("spdx-json", output_path)
        return self._generate_spdx_manual(output_path)

    def _generate_with_syft(self, fmt: str, output_path: str = None) -> Dict:
        try:
            result = subprocess.run(
                ["syft", str(self.project_path), "-o", f"{fmt}",
                 "--file", output_path or "/dev/null"],
                capture_output=True, text=True, timeout=300,
            )
            if output_path and Path(output_path).exists():
                return json.loads(Path(output_path).read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[SBOM] syft error: {e}")

        return self._generate_cyclonedx_manual(output_path)

    def _generate_cyclonedx_manual(self, output_path: str = None) -> Dict:
        components = self._collect_components()

        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.5",
            "serialNumber": f"urn:uuid:{uuid.uuid4()}",
            "version": 1,
            "metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "component": {
                    "type": "application",
                    "name": self.project_path.name,
                },
                "tools": [{
                    "name": "aura-sbom-generator",
                    "vendor": "AURA Audit Engine",
                }],
            },
            "components": [
                {
                    "type": c.type,
                    "name": c.name,
                    "version": c.version,
                    "scope": c.scope,
                    "purl": c.purl,
                }
                for c in components
            ],
        }

        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_text(
                json.dumps(sbom, indent=2), encoding="utf-8"
            )

        return sbom

    def _generate_spdx_manual(self, output_path: str = None) -> Dict:
        components = self._collect_components()

        sbom = {
            "spdxVersion": "SPDX-2.3",
            "dataLicense": "CC0-1.0",
            "SPDXID": "SPDXRef-DOCUMENT",
            "documentNamespace": (
                f"https://aura.audit/sbom/{self.project_path.name}-"
                f"{uuid.uuid4()}"
            ),
            "name": self.project_path.name,
            "creationInfo": {
                "created": datetime.now(timezone.utc).isoformat(),
                "creators": ["Tool: AURA Audit Engine"],
            },
            "packages": [
                {
                    "SPDXID": f"SPDXRef-{i}",
                    "name": c.name,
                    "versionInfo": c.version,
                    "downloadLocation": "NOASSERTION",
                    "packageSupplier": "NOASSERTION",
                    "externalRefs": [
                        {
                            "referenceCategory": "PACKAGE-MANAGER",
                            "referenceLocator": c.purl,
                            "referenceType": "purl",
                        }
                    ] if c.purl else [],
                }
                for i, c in enumerate(components)
            ],
        }

        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_text(
                json.dumps(sbom, indent=2), encoding="utf-8"
            )

        return sbom

    def _collect_components(self) -> List[SBOMComponent]:
        components: List[SBOMComponent] = []
        manifests = {
            "npm": self.project_path / "package.json",
            "composer": self.project_path / "composer.json",
            "python-req": self.project_path / "requirements.txt",
            "python-poetry": self.project_path / "pyproject.toml",
            "python-pipfile": self.project_path / "Pipfile",
            "rust": self.project_path / "Cargo.toml",
            "go": self.project_path / "go.mod",
            "ruby": self.project_path / "Gemfile",
            "java-maven": self.project_path / "pom.xml",
            "java-gradle": self.project_path / "build.gradle",
        }

        for eco, manifest_path in manifests.items():
            if not manifest_path.exists():
                continue

            if eco == "npm":
                try:
                    pkg = json.loads(manifest_path.read_text(encoding="utf-8"))
                    for name, version in (pkg.get("dependencies") or {}).items():
                        components.append(SBOMComponent(
                            name=name, version=version,
                            purl=f"pkg:npm/{name}@{version}",
                        ))
                    for name, version in (pkg.get("devDependencies") or {}).items():
                        components.append(SBOMComponent(
                            name=name, version=version,
                            purl=f"pkg:npm/{name}@{version}",
                            scope="development",
                        ))
                except (json.JSONDecodeError, KeyError):
                    pass

            elif eco == "composer":
                try:
                    comp = json.loads(manifest_path.read_text(encoding="utf-8"))
                    for name, version in (comp.get("require") or {}).items():
                        components.append(SBOMComponent(
                            name=name, version=version,
                            purl=f"pkg:composer/{name}@{version}",
                        ))
                    for name, version in (comp.get("require-dev") or {}).items():
                        components.append(SBOMComponent(
                            name=name, version=version,
                            purl=f"pkg:composer/{name}@{version}",
                            scope="development",
                        ))
                except (json.JSONDecodeError, KeyError):
                    pass

            elif eco == "python-req":
                for line in manifest_path.read_text(encoding="utf-8").splitlines():
                    m = re.match(
                        r'^([a-zA-Z0-9_\-\.]+)([><=!~]+[\d\.\*,\s]+.*)?$',
                        line.strip(),
                    )
                    if m and not line.strip().startswith("#"):
                        name = m.group(1)
                        version = m.group(2).strip() if m.group(2) else "*"
                        components.append(SBOMComponent(
                            name=name, version=version,
                            purl=f"pkg:pypi/{name}@{version}",
                        ))

            elif eco == "go":
                in_require = False
                for line in manifest_path.read_text(encoding="utf-8").splitlines():
                    if line.strip() == "require (":
                        in_require = True
                        continue
                    if in_require and line.strip() == ")":
                        in_require = False
                        continue
                    if in_require:
                        m = re.match(r'^\s*([^\s]+)\s+(v[\d\.]+[^\s]*)', line)
                        if m:
                            name, version = m.group(1), m.group(2)
                            components.append(SBOMComponent(
                                name=name, version=version,
                                purl=f"pkg:golang/{name}@{version}",
                            ))

        return components

    def list_dependencies(self) -> Dict[str, List[str]]:
        components = self._collect_components()
        by_ecosystem: Dict[str, List[str]] = {}

        for c in components:
            eco = "unknown"
            if c.purl:
                match = re.match(r'^pkg:([^/]+)/', c.purl)
                if match:
                    eco = match.group(1)

            if eco not in by_ecosystem:
                by_ecosystem[eco] = []

            by_ecosystem[eco].append(f"{c.name}@{c.version}")

        return by_ecosystem

    def find_vulnerable_deps(self) -> List[Dict]:
        components = self._collect_components()
        vulnerable: List[Dict] = []

        npm_packages = [
            c for c in components
            if c.purl and c.purl.startswith("pkg:npm/")
        ]
        if npm_packages:
            try:
                result = subprocess.run(
                    ["npm", "audit", "--json"],
                    cwd=str(self.project_path),
                    capture_output=True, text=True, timeout=120,
                )
                if result.stdout.strip():
                    data = json.loads(result.stdout)
                    vulns = data.get("vulnerabilities", {})
                    for key, vuln in vulns.items():
                        if vuln:
                            vulnerable.append({
                                "ecosystem": "npm",
                                "package": vuln.get("name", key),
                                "severity": (vuln.get("severity") or "low").upper(),
                                "description": (
                                    vuln.get("via", [{}])[0].get("title", "")
                                    if isinstance(vuln.get("via", [{}])[0], dict)
                                    else ""
                                ),
                            })
            except Exception:
                pass

        return vulnerable

    def get_license_compliance(self) -> Dict:
        components = self._collect_components()
        npm_licenses: Dict[str, str] = {}
        pkg_json = self.project_path / "package.json"
        if pkg_json.exists():
            try:
                pkg = json.loads(pkg_json.read_text(encoding="utf-8"))

                node_modules = self.project_path / "node_modules"
                for name in (pkg.get("dependencies") or {}).keys():
                    dep_pkg = node_modules / name / "package.json"
                    if dep_pkg.exists():
                        try:
                            dep = json.loads(dep_pkg.read_text(encoding="utf-8"))
                            npm_licenses[name] = dep.get("license", "UNKNOWN")
                        except (json.JSONDecodeError, KeyError):
                            npm_licenses[name] = "UNKNOWN"
            except (json.JSONDecodeError, KeyError):
                pass

        return {
            "total_dependencies": len(components),
            "by_ecosystem": self.list_dependencies(),
            "npm_licenses": npm_licenses,
            "unknown_license_count": sum(
                1 for v in npm_licenses.values() if v == "UNKNOWN"
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }