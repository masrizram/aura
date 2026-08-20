"""
Community plugin registry client.
Discovers and installs community-contributed plugins from GitHub.
"""

import json
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

COMMUNITY_REGISTRY_URL = (
    "https://raw.githubusercontent.com/aura-audit/plugins/main/registry.json"
)


class CommunityRegistry:
    def __init__(self, cache_dir: Optional[str] = None):
        if cache_dir is None:
            cache_dir = ".aura/plugins/cache"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._registry: Dict = {}
        self._registry_path = self.cache_dir / "registry.json"
        self.registry: Dict = self._load_cached_registry()

    def _load_cached_registry(self) -> Dict:
        if self._registry_path.exists():
            try:
                with open(self._registry_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_cached_registry(self) -> None:
        try:
            with open(self._registry_path, "w", encoding="utf-8") as f:
                json.dump(self._registry, f, indent=2)
        except OSError:
            pass

    def refresh(self) -> Dict:
        try:
            import requests
            resp = requests.get(COMMUNITY_REGISTRY_URL, timeout=30)
            resp.raise_for_status()
            self._registry = resp.json()
            self._save_cached_registry()
            return self._registry
        except Exception as e:
            if not self._registry:
                return {"error": str(e), "source": "cache", "plugins": []}
            return self._registry

    def search(self, query: str) -> List[Dict]:
        if not self._registry:
            self.refresh()
        q = query.lower()
        plugins = self._registry.get("plugins", [])
        results: List[Dict] = []
        for plugin in plugins:
            name = plugin.get("name", "").lower()
            desc = plugin.get("description", "").lower()
            ptype = plugin.get("plugin_type", "").lower()
            if q in name or q in desc or q in ptype:
                results.append(plugin)
        return results

    def install(self, plugin_name: str, version: str = "latest") -> bool:
        if not self._registry:
            self.refresh()

        plugins = self._registry.get("plugins", [])
        target_plugin: Optional[Dict] = None
        for plugin in plugins:
            if plugin.get("name") == plugin_name:
                target_plugin = plugin
                break

        if target_plugin is None:
            return False

        download_url = target_plugin.get("download_url", "")
        if not download_url:
            if version == "latest":
                versions = target_plugin.get("versions", [])
                if versions:
                    latest = versions[0]
                    download_url = latest.get("url", "")
                    if not download_url:
                        repo = target_plugin.get("repo", "")
                        tag = latest.get("tag", "")
                        if repo and tag:
                            download_url = (
                                f"https://github.com/{repo}/archive/refs/tags/"
                                f"{tag}.zip"
                            )

        if not download_url:
            return False

        try:
            import requests
            import zipfile
            import io

            resp = requests.get(download_url, timeout=120)
            resp.raise_for_status()

            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                members = zf.namelist()
                yaml_members = [
                    m for m in members
                    if (m.endswith(".yml") or m.endswith(".yaml"))
                    and "plugin" in m.lower()
                ]
                if not yaml_members:
                    return False

                install_dir = self.cache_dir / plugin_name
                if install_dir.exists():
                    shutil.rmtree(install_dir)
                install_dir.mkdir(parents=True, exist_ok=True)

                for member in yaml_members:
                    zf.extract(member, install_dir)
            return True
        except Exception:
            return False

    def list_installed(self) -> List[Dict]:
        results: List[Dict] = []
        if not self.cache_dir.exists():
            return results
        for item in sorted(self.cache_dir.iterdir()):
            if item.is_dir() and item.name != "registry.json":
                plugin_files = list(item.glob("**/*.yml")) + list(
                    item.glob("**/*.yaml")
                )
                for pf in plugin_files:
                    try:
                        import yaml
                        with open(pf, "r", encoding="utf-8") as f:
                            config = yaml.safe_load(f)
                        if isinstance(config, dict) and "name" in config:
                            config["path"] = str(pf.parent)
                            results.append(config)
                            break
                    except Exception:
                        pass
        return results

    def uninstall(self, plugin_name: str) -> bool:
        installed = self.list_installed()
        for entry in installed:
            if entry.get("name") == plugin_name:
                p = Path(entry.get("path", ""))
                if p.exists():
                    try:
                        shutil.rmtree(p)
                        return True
                    except OSError:
                        return False
        return False