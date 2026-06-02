from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

from agent_buffet.paths import display_path


MIN_OFFICIAL_VERSION = (1, 28, 0)


@dataclass
class OfficialEnvStatus:
    available: bool
    python_version: str
    package_version: str | None
    message: str


def _version_tuple(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in value.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        if digits == "":
            break
        parts.append(int(digits))
    return tuple(parts)


def official_env_status() -> OfficialEnvStatus:
    python_version = ".".join(str(part) for part in sys.version_info[:3])
    if sys.version_info < (3, 11):
        return OfficialEnvStatus(
            available=False,
            python_version=python_version,
            package_version=None,
            message="Official Orbit Wars requires Python 3.11+ with kaggle-environments>=1.28.0.",
        )
    try:
        package_version = metadata.version("kaggle-environments")
    except metadata.PackageNotFoundError:
        return OfficialEnvStatus(
            available=False,
            python_version=python_version,
            package_version=None,
            message='Install with: python -m pip install "kaggle-environments>=1.28.0"',
        )
    if _version_tuple(package_version) < MIN_OFFICIAL_VERSION:
        return OfficialEnvStatus(
            available=False,
            python_version=python_version,
            package_version=package_version,
            message='Upgrade with: python -m pip install -U "kaggle-environments>=1.28.0"',
        )
    return OfficialEnvStatus(
        available=True,
        python_version=python_version,
        package_version=package_version,
        message="Official Orbit Wars environment is ready.",
    )


def list_local_agents(root: Path) -> list[dict[str, str]]:
    agents_dir = root / "agents"
    result: list[dict[str, str]] = []
    if not agents_dir.exists():
        return result
    for main_path in sorted(agents_dir.glob("*/main.py")):
        result.append({"name": main_path.parent.name, "path": display_path(main_path, root)})
    return result


def resolve_agent_spec(root: Path, spec: str) -> str:
    spec = spec.strip()
    if spec in {"random", "reaction", "do_nothing"}:
        return spec
    candidate = Path(spec)
    if candidate.exists():
        return str(candidate.resolve())
    agent_main = root / "agents" / spec / "main.py"
    if agent_main.exists():
        return str(agent_main.resolve())
    if spec == "current":
        current = root / "agents" / "current" / "main.py"
        if current.exists():
            return str(current.resolve())
    return spec


def run_official_games(
    root: Path,
    agent: str,
    opponent: str,
    *,
    games: int,
    seed: int,
    debug: bool = True,
    save_dir: Path | None = None,
) -> dict[str, Any]:
    status = official_env_status()
    if not status.available:
        raise RuntimeError(status.message)

    from kaggle_environments import make  # type: ignore[import]

    agent_spec = resolve_agent_spec(root, agent)
    opponent_spec = resolve_agent_spec(root, opponent)
    results: list[dict[str, Any]] = []
    for offset in range(games):
        game_seed = seed + offset
        env = make("orbit_wars", configuration={"seed": game_seed}, debug=debug)
        env.run([agent_spec, opponent_spec])
        final = env.steps[-1]
        player_rows = []
        for index, state in enumerate(final):
            player_rows.append(
                {
                    "player": index,
                    "reward": getattr(state, "reward", None),
                    "status": getattr(state, "status", None),
                }
            )
        reward0 = player_rows[0]["reward"]
        reward1 = player_rows[1]["reward"] if len(player_rows) > 1 else None
        win = reward1 is None or (reward0 is not None and reward1 is not None and reward0 > reward1)
        row = {"seed": game_seed, "players": player_rows, "win": bool(win)}
        results.append(row)
        if save_dir:
            save_dir.mkdir(parents=True, exist_ok=True)
            replay_path = save_dir / f"official_{game_seed}.json"
            try:
                replay_data = env.toJSON()
            except Exception:
                replay_data = {"steps": str(env.steps)}
            replay_path.write_text(json.dumps(replay_data, indent=2, default=str), encoding="utf-8")
            row["replay"] = str(replay_path)

    return {
        "agent": agent,
        "opponent": opponent,
        "games": games,
        "wins": sum(1 for row in results if row["win"]),
        "win_rate": round(sum(1 for row in results if row["win"]) / max(1, games), 3),
        "results": results,
        "package_version": status.package_version,
    }
