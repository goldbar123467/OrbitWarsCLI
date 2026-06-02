from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class PublicIdea:
    title: str
    evidence: str
    suggestion: str


KEYWORDS: list[tuple[str, str, str]] = [
    (
        "Moving-planet prediction seems important.",
        "orbit|moving|angular|velocity|prediction|eta",
        "physics.moving_planet_prediction = true",
    ),
    (
        "Sun collision losses are worth guarding against.",
        "sun|collision|center|destroy|lost",
        "physics.sun_avoidance = true",
    ),
    (
        "Early neutral expansion is a strong default hypothesis.",
        "neutral|expand|expansion|early|production",
        "preset = fast_expansion or target_scoring.neutral_bonus += 4",
    ),
    (
        "Over-sending and duplicate attacks need budget checks.",
        "over.?send|duplicate|already|fleet|target",
        "attacks.avoid_oversending = true",
    ),
    (
        "Defense needs incoming fleet awareness.",
        "defend|reinforce|incoming|threat|under attack",
        "defense.detect_incoming_fleets = true",
    ),
    (
        "Comets are an optional specialized module.",
        "comet|comets",
        "strategy.comet_usage = opportunistic",
    ),
]


def extract_ideas(paths: list[Path]) -> list[PublicIdea]:
    import re

    combined = "\n".join(path.read_text(errors="ignore") for path in paths if path.exists())
    lowered = combined.lower()
    ideas: list[PublicIdea] = []
    for title, pattern, suggestion in KEYWORDS:
        matches = re.findall(pattern, lowered)
        if matches:
            ideas.append(
                PublicIdea(
                    title=title,
                    evidence=f"Found {len(matches)} keyword hits across {len(paths)} cached public mining file(s).",
                    suggestion=suggestion,
                )
            )
    if not ideas:
        ideas.append(
            PublicIdea(
                title="No strong public pattern detected yet.",
                evidence="Cached mining files did not contain the tracked strategy keywords.",
                suggestion="Run `kab mine discussions --sort recent` and `kab mine leaderboard` first.",
            )
        )
    return ideas


def render_idea_board(ideas: list[PublicIdea]) -> str:
    lines = ["# Public Ideas Found", ""]
    for idx, idea in enumerate(ideas, start=1):
        lines.append(f"{idx}. {idea.title}")
        lines.append(f"   Evidence: {idea.evidence}")
        lines.append(f"   Suggested buffet toggle: `{idea.suggestion}`")
        lines.append("")
    return "\n".join(lines)
