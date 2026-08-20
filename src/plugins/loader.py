"""
Plugin loader: discovers and loads plugins from multiple sources:
- Python packages (aura_plugins.*)
- YAML/JSON config files (.aura/plugins/*.yml)
- Community registry (GitHub releases)
"""

from pathlib import Path
from typing import List, Dict, Optional
import json
import logging

logger = logging.getLogger(__name__)

from .registry import PluginRegistry, PluginLifecycle
from .community_registry import CommunityRegistry


class PluginLoader:
    def __init__(self, registry: PluginRegistry):
        self.registry = registry

    def load_from_directory(self, directory: str) -> int:
        return self.registry.discover_plugins([directory])

    def load_from_package(self, package_name: str) -> int:
        return self.registry.load_from_package(package_name)

    def load_from_registry(
        self, plugin_name: str, version: str = "latest"
    ) -> bool:
        community = CommunityRegistry()
        installed = community.list_installed()
        for entry in installed:
            if entry.get("name") == plugin_name:
                if version == "latest" or entry.get("version") == version:
                    return self.load_from_directory(entry.get("path", "")) > 0
        return community.install(plugin_name, version)

    def install_community_plugin(self, plugin_name: str) -> bool:
        community = CommunityRegistry()
        return community.install(plugin_name)

    def init_plugins(self, engine_config: Dict) -> int:
        count = 0
        for plugin in list(self.registry._plugins.values()):
            try:
                plugin.on_init(engine_config)
                count += 1
            except Exception as e:
                logger.error("Plugin %s failed init: %s", type(plugin).__name__, e)
        return count

    def run_cycle_start(self, cycle: int) -> None:
        for plugin in self.registry._plugins.values():
            if plugin.get_metadata().lifecycle == PluginLifecycle.PER_CYCLE:
                try:
                    plugin.on_cycle_start(cycle)
                except Exception as e:
                    logger.error("Plugin %s failed on_cycle_start: %s", type(plugin).__name__, e)

    def run_cycle_end(self, cycle: int) -> None:
        for plugin in self.registry._plugins.values():
            if plugin.get_metadata().lifecycle == PluginLifecycle.PER_CYCLE:
                try:
                    plugin.on_cycle_end(cycle)
                except Exception as e:
                    logger.error("Plugin %s failed on_cycle_end: %s", type(plugin).__name__, e)