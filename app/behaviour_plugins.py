"""Behavior plugins for SET-transition-driven runtime actions.

Plugins can inspect a SET transition context and emit trap directives.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


type VarBindValue = str | int


@dataclass(frozen=True)
class TrapDirective:
    """A trap emission request returned by behavior plugins."""

    trap_oid: str
    var_binds: list[tuple[str, VarBindValue]]


@dataclass(frozen=True)
class SetTransition:
    """SET transition context passed to behavior plugins."""

    oid: str
    mib_name: str | None
    symbol_name: str | None
    old_value: str | None
    new_value: str


type SetTransitionPlugin = Callable[[SetTransition], list[TrapDirective] | None]


class SetTransitionPluginRegistry:
    """Registry for runtime SET-transition behavior plugins."""

    def __init__(self) -> None:
        """Initialize an empty plugin registry."""
        self._plugins: list[SetTransitionPlugin] = []
        self._plugin_names: dict[str, SetTransitionPlugin] = {}

    def register(self, name: str, plugin: SetTransitionPlugin) -> None:
        """Register a transition plugin under a stable name."""
        if name in self._plugin_names:
            old_plugin = self._plugin_names[name]
            if old_plugin != plugin and old_plugin in self._plugins:
                self._plugins.remove(old_plugin)
            logger.warning("Behavior plugin '%s' already registered, replacing", name)

        self._plugin_names[name] = plugin
        if plugin not in self._plugins:
            self._plugins.append(plugin)

    def get_trap_directives(self, transition: SetTransition) -> list[TrapDirective]:
        """Aggregate trap directives from all registered plugins."""
        directives: list[TrapDirective] = []
        for plugin in self._plugins:
            try:
                plugin_result = plugin(transition)
            except (AttributeError, LookupError, OSError, TypeError, ValueError):
                logger.exception("Behavior plugin %s failed", plugin.__name__)
                continue
            if plugin_result:
                directives.extend(plugin_result)
        return directives


_registry = SetTransitionPluginRegistry()


def register_set_transition_plugin(
    name: str,
) -> Callable[[SetTransitionPlugin], SetTransitionPlugin]:
    """Register a runtime SET-transition behavior plugin via decorator."""

    def decorator(func: SetTransitionPlugin) -> SetTransitionPlugin:
        _registry.register(name, func)
        return func

    return decorator


def get_set_transition_trap_directives(transition: SetTransition) -> list[TrapDirective]:
    """Return trap directives for one SET transition context."""
    return _registry.get_trap_directives(transition)
