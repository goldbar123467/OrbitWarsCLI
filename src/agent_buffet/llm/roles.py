from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentRole:
    name: str
    job: str
    auto_allowed: tuple[str, ...]
    requires_confirmation: tuple[str, ...] = ()


ROLES = [
    AgentRole(
        name="Miner",
        job="Read public discussions, leaderboards, episodes, and logs.",
        auto_allowed=("read public material", "write mining notes"),
    ),
    AgentRole(
        name="Strategist",
        job="Convert evidence into strategy hypotheses.",
        auto_allowed=("update local configs", "write reports"),
    ),
    AgentRole(
        name="Builder",
        job="Compile selected modules into self-contained agent files.",
        auto_allowed=("write generated agents", "run validation"),
    ),
    AgentRole(
        name="Critic",
        job="Check invalid actions, timeout risk, and failure modes.",
        auto_allowed=("run local tests", "compare metrics"),
    ),
    AgentRole(
        name="Teacher",
        job="Explain changes in plain English.",
        auto_allowed=("write reports", "summarize risks"),
    ),
    AgentRole(
        name="Submitter",
        job="Package and submit only after explicit confirmation.",
        auto_allowed=("package local files",),
        requires_confirmation=("submit to Kaggle", "overwrite champion", "delete experiments"),
    ),
]


def render_roles() -> str:
    lines = ["# Internal Agent Roles", ""]
    for role in ROLES:
        lines.append(f"## {role.name}")
        lines.append(role.job)
        lines.append("")
        lines.append("Allowed automatically: " + ", ".join(role.auto_allowed))
        if role.requires_confirmation:
            lines.append("Requires confirmation: " + ", ".join(role.requires_confirmation))
        lines.append("")
    return "\n".join(lines)
