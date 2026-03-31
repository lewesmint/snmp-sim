"""SET-transition behavior plugin for TEST-ENUM-MIB trap semantics."""

from __future__ import annotations

from app.behaviour_plugins import (
    SetTransition,
    TrapDirective,
    register_set_transition_plugin,
)

_COMPLETION_TRAP_OID = "1.3.6.1.4.1.99998.0.2"
_EVENT_TRAP_OID = "1.3.6.1.4.1.99998.0.3"
_ALARM_KEYWORDS = ("alarm", "fault", "critical", "major", "minor")


def _is_alarm_like(value: str | None) -> bool:
    if value is None:
        return False
    lowered = value.lower()
    if any(keyword in lowered for keyword in _ALARM_KEYWORDS):
        return True
    return lowered in {"1", "2", "3", "4", "5"}


def _is_alarm_transition(old_value: str | None, new_value: str) -> bool:
    return _is_alarm_like(new_value) and not _is_alarm_like(old_value)


def _infer_event_severity(value: str) -> int:
    lowered = value.lower()
    if "critical" in lowered:
        return 5
    if "major" in lowered:
        return 4
    if "minor" in lowered:
        return 3
    if "alarm" in lowered or "fault" in lowered:
        return 2
    if lowered.isdigit():
        return max(1, min(5, int(lowered)))
    return 2


@register_set_transition_plugin("test_enum_mib_trap_behaviour")
def emit_enum_mib_traps(transition: SetTransition) -> list[TrapDirective] | None:
    """Emit completion/event trap directives for TEST-ENUM-MIB transitions."""
    if transition.mib_name != "TEST-ENUM-MIB":
        return None

    directives = [
        TrapDirective(
            trap_oid=_COMPLETION_TRAP_OID,
            var_binds=[
                ("1.3.6.1.4.1.99998.1.1.3", f"SET {transition.oid}"),
                ("1.3.6.1.4.1.99998.1.1.4", 0),
            ],
        )
    ]

    if _is_alarm_transition(transition.old_value, transition.new_value):
        directives.append(
            TrapDirective(
                trap_oid=_EVENT_TRAP_OID,
                var_binds=[
                    (
                        "1.3.6.1.4.1.99998.1.1.5",
                        _infer_event_severity(transition.new_value),
                    ),
                    (
                        "1.3.6.1.4.1.99998.1.1.6",
                        f"Alarm state entered on {transition.oid}: {transition.new_value}",
                    ),
                ],
            )
        )

    return directives
