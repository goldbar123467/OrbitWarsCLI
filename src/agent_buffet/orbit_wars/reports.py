from __future__ import annotations

from pathlib import Path
from typing import Any


def render_run_report(metrics: dict[str, Any], *, agent_path: Path, opponents: list[str]) -> str:
    strengths = []
    risks = []
    if metrics.get("win_rate", 0) >= 0.55:
        strengths.append("Wins more than half of local synthetic games.")
    if metrics.get("avg_neutral_captures_by_50", 0) >= 1:
        strengths.append("Captures neutral planets consistently.")
    if metrics.get("avg_fleets_lost_to_sun", 0) == 0:
        strengths.append("Avoids simulated sun losses.")
    if metrics.get("avg_reinforcements_sent", 0) > 0:
        strengths.append("Uses reinforcements instead of only attacking.")
    if not strengths:
        strengths.append("Produces valid actions and completes local games.")

    if metrics.get("avg_invalid_moves", 0) > 0:
        risks.append("Some turns generate invalid moves.")
    if metrics.get("avg_fleets_lost_to_sun", 0) > 0:
        risks.append("Some fleets are lost to the simulated sun.")
    if metrics.get("avg_attacks_arrived_underpowered", 0) > 2:
        risks.append("Several attacks arrive underpowered.")
    if metrics.get("win_rate", 0) < 0.5:
        risks.append("Local win rate is below the promote threshold.")
    if not risks:
        risks.append("Main risk is that local simulation is approximate, not the official Orbit Wars engine.")

    recommendation = (
        "yes"
        if metrics.get("win_rate", 0) >= 0.6
        and metrics.get("avg_invalid_moves", 0) == 0
        and metrics.get("avg_fleets_lost_to_sun", 0) == 0
        else "no"
    )

    lines = [
        "# Agent Buffet Run Report",
        "",
        f"Agent: `{agent_path}`",
        f"Opponents: {', '.join(opponents)}",
        "",
        "## Result Metrics",
        "",
        f"- Games: {metrics.get('games', 0)}",
        f"- Win rate: {metrics.get('win_rate', 0):.1%}",
        f"- Average final ship score: {metrics.get('avg_final_ship_score', 0)}",
        f"- Average final ship diff: {metrics.get('avg_final_ship_diff', 0)}",
        f"- Average planet count: {metrics.get('avg_planet_count', 0)}",
        f"- Average production controlled: {metrics.get('avg_production_controlled', 0)}",
        "",
        "## Failure Metrics",
        "",
        f"- Invalid moves per game: {metrics.get('avg_invalid_moves', 0)}",
        f"- Timeout turns per game: {metrics.get('avg_timeout_turns', 0)}",
        f"- Fleets lost to sun per game: {metrics.get('avg_fleets_lost_to_sun', 0)}",
        f"- Underpowered attacks per game: {metrics.get('avg_attacks_arrived_underpowered', 0)}",
        "",
        "## Strengths",
        "",
        *[f"- {item}" for item in strengths[:5]],
        "",
        "## Failure Modes",
        "",
        *[f"- {item}" for item in risks[:5]],
        "",
        f"Submit recommendation: **{recommendation}**",
        "",
    ]
    return "\n".join(lines)
