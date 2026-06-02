# Agent Buffet

A friendly no-code/low-code CLI for building Orbit Wars bots.

Pick a strategy, build a Python agent, run local games, read the results in plain English, mine public Kaggle info, and submit only when you explicitly confirm.

## One-Line Startup

From the project folder:

```bash
./scripts/start.sh
```

That one command creates a local `.venv`, installs the CLI inside it, creates an Orbit Wars workspace if needed, builds the current bot, validates it, and opens the terminal cockpit.

### What The Startup Script Does

`./scripts/start.sh` is the safe default for Linux, WSL, and macOS:

1. Finds `python3`.
2. Creates a project-local virtual environment at `.venv`.
3. Activates that virtual environment.
4. Upgrades `pip` inside `.venv`.
5. Installs Agent Buffet in editable mode with `python -m pip install -e .`.
6. Runs `kab start`.

This is the correct approach on Ubuntu, Debian, and WSL because those systems often block system-wide `pip install` with the `externally-managed-environment` error. The virtual environment keeps this project's Python packages separate from your operating system Python.

### Is This A Sandbox?

No. A Python virtual environment is not a security sandbox.

What `.venv` does:

- isolates Python packages for this project
- avoids breaking system Python
- gives the CLI its own `kab` command
- makes install/uninstall cleaner

What `.venv` does not do:

- it does not block filesystem access
- it does not block network access
- it does not safely contain untrusted code
- it does not protect secrets by itself

Agent Buffet still protects the risky actions at the CLI level: Kaggle tokens are prompted without echo, credential files are not written by the tool, and Kaggle submit requires `--confirm`.

If your Linux/WSL machine is missing venv support:

```bash
sudo apt update && sudo apt install -y python3-venv
./scripts/start.sh
```

Manual Linux/macOS version:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .
kab start
```

On Windows PowerShell:

```powershell
.\scripts\start.ps1
```

## What It Looks Like

```text
    ___                    __     ____        ________     __
   /   | ____ ____  ____  / /_   / __ )__  __/ __/ __/__  / /_
  / /| |/ __ `/ _ \/ __ \/ __/  / __  / / / / /_/ /_/ _ \/ __/
 / ___ / /_/ /  __/ / / / /_   / /_/ / /_/ / __/ __/  __/ /_
/_/  |_\__, /\___/_/ /_/\__/  /_____/\__,_/_/ /_/  \___/\__/
      /____/

+------------------------ Cockpit ------------------------+
| System       | State       | Detail                     |
| Project      | ready       | .                          |
| Config       | ready       | agents/current/agent.yaml  |
| Agent        | ready       | agents/current/main.py     |
| Kaggle token | not linked  | auth-check --prompt-token  |
+---------------------------------------------------------+

+---------------------- Next Moves -----------------------+
| Pick a bot style   | kab buffet                         |
| Build and validate | kab start --no-view                |
| Run local games    | kab test --games 100               |
| Train preset sweep | kab train --games 20               |
| Link Kaggle safely | kab kaggle auth-check --prompt-token |
+---------------------------------------------------------+
```

Works in normal terminals on macOS, Linux, and Windows. It uses Rich tables and ASCII-safe boxes.

## Quick Commands

```bash
kab view
kab view --interactive
kab buffet
kab build
kab validate
kab test --games 100
kab official-test --games 1 --opponents random
kab agents
kab train --games 20
kab report
kab explain
```

## Link Kaggle Safely

The safest flow is a hidden prompt:

```bash
kab kaggle auth-check --prompt-token
```

The token is used for that process only. Agent Buffet does not write `kaggle.json`, access-token files, shell profiles, or `.env` files.

If you prefer environment variables, use a temporary shell value:

macOS/Linux:

```bash
export KAGGLE_API_TOKEN="paste-token-here"
kab kaggle auth-check
```

Windows PowerShell:

```powershell
$env:KAGGLE_API_TOKEN="paste-token-here"
kab kaggle auth-check
```

Never commit a real token. `.gitignore` blocks common Kaggle credential files and local runtime state.

## Orbit Wars Flow

```bash
kab start
kab buffet --preset balanced_ladder
kab build
kab validate
kab test --games 100 --opponents random,starter_sniper,safe_sniper
kab official-test --games 1 --opponents random
kab explain
kab train --games 20
kab mine discussions --sort recent
kab mine digest
kab submit --confirm
```

Submit is always gated by `--confirm`.

## Strategy Presets

- `starter_sniper`
- `safe_sniper`
- `balanced_ladder`
- `fast_expansion`
- `defensive_turtle`
- `enemy_raider`
- `experimental_comet`
- `advanced_from_submission77`

Configs live in `agents/<name>/agent.yaml`. Generated Kaggle-ready Python agents live beside them as `main.py`.

## What Local Testing Measures

- win rate
- average final ship score
- average planet count
- production controlled
- invalid moves
- timeout turns
- fleets lost to sun
- underpowered attacks
- neutral and enemy captures
- reinforcements sent

The simulator is intentionally lightweight. Treat it as a fast smoke-test and coaching loop, not a perfect copy of Kaggle's official engine.

## Official Kaggle Environment Test

Orbit Wars official local testing uses Kaggle Environments:

```bash
python -m pip install "kaggle-environments>=1.28.0"
```

That package requires Python 3.11 or newer. Once installed, run:

```bash
kab official-test --agent current --opponents random --games 1 --seed 42 --save-replays
```

Under the hood this does the same thing as:

```python
from kaggle_environments import make

env = make("orbit_wars", configuration={"seed": 42}, debug=True)
env.run(["main.py", "random"])
```

You can test against saved local agents too:

```bash
kab agents
kab official-test --agent current --opponents train_20260602_225231_safe_sniper --games 3
```

In `kab view --interactive`, choose:

```text
Run official Kaggle env game
```

That is the simple terminal "button" for humans.

## Secret Safety

This project should not contain:

- Kaggle API tokens
- `kaggle.json`
- `.env` files
- access-token files
- personal leaderboard notes with private identifiers
- local SQLite run databases

Before publishing:

```bash
rg "KGAT_|KAGGLE_(USERNAME|KEY|API_TOKEN)=|kaggle.json|access_token|secret|api_key"
```

The source code mentions `KAGGLE_API_TOKEN` as an environment variable name only. That is expected.

## Install Notes

Python 3.10+ is recommended.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
kab --help
```

Optional Kaggle packages are detected at runtime:

```bash
python -m pip install -e ".[kaggle]"
```
