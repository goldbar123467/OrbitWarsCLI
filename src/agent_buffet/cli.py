from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import questionary
import typer
from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from agent_buffet.config import AgentConfig, SourceNote, load_config, preset_config, preset_names, save_config
from agent_buffet.kaggle_api import CommandResult, KaggleGateway
from agent_buffet.llm.roles import render_roles
from agent_buffet.mining.idea_extractor import extract_ideas, render_idea_board
from agent_buffet.orbit_wars.adapter import OrbitWarsAdapter, save_metrics
from agent_buffet.orbit_wars.official import list_local_agents, official_env_status, run_official_games
from agent_buffet.orbit_wars.reports import render_run_report
from agent_buffet.paths import MARKER_DIR, display_path, project_root, require_project_root
from agent_buffet.storage import db


console = Console()
app = typer.Typer(no_args_is_help=True, help="No-code/low-code agent factory CLI.")
kaggle_app = typer.Typer(no_args_is_help=True, help="Kaggle auth and competition commands.")
mine_app = typer.Typer(no_args_is_help=True, help="Mine public Kaggle surfaces into idea notes.")
app.add_typer(kaggle_app, name="kaggle")
app.add_typer(mine_app, name="mine")


BANNER = r"""
    ___                    __     ____        ________     __
   /   | ____ ____  ____  / /_   / __ )__  __/ __/ __/__  / /_
  / /| |/ __ `/ _ \/ __ \/ __/  / __  / / / / /_/ /_/ _ \/ __/
 / ___ / /_/ /  __/ / / / /_   / /_/ / /_/ / __/ __/  __/ /_
/_/  |_\__, /\___/_/ /_/\__/  /_____/\__,_/_/ /_/  \___/\__/
      /____/
"""


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _adapter(competition: str = "orbit-wars") -> OrbitWarsAdapter:
    if competition != "orbit-wars":
        raise typer.BadParameter("Only orbit-wars is implemented in this build.")
    return OrbitWarsAdapter()


def _write_project_file(root: Path, competition: str) -> None:
    marker = root / MARKER_DIR
    marker.mkdir(parents=True, exist_ok=True)
    project_file = marker / "project.yaml"
    if not project_file.exists():
        project_file.write_text(f"competition: {competition}\ncreated_at: {_utc_stamp()}\n", encoding="utf-8")


def _default_config_path(root: Path) -> Path:
    return root / "agents" / "current" / "agent.yaml"


def _default_agent_path(root: Path) -> Path:
    return root / "agents" / "current" / "main.py"


def _ensure_dirs(root: Path) -> None:
    for name in ["agents/current", "runs", "cache/mining", "reports"]:
        (root / name).mkdir(parents=True, exist_ok=True)


def _print_result(result: CommandResult, *, save_to: Optional[Path] = None) -> None:
    if result.stdout.strip():
        console.print(result.stdout.rstrip())
    if result.stderr.strip():
        console.print(result.stderr.rstrip(), style="yellow")
    if save_to:
        save_to.parent.mkdir(parents=True, exist_ok=True)
        save_to.write_text(
            "\n".join(
                [
                    "$ " + " ".join(result.args),
                    "",
                    "## stdout",
                    result.stdout,
                    "",
                    "## stderr",
                    result.stderr,
                    "",
                    f"returncode: {result.returncode}",
                ]
            ),
            encoding="utf-8",
        )
        console.print(f"Saved: {display_path(save_to)}")
    if not result.ok:
        raise typer.Exit(result.returncode if result.returncode else 1)


def _gateway(prompt_token: bool = False) -> KaggleGateway:
    return KaggleGateway.from_env_or_prompt(prompt=prompt_token)


def _bootstrap_project(root: Path, competition: str, preset: str) -> Path:
    if competition != "orbit-wars":
        raise typer.BadParameter("Only orbit-wars is implemented in this build.")
    root = root.resolve()
    _write_project_file(root, competition)
    _ensure_dirs(root)
    db.init_db(root)
    config_path = _default_config_path(root)
    if not config_path.exists():
        config = preset_config(preset)
        config.name = "current"
        config.sources.append(SourceNote(kind="generated", detail="kab start"))
        save_config(config, config_path)
        db.record_agent(root, "current", config_path)
    return config_path


def _find_or_create_root() -> Path:
    try:
        return require_project_root()
    except RuntimeError:
        return Path.cwd().resolve()


def _build_current(root: Path) -> dict[str, Path]:
    config_path = _default_config_path(root)
    built = _adapter().render_agent(config_path, config_path.parent)
    config = load_config(config_path)
    db.record_agent(root, config.name, config_path, built["main"])
    return built


def _validate_current(root: Path) -> tuple[bool, list[str], dict[str, object]]:
    return _adapter().validate_agent(_default_agent_path(root))


def _status_word(value: bool) -> str:
    return "[green]ready[/green]" if value else "[yellow]needs setup[/yellow]"


def _clip_ascii(value: object, limit: int = 42) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def _latest_run(root: Path) -> dict[str, object] | None:
    try:
        return db.latest_run(root)
    except Exception:
        return None


def _dashboard(root: Path) -> None:
    config_path = _default_config_path(root)
    agent_path = _default_agent_path(root)
    config = load_config(config_path) if config_path.exists() else None
    latest = _latest_run(root)
    gateway = KaggleGateway.from_env_or_prompt(prompt=False)

    console.print(Panel(BANNER, subtitle="No-code Orbit Wars agent factory", box=box.ASCII))

    status = Table(title="Cockpit", box=box.ASCII)
    status.add_column("System")
    status.add_column("State")
    status.add_column("Detail")
    status.add_row("Project", "[green]ready[/green]", display_path(root, root))
    status.add_row("Config", _status_word(config_path.exists()), display_path(config_path, root))
    status.add_row("Agent", _status_word(agent_path.exists()), display_path(agent_path, root))
    status.add_row("Kaggle token", "[green]env present[/green]" if os.getenv("KAGGLE_API_TOKEN") else "[yellow]not linked[/yellow]", "use `kab kaggle auth-check --prompt-token`")
    status.add_row("Kaggle CLI", "[green]installed[/green]" if gateway.cli_available() else "[yellow]missing[/yellow]", gateway.cli_version() or "not found")
    official = official_env_status()
    status.add_row("Official env", "[green]ready[/green]" if official.available else "[yellow]needs setup[/yellow]", _clip_ascii(official.message, 58))
    console.print(status)

    if config:
        strategy = Table(title="Current Strategy", box=box.ASCII)
        strategy.add_column("Module")
        strategy.add_column("Choice")
        strategy.add_row("Template", config.base_template)
        strategy.add_row("Expansion", config.strategy.expansion)
        strategy.add_row("Aggression", config.strategy.aggression)
        strategy.add_row("Defense", config.strategy.defense)
        strategy.add_row("Sun avoidance", str(config.physics.sun_avoidance))
        strategy.add_row("Moving planets", str(config.physics.moving_planet_prediction))
        strategy.add_row("Comets", config.strategy.comet_usage)
        console.print(strategy)

    run_table = Table(title="Last Run", box=box.ASCII)
    run_table.add_column("Metric")
    run_table.add_column("Value")
    if latest:
        metrics = latest["metrics"]
        win_rate = metrics.get("win_rate", 0)
        if isinstance(win_rate, float):
            win_rate = f"{win_rate:.1%}"
        run_table.add_row("Run id", str(latest["id"]))
        run_table.add_row("Games", str(metrics.get("games", 0)))
        run_table.add_row("Win rate", str(win_rate))
        run_table.add_row("Invalid moves/game", str(metrics.get("avg_invalid_moves", "n/a")))
        run_table.add_row("Sun losses/game", str(metrics.get("avg_fleets_lost_to_sun", "n/a")))
    else:
        run_table.add_row("Status", "No local run yet")
        run_table.add_row("Next", "kab test --games 50")
    console.print(run_table)

    commands = Table(title="Next Moves", box=box.ASCII)
    commands.add_column("Goal")
    commands.add_column("Command")
    commands.add_row("Pick a bot style", "kab buffet")
    commands.add_row("Build and validate", "kab start --no-view")
    commands.add_row("Run local games", "kab test --games 100")
    commands.add_row("Run official game", "kab official-test --games 1 --opponents random")
    commands.add_row("Train preset sweep", "kab train --games 20")
    commands.add_row("List saved agents", "kab agents")
    commands.add_row("Link Kaggle safely", "kab kaggle auth-check --prompt-token")
    commands.add_row("Submit, gated", "kab submit --confirm")
    console.print(commands)


def _interactive_view(root: Path) -> None:
    choice = questionary.select(
        "What do you want to do?",
        choices=[
            "Build current bot",
            "Validate current bot",
            "Run 25 local games",
            "Run official Kaggle env game",
            "Train preset sweep",
            "Show last report",
            "Check/link Kaggle",
            "Exit",
        ],
    ).ask()
    if choice == "Build current bot":
        build(None, None)
    elif choice == "Validate current bot":
        validate_cmd(None)
    elif choice == "Run 25 local games":
        test_cmd(agent_path=None, games=25, opponents="random,starter_sniper,safe_sniper", turns=220)
    elif choice == "Run official Kaggle env game":
        official_test(agent="current", opponents="random", games=1, seed=42, save_replays=True)
    elif choice == "Train preset sweep":
        train(games=12, presets="balanced_ladder,fast_expansion,safe_sniper,enemy_raider", opponents="random,starter_sniper,safe_sniper")
    elif choice == "Show last report":
        report("last-run")
    elif choice == "Check/link Kaggle":
        kaggle_auth_check(prompt_token=True)


@app.command("init")
def init_project(
    competition: str = typer.Argument("orbit-wars", help="Competition adapter to initialize."),
    root: Path = typer.Option(Path("."), "--root", help="Project root."),
    preset: str = typer.Option("balanced_ladder", "--preset", help="Initial Orbit Wars preset."),
) -> None:
    """Initialize an Agent Buffet workspace."""

    root = root.resolve()
    if competition != "orbit-wars":
        raise typer.BadParameter("Only orbit-wars is implemented in this build.")
    config_path = _bootstrap_project(root, competition, preset)
    console.print(Panel.fit(f"Initialized Agent Buffet at {root}\nDefault config: {display_path(config_path, root)}"))


@app.command()
def start(
    preset: str = typer.Option("balanced_ladder", "--preset", help="Preset used when no project exists yet."),
    games: int = typer.Option(0, "--games", min=0, help="Optional local games to run after validation."),
    no_view: bool = typer.Option(False, "--no-view", help="Skip the cockpit after startup."),
) -> None:
    """One-line startup: initialize if needed, build, validate, and show the cockpit."""

    root = _find_or_create_root()
    _bootstrap_project(root, "orbit-wars", preset)
    _build_current(root)
    ok, errors, details = _validate_current(root)
    if not ok:
        for error in errors:
            console.print(f"- {error}", style="red")
        raise typer.Exit(1)
    console.print(f"Agent validated in {details.get('runtime_ms', 0)} ms.")
    if games:
        test_cmd(agent_path=_default_agent_path(root), games=games, opponents="random,starter_sniper,safe_sniper", turns=220)
    if not no_view:
        _dashboard(root)


@app.command()
def view(interactive: bool = typer.Option(False, "--interactive", "-i", help="Show a menu after the cockpit.")) -> None:
    """Show the terminal cockpit for humans."""

    root = require_project_root()
    _dashboard(root)
    if interactive and sys.stdin.isatty():
        _interactive_view(root)


@app.command()
def roles() -> None:
    """Show internal AI role policy."""

    console.print(Markdown(render_roles()))


@app.command()
def new(
    name: str = typer.Argument(..., help="Agent directory name under agents/."),
    preset: str = typer.Option("balanced_ladder", "--preset", help="Preset name."),
) -> None:
    """Create a new agent config from a preset."""

    root = require_project_root()
    config = preset_config(preset)
    config.name = name
    config.sources.append(SourceNote(kind="generated", detail=f"kab new --preset {preset}"))
    config_path = root / "agents" / name / "agent.yaml"
    save_config(config, config_path)
    db.record_agent(root, name, config_path)
    console.print(f"Created {display_path(config_path, root)}")


@app.command("agents")
def agents_cmd() -> None:
    """List local generated agents that can be used as official-test opponents."""

    root = require_project_root()
    table = Table(title="Local Agents", box=box.ASCII)
    table.add_column("Name")
    table.add_column("main.py")
    rows = list_local_agents(root)
    if not rows:
        table.add_row("none", "Run `kab build` or `kab train` first.")
    for row in rows:
        table.add_row(row["name"], row["path"])
    console.print(table)
    console.print("Built-in official opponent: random")


@app.command()
def buffet(
    preset: Optional[str] = typer.Option(None, "--preset", help="Use a named preset instead of interactive prompts."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Where to write agent.yaml."),
) -> None:
    """Choose strategy buffet options and write an agent config."""

    root = require_project_root()
    output = output or _default_config_path(root)
    if preset is None and sys.stdin.isatty():
        preset = questionary.select(
            "Choose your playstyle:",
            choices=[
                "fast_expansion",
                "defensive_turtle",
                "enemy_raider",
                "balanced_ladder",
                "experimental_comet",
                "safe_sniper",
                "starter_sniper",
            ],
        ).ask()
        if preset is None:
            raise typer.Exit(1)
        sun = questionary.select(
            "Do you want the bot to avoid sending fleets through the sun?",
            choices=["Yes, always", "Only for big fleets", "No, keep it simple"],
        ).ask()
        comets = questionary.confirm("Try opportunistic comet handling?", default=False).ask()
    else:
        preset = preset or "balanced_ladder"
        sun = "Yes, always"
        comets = False

    config = preset_config(preset)
    if sun == "No, keep it simple":
        config.physics.sun_avoidance = False
    if comets:
        config.strategy.comet_usage = "opportunistic"
        config.physics.comet_prediction = True
    config.sources.append(SourceNote(kind="buffet", detail=f"preset={preset}"))
    save_config(config, output)
    db.record_agent(root, config.name, output)
    console.print(f"Wrote {display_path(output, root)}")


@app.command()
def build(
    config_path: Optional[Path] = typer.Argument(None, help="agent.yaml path."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output agent directory."),
) -> None:
    """Compile an agent.yaml config into main.py and reports."""

    root = require_project_root()
    config_path = (config_path or _default_config_path(root)).resolve()
    output = (output or config_path.parent).resolve()
    built = _adapter().render_agent(config_path, output)
    config = load_config(config_path)
    db.record_agent(root, config.name, config_path, built["main"])
    table = Table(title="Build Output")
    table.add_column("File")
    table.add_column("Path")
    for label, path in built.items():
        table.add_row(label, display_path(path, root))
    console.print(table)


@app.command("validate")
def validate_cmd(path: Optional[Path] = typer.Argument(None, help="Path to main.py.")) -> None:
    """Validate that an Orbit Wars agent imports and returns legal moves."""

    root = require_project_root()
    path = (path or _default_agent_path(root)).resolve()
    ok, errors, details = _adapter().validate_agent(path)
    table = Table(title="Validation")
    table.add_column("Check")
    table.add_column("Result")
    table.add_row("callable agent(obs)", "ok" if "Import failed" not in " ".join(errors) else "fail")
    table.add_row("runtime", f"{details.get('runtime_ms', 0)} ms")
    table.add_row("valid moves", "ok" if ok else "fail")
    console.print(table)
    if errors:
        for error in errors:
            console.print(f"- {error}", style="red")
        raise typer.Exit(1)
    console.print("Agent validated.")


@app.command("test")
def test_cmd(
    agent_path: Optional[Path] = typer.Option(None, "--agent", help="Path to generated main.py."),
    games: int = typer.Option(50, "--games", min=1, help="Number of local synthetic games."),
    opponents: str = typer.Option("random,starter_sniper,safe_sniper", "--opponents", help="Comma-separated opponents."),
    turns: int = typer.Option(220, "--turns", min=20, help="Turns per local synthetic game."),
) -> None:
    """Run local synthetic Orbit Wars simulations and write a report."""

    root = require_project_root()
    agent_path = (agent_path or _default_agent_path(root)).resolve()
    opponent_list = [item.strip() for item in opponents.split(",") if item.strip()]
    run_id = _utc_stamp()
    run_dir = root / "runs" / run_id
    with console.status(f"Running {games} synthetic games..."):
        metrics = _adapter().run_suite(agent_path, opponent_list, games, turns)
    metrics_path = run_dir / "metrics.json"
    save_metrics(metrics_path, metrics)
    report_text = render_run_report(metrics, agent_path=agent_path, opponents=opponent_list)
    report_path = run_dir / "report.md"
    report_path.write_text(report_text, encoding="utf-8")
    db.record_run(root, run_id, agent_path, opponent_list, metrics.get("games", games), metrics, report_path)
    _print_metrics(metrics)
    console.print(f"Report: {display_path(report_path, root)}")


@app.command("official-test")
def official_test(
    agent: str = typer.Option("current", "--agent", help="Agent name, path, or built-in spec."),
    opponents: str = typer.Option("random", "--opponents", help="Comma-separated opponent names, paths, or built-ins."),
    games: int = typer.Option(1, "--games", min=1, help="Official environment games per opponent."),
    seed: int = typer.Option(42, "--seed", help="First official environment seed."),
    save_replays: bool = typer.Option(False, "--save-replays", help="Save official replay JSON files under runs/."),
) -> None:
    """Run Kaggle's official Orbit Wars environment with make('orbit_wars')."""

    root = require_project_root()
    status = official_env_status()
    if not status.available:
        console.print("Official Orbit Wars environment is not ready.", style="yellow")
        console.print(status.message)
        console.print("")
        console.print("Python 3.11+ is required for kaggle-environments>=1.28.0.")
        console.print('Install on Python 3.11 with: python -m pip install -e ".[official]"', markup=False)
        raise typer.Exit(1)

    opponent_list = [item.strip() for item in opponents.split(",") if item.strip()]
    run_id = f"official_{_utc_stamp()}"
    run_dir = root / "runs" / run_id
    summary: list[dict[str, object]] = []
    for index, opponent in enumerate(opponent_list):
        with console.status(f"Running official Orbit Wars: {agent} vs {opponent}..."):
            result = run_official_games(
                root,
                agent,
                opponent,
                games=games,
                seed=seed + index * games,
                save_dir=run_dir if save_replays else None,
            )
        summary.append(result)

    metrics = {
        "games": sum(int(row["games"]) for row in summary),
        "official": True,
        "package_version": status.package_version,
        "opponents": opponent_list,
        "results": summary,
        "win_rate": round(
            sum(int(row["wins"]) for row in summary) / max(1, sum(int(row["games"]) for row in summary)),
            3,
        ),
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = run_dir / "official_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")

    table = Table(title="Official Orbit Wars Results", box=box.ASCII)
    table.add_column("Agent")
    table.add_column("Opponent")
    table.add_column("Games")
    table.add_column("Wins")
    table.add_column("Win Rate")
    for row in summary:
        win_rate = row.get("win_rate", 0)
        if isinstance(win_rate, float):
            win_rate = f"{win_rate:.1%}"
        table.add_row(str(row["agent"]), str(row["opponent"]), str(row["games"]), str(row["wins"]), str(win_rate))
    console.print(table)
    console.print(f"Saved: {display_path(metrics_path, root)}")


def _print_metrics(metrics: dict[str, object]) -> None:
    table = Table(title="Local Results")
    table.add_column("Metric")
    table.add_column("Value")
    for key in ["games", "win_rate", "avg_final_ship_score", "avg_final_ship_diff", "avg_invalid_moves", "avg_fleets_lost_to_sun", "avg_attacks_arrived_underpowered"]:
        value = metrics.get(key, "")
        if key == "win_rate" and isinstance(value, float):
            value = f"{value:.1%}"
        table.add_row(key, str(value))
    console.print(table)


@app.command()
def report(run_id: str = typer.Argument("last-run", help="Run id or last-run.")) -> None:
    """Render a saved run report."""

    root = require_project_root()
    row = db.latest_run(root) if run_id == "last-run" else db.get_run(root, run_id)
    if row is None:
        console.print("No run found.", style="red")
        raise typer.Exit(1)
    report_path = Path(row["report_path"]) if row.get("report_path") else None
    if report_path and report_path.exists():
        console.print(Markdown(report_path.read_text(encoding="utf-8")))
    else:
        console.print(json.dumps(row["metrics"], indent=2))


@app.command()
def explain(run_id: str = typer.Argument("last-run", help="Run id or last-run.")) -> None:
    """Explain the latest bot and run in coach language."""

    root = require_project_root()
    row = db.latest_run(root) if run_id == "last-run" else db.get_run(root, run_id)
    if row is None:
        console.print("No run found.", style="red")
        raise typer.Exit(1)
    metrics = row["metrics"]
    lines = [
        "Your bot was tested in the local Orbit Wars simulator.",
        "",
        f"- Win rate: {metrics.get('win_rate', 0):.1%}",
        f"- Average final ship difference: {metrics.get('avg_final_ship_diff', 0)}",
        f"- Invalid moves per game: {metrics.get('avg_invalid_moves', 0)}",
        f"- Fleets lost to sun per game: {metrics.get('avg_fleets_lost_to_sun', 0)}",
        "",
    ]
    if metrics.get("avg_fleets_lost_to_sun", 0) > 0:
        lines.append("Main coaching note: turn on or strengthen sun avoidance before submitting.")
    elif metrics.get("win_rate", 0) < 0.5:
        lines.append("Main coaching note: the bot needs stronger target selection or less conservative fleet budgeting.")
    else:
        lines.append("Main coaching note: local results are stable enough for a cautious Kaggle test submission.")
    console.print(Panel("\n".join(lines), title="Coach Explanation"))


@app.command()
def improve(
    goal: str = typer.Option("reduce sun deaths and over-sending", "--goal", help="Plain-English improvement goal."),
    source: Optional[Path] = typer.Option(None, "--source", help="Source agent.yaml."),
    output: Optional[Path] = typer.Option(None, "--output", help="Output agent directory."),
    test_games: int = typer.Option(20, "--test-games", min=0, help="Run tests after build; 0 skips."),
) -> None:
    """Apply a deterministic patch to agent.yaml from a plain-English goal."""

    root = require_project_root()
    source = (source or _default_config_path(root)).resolve()
    config = load_config(source)
    goal_lower = goal.lower()
    if "sun" in goal_lower or "collision" in goal_lower:
        config.physics.sun_avoidance = True
        config.physics.continuous_collision_check = True
        config.physics.sun_radius = max(config.physics.sun_radius, 15.0)
    if "over" in goal_lower or "duplicate" in goal_lower or "send" in goal_lower:
        config.attacks.avoid_oversending = True
        config.attacks.avoid_duplicate_targeting = True
        config.attacks.send_fraction = min(config.attacks.send_fraction, 0.55)
    if "defense" in goal_lower or "reinforce" in goal_lower:
        config.defense.detect_incoming_fleets = True
        config.defense.reinforce_under_attack = True
    if "endgame" in goal_lower or "final" in goal_lower:
        config.strategy.endgame_swarm = True
    config.name = f"{config.name}_improved_{_utc_stamp()}"
    config.sources.append(SourceNote(kind="improve", detail=goal))

    output = (output or (root / "agents" / config.name)).resolve()
    config_path = output / "agent.yaml"
    save_config(config, config_path)
    built = _adapter().render_agent(config_path, output)
    db.record_agent(root, config.name, config_path, built["main"], notes=goal)
    console.print(f"Built improved agent: {display_path(built['main'], root)}")
    if test_games > 0:
        test_cmd(agent_path=built["main"], games=test_games, opponents="random,starter_sniper,safe_sniper", turns=config.testing.turns)


@app.command()
def train(
    games: int = typer.Option(20, "--games", min=1, help="Games per preset."),
    presets: str = typer.Option(
        "balanced_ladder,fast_expansion,safe_sniper,enemy_raider",
        "--presets",
        help="Comma-separated preset names to sweep.",
    ),
    opponents: str = typer.Option("random,starter_sniper,safe_sniper", "--opponents", help="Comma-separated local opponents."),
    promote_best: bool = typer.Option(False, "--promote-best", help="Promote the best variant to agents/current."),
    confirm: bool = typer.Option(False, "--confirm", help="Required with --promote-best."),
) -> None:
    """Run a local preset sweep and rank generated agents."""

    root = require_project_root()
    db.init_db(root)
    preset_list = [item.strip() for item in presets.split(",") if item.strip()]
    opponent_list = [item.strip() for item in opponents.split(",") if item.strip()]
    if not preset_list:
        raise typer.BadParameter("At least one preset is required.")

    stamp = _utc_stamp()
    rows: list[dict[str, object]] = []
    adapter = _adapter()
    for preset_name in preset_list:
        if preset_name not in preset_names():
            console.print(f"Skipping unknown preset: {preset_name}", style="yellow")
            continue
        agent_name = f"train_{stamp}_{preset_name}"
        config = preset_config(preset_name)
        config.name = agent_name
        config.sources.append(SourceNote(kind="train", detail=f"preset sweep {stamp}"))
        agent_dir = root / "agents" / agent_name
        config_path = agent_dir / "agent.yaml"
        save_config(config, config_path)
        built = adapter.render_agent(config_path, agent_dir)
        ok, errors, _ = adapter.validate_agent(built["main"])
        if not ok:
            rows.append({"name": agent_name, "preset": preset_name, "ok": False, "error": "; ".join(errors), "agent_dir": agent_dir})
            continue
        with console.status(f"Training {preset_name}: {games} local games..."):
            metrics = adapter.run_suite(built["main"], opponent_list, games, config.testing.turns)
        run_id = f"{stamp}_{preset_name}"
        run_dir = root / "runs" / run_id
        metrics_path = run_dir / "metrics.json"
        save_metrics(metrics_path, metrics)
        report_text = render_run_report(metrics, agent_path=built["main"], opponents=opponent_list)
        report_path = run_dir / "report.md"
        report_path.write_text(report_text, encoding="utf-8")
        db.record_agent(root, agent_name, config_path, built["main"], notes="training sweep")
        db.record_run(root, run_id, built["main"], opponent_list, metrics.get("games", games), metrics, report_path)
        rows.append({"name": agent_name, "preset": preset_name, "ok": True, "metrics": metrics, "agent_dir": agent_dir, "report": report_path})

    if not rows:
        console.print("No training variants were run.", style="red")
        raise typer.Exit(1)

    rows.sort(
        key=lambda row: (
            bool(row.get("ok")),
            float(row.get("metrics", {}).get("win_rate", 0)) if isinstance(row.get("metrics"), dict) else 0,
            float(row.get("metrics", {}).get("avg_final_ship_diff", 0)) if isinstance(row.get("metrics"), dict) else 0,
        ),
        reverse=True,
    )

    table = Table(title="Training Leaderboard", box=box.ASCII)
    table.add_column("Rank")
    table.add_column("Preset")
    table.add_column("Agent")
    table.add_column("Win Rate")
    table.add_column("Invalid/Game")
    table.add_column("Sun/Game")
    table.add_column("Report")
    for rank, row in enumerate(rows, start=1):
        metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
        win_rate = metrics.get("win_rate", 0)
        if isinstance(win_rate, float):
            win_rate = f"{win_rate:.1%}"
        table.add_row(
            str(rank),
            str(row["preset"]),
            str(row["name"]),
            str(win_rate),
            str(metrics.get("avg_invalid_moves", "fail")),
            str(metrics.get("avg_fleets_lost_to_sun", "fail")),
            _clip_ascii(display_path(Path(row["report"]), root), 38) if row.get("report") else _clip_ascii(row.get("error", ""), 28),
        )
    console.print(table)

    best = rows[0]
    if promote_best:
        if not confirm:
            console.print("Best-agent promotion requires --confirm. No files were overwritten.", style="yellow")
            raise typer.Exit(1)
        source = Path(best["agent_dir"])
        target = root / "agents" / "current"
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / "main.py", target / "main.py")
        shutil.copy2(source / "agent.yaml", target / "agent.yaml")
        if (source / "README.md").exists():
            shutil.copy2(source / "README.md", target / "README.md")
        if (source / "report.md").exists():
            shutil.copy2(source / "report.md", target / "report.md")
        db.record_agent(root, "current", target / "agent.yaml", target / "main.py", notes=f"promoted training winner {best['name']}")
        console.print(f"Promoted {best['name']} to agents/current")


@app.command()
def promote(
    agent_dir: Path = typer.Argument(..., help="Agent directory to promote to agents/current."),
    confirm: bool = typer.Option(False, "--confirm", help="Required to overwrite current champion."),
) -> None:
    """Promote a generated agent directory to agents/current."""

    root = require_project_root()
    if not confirm:
        console.print("Promotion overwrites agents/current. Re-run with --confirm.", style="yellow")
        raise typer.Exit(1)
    source = agent_dir.resolve()
    target = root / "agents" / "current"
    if not (source / "main.py").exists() or not (source / "agent.yaml").exists():
        console.print("Agent directory must contain main.py and agent.yaml.", style="red")
        raise typer.Exit(1)
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "main.py", target / "main.py")
    shutil.copy2(source / "agent.yaml", target / "agent.yaml")
    for optional in ["README.md", "report.md"]:
        if (source / optional).exists():
            shutil.copy2(source / optional, target / optional)
    db.record_agent(root, "current", target / "agent.yaml", target / "main.py", notes=f"promoted from {source}")
    console.print(f"Promoted {display_path(source, root)} to agents/current")


@app.command()
def submit(
    agent_path: Optional[Path] = typer.Option(None, "--agent", help="main.py to submit."),
    competition: str = typer.Option("orbit-wars", "--competition"),
    message: str = typer.Option("Agent Buffet submission", "--message", "-m"),
    confirm: bool = typer.Option(False, "--confirm", help="Required before any Kaggle submit."),
    prompt_token: bool = typer.Option(False, "--prompt-token", help="Prompt for KAGGLE_API_TOKEN without echo."),
) -> None:
    """Submit to Kaggle after explicit confirmation."""

    root = require_project_root()
    agent_path = (agent_path or _default_agent_path(root)).resolve()
    if not confirm:
        console.print("Submit requires --confirm. No Kaggle call was made.", style="yellow")
        raise typer.Exit(1)
    if not agent_path.exists():
        console.print(f"Missing agent file: {agent_path}", style="red")
        raise typer.Exit(1)
    result = _gateway(prompt_token).submit(competition, agent_path, message)
    _print_result(result)


@kaggle_app.command("auth-check")
def kaggle_auth_check(prompt_token: bool = typer.Option(False, "--prompt-token", help="Prompt for KAGGLE_API_TOKEN without echo.")) -> None:
    """Check SDK and installed CLI authentication without saving credentials."""

    gateway = _gateway(prompt_token)
    table = Table(title="Kaggle Auth Check")
    table.add_column("Surface")
    table.add_column("Result")
    table.add_column("Detail")
    table.add_row("CLI installed", "yes" if gateway.cli_available() else "no", gateway.cli_version() or "")
    sdk_ok, sdk_detail = gateway.sdk_whoami()
    table.add_row("KaggleHub SDK", "ok" if sdk_ok else "fail", sdk_detail)
    cli_result = gateway.submissions("orbit-wars")
    detail = (cli_result.stderr or cli_result.stdout).strip().splitlines()
    table.add_row("Classic CLI auth", "ok" if cli_result.ok else "fail", detail[0] if detail else "")
    console.print(table)
    if not sdk_ok and not cli_result.ok:
        raise typer.Exit(1)


@kaggle_app.command()
def submissions(competition: str = typer.Argument("orbit-wars"), prompt_token: bool = typer.Option(False, "--prompt-token")) -> None:
    _print_result(_gateway(prompt_token).submissions(competition))


@kaggle_app.command()
def leaderboard(competition: str = typer.Argument("orbit-wars"), prompt_token: bool = typer.Option(False, "--prompt-token")) -> None:
    _print_result(_gateway(prompt_token).leaderboard(competition))


@kaggle_app.command()
def episodes(submission_id: str, prompt_token: bool = typer.Option(False, "--prompt-token")) -> None:
    _print_result(_gateway(prompt_token).episodes(submission_id))


@kaggle_app.command()
def replay(episode_id: str, prompt_token: bool = typer.Option(False, "--prompt-token")) -> None:
    _print_result(_gateway(prompt_token).replay(episode_id))


@kaggle_app.command()
def logs(episode_id: str, index: int = typer.Argument(0), prompt_token: bool = typer.Option(False, "--prompt-token")) -> None:
    _print_result(_gateway(prompt_token).logs(episode_id, index))


@mine_app.command()
def discussions(
    competition: str = typer.Argument("orbit-wars"),
    sort: str = typer.Option("recent", "--sort"),
    page_size: int = typer.Option(20, "--page-size", min=1, max=200),
    prompt_token: bool = typer.Option(False, "--prompt-token"),
) -> None:
    """Mine public competition discussion topics."""

    root = require_project_root()
    out = root / "cache" / "mining" / f"{_utc_stamp()}_discussions.txt"
    result = _gateway(prompt_token).topics(competition, sort=sort, page_size=page_size)
    _print_result(result, save_to=out)
    db.record_mining_note(root, "discussions", " ".join(result.args), out)


@mine_app.command()
def leaderboard(
    competition: str = typer.Argument("orbit-wars"),
    prompt_token: bool = typer.Option(False, "--prompt-token"),
) -> None:
    """Mine the public leaderboard."""

    root = require_project_root()
    out = root / "cache" / "mining" / f"{_utc_stamp()}_leaderboard.txt"
    result = _gateway(prompt_token).leaderboard(competition)
    _print_result(result, save_to=out)
    db.record_mining_note(root, "leaderboard", " ".join(result.args), out)


@mine_app.command("public-code")
def public_code(
    competition: str = typer.Argument("orbit-wars"),
    prompt_token: bool = typer.Option(False, "--prompt-token"),
) -> None:
    """List public notebooks/kernels associated with the competition."""

    root = require_project_root()
    out = root / "cache" / "mining" / f"{_utc_stamp()}_public_code.txt"
    result = _gateway(prompt_token).run_cli(["kernels", "list", "--competition", competition, "-v"])
    _print_result(result, save_to=out)
    db.record_mining_note(root, "public-code", " ".join(result.args), out)


@mine_app.command()
def digest(limit: int = typer.Option(20, "--limit", min=1)) -> None:
    """Summarize cached public mining outputs into an idea board."""

    root = require_project_root()
    paths = sorted((root / "cache" / "mining").glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    ideas = extract_ideas(paths)
    board = render_idea_board(ideas)
    out = root / "reports" / "public_ideas.md"
    out.write_text(board, encoding="utf-8")
    console.print(Markdown(board))
    console.print(f"Saved: {display_path(out, root)}")


@mine_app.command()
def episodes(submission_id: str, prompt_token: bool = typer.Option(False, "--prompt-token")) -> None:
    root = require_project_root()
    out = root / "cache" / "mining" / f"{_utc_stamp()}_episodes_{submission_id}.txt"
    result = _gateway(prompt_token).episodes(submission_id)
    _print_result(result, save_to=out)
    db.record_mining_note(root, "episodes", " ".join(result.args), out)


@mine_app.command()
def replay(episode_id: str, prompt_token: bool = typer.Option(False, "--prompt-token")) -> None:
    root = require_project_root()
    out = root / "cache" / "mining" / f"{_utc_stamp()}_replay_{episode_id}.txt"
    result = _gateway(prompt_token).replay(episode_id)
    _print_result(result, save_to=out)
    db.record_mining_note(root, "replay", " ".join(result.args), out)


@mine_app.command()
def logs(episode_id: str, index: int = typer.Argument(0), prompt_token: bool = typer.Option(False, "--prompt-token")) -> None:
    root = require_project_root()
    out = root / "cache" / "mining" / f"{_utc_stamp()}_logs_{episode_id}_{index}.txt"
    result = _gateway(prompt_token).logs(episode_id, index)
    _print_result(result, save_to=out)
    db.record_mining_note(root, "logs", " ".join(result.args), out)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
