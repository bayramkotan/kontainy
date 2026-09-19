"""kontainy — teşhis motoru (VenvStudio'daki Conflict Manager'ın karşılığı)."""

from .engine import (                                        # noqa: F401
    ERROR, WARN, INFO, SEVERITY_TITLES, SEVERITY_ICONS,
    Environment, Rule, Finding, collect, run_rules,
)
from .catalog import RULES, rule_by_id, rule_stats           # noqa: F401


def diagnose(probe: bool = True) -> tuple:
    """Ortamı toplar, tüm kuralları çalıştırır, (env, findings) döndürür."""
    env = collect(probe=probe)
    return env, run_rules(env, RULES)
