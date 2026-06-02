from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path


@dataclass
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class KaggleGateway:
    def __init__(self, token: str | None = None) -> None:
        self.token = token

    @classmethod
    def from_env_or_prompt(cls, *, prompt: bool = False) -> "KaggleGateway":
        token = os.getenv("KAGGLE_API_TOKEN")
        if prompt and not token:
            token = getpass("Kaggle API token: ")
        return cls(token=token)

    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        if self.token:
            env["KAGGLE_API_TOKEN"] = self.token
        return env

    def cli_available(self) -> bool:
        return shutil.which("kaggle") is not None

    def cli_version(self) -> str | None:
        if not self.cli_available():
            return None
        result = self.run_cli(["--version"])
        return result.stdout.strip() or result.stderr.strip()

    def sdk_whoami(self) -> tuple[bool, str]:
        try:
            if self.token:
                os.environ["KAGGLE_API_TOKEN"] = self.token
            from kagglehub.auth import whoami
            from kagglehub.config import clear_kaggle_credentials, set_kaggle_api_token

            if self.token:
                set_kaggle_api_token(self.token)
            user = whoami(verbose=False)
            clear_kaggle_credentials()
            return True, str(user.get("username", "authenticated"))
        except Exception as exc:
            return False, type(exc).__name__
        finally:
            if self.token:
                os.environ.pop("KAGGLE_API_TOKEN", None)

    def run_cli(self, args: list[str], *, cwd: Path | None = None, timeout: int = 120) -> CommandResult:
        if not self.cli_available():
            return CommandResult(["kaggle", *args], 127, "", "kaggle executable not found")
        proc = subprocess.run(
            ["kaggle", *args],
            cwd=str(cwd) if cwd else None,
            env=self._env(),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return CommandResult(["kaggle", *args], proc.returncode, proc.stdout, proc.stderr)

    def leaderboard(self, competition: str, *, show: bool = True, csv: bool = True) -> CommandResult:
        args = ["competitions", "leaderboard", competition]
        if show:
            args.append("-s")
        if csv:
            args.append("-v")
        return self.run_cli(args)

    def topics(self, competition: str, *, sort: str = "recent", page_size: int = 20, csv: bool = False) -> CommandResult:
        args = ["competitions", "topics", "list", competition, "-s", sort, "--page-size", str(page_size)]
        if csv:
            args.append("-v")
        return self.run_cli(args)

    def topic_show(self, topic_ref: str, *, page_size: int = 50) -> CommandResult:
        return self.run_cli(["competitions", "topics", "show", topic_ref, "--page-size", str(page_size)])

    def submissions(self, competition: str, *, csv: bool = True) -> CommandResult:
        args = ["competitions", "submissions", competition]
        if csv:
            args.append("-v")
        return self.run_cli(args)

    def episodes(self, submission_id: str) -> CommandResult:
        return self.run_cli(["competitions", "episodes", submission_id])

    def replay(self, episode_id: str) -> CommandResult:
        return self.run_cli(["competitions", "replay", episode_id])

    def logs(self, episode_id: str, index: int = 0) -> CommandResult:
        return self.run_cli(["competitions", "logs", episode_id, str(index)])

    def submit(self, competition: str, file_path: Path, message: str) -> CommandResult:
        return self.run_cli(["competitions", "submit", competition, "-f", str(file_path), "-m", message])
