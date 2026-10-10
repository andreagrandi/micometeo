"""Run one experiment in a child process with a time limit and write a run record."""

import importlib.metadata
import importlib.util
import json
import multiprocessing
import os
import platform
import secrets
import shutil
import subprocess
import tempfile
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from micometeo import __version__
from micometeo.config import ExperimentConfig, load_config
from micometeo.context import RunContext

KILL_GRACE_SECONDS = 3.0


def make_run_id() -> str:
    """Return a UTC timestamp with a short random suffix."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{secrets.token_hex(3)}"


def _iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _child_main(
    *,
    run_file: str,
    config: dict[str, Any],
    seed: int,
    run_id: str,
    raw_dir: str,
    output_dir: str,
    state_path: str,
) -> None:
    """Load run.py by path and call its run function."""
    context = RunContext(
        config=config,
        seed=seed,
        run_id=run_id,
        raw_dir=Path(raw_dir),
        output_dir=Path(output_dir),
        state_path=Path(state_path),
    )
    try:
        spec = importlib.util.spec_from_file_location("experiment_run", run_file)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load {run_file}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.run(context)
    except BaseException as error:
        context.set_error(f"{type(error).__name__}: {error}")
        traceback.print_exc()
        raise SystemExit(1) from error


def _git_info(*, root: Path) -> dict[str, Any]:
    def git(*args: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", *args], cwd=root, capture_output=True, text=True, timeout=30
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return result.stdout.strip() if result.returncode == 0 else None

    commit = git("rev-parse", "HEAD")
    status = git("status", "--porcelain")
    return {
        "commit": commit,
        "uncommitted_changes": None if status is None else bool(status),
    }


def _relative_path(*, path: str, root: Path) -> str:
    """Return the path relative to the repository root when it is inside it.

    Records are committed, so they must not contain the local home folder.
    """
    try:
        return str(Path(path).resolve().relative_to(root.resolve()))
    except ValueError:
        return path


def _total_ram_bytes() -> int | None:
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        return None


def _versions() -> dict[str, Any]:
    packages = {
        dist.metadata["Name"]: dist.version
        for dist in importlib.metadata.distributions()
        if dist.metadata["Name"]
    }
    return {
        "python": platform.python_version(),
        "micometeo": __version__,
        "packages": dict(sorted(packages.items(), key=lambda item: item[0].lower())),
    }


def _computer() -> dict[str, Any]:
    return {
        "os": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "processor": platform.processor(),
        "total_ram_bytes": _total_ram_bytes(),
    }


def _stop(process: multiprocessing.process.BaseProcess) -> None:
    process.terminate()
    process.join(timeout=KILL_GRACE_SECONDS)
    if process.is_alive():
        process.kill()
        process.join()


def run_experiment(
    *,
    name: str,
    root: Path,
    time_limit_seconds: float | None = None,
) -> Path:
    """Run an experiment and return the path of its run record."""
    experiment_dir = root / "experiments" / name
    config: ExperimentConfig = load_config(path=experiment_dir / "config.toml")
    run_file = experiment_dir / "run.py"
    if not run_file.is_file():
        raise FileNotFoundError(f"Experiment script not found: {run_file}")
    limit = (
        time_limit_seconds
        if time_limit_seconds is not None
        else config.time_limit_minutes * 60
    )
    run_id = make_run_id()
    raw_dir = root / "data" / "raw" / name
    output_dir = root / "data" / "processed" / name / run_id
    git = _git_info(root=root)

    temp_dir = Path(tempfile.mkdtemp(prefix="micometeo_run_"))
    state_path = temp_dir / "state.json"
    started = datetime.now(UTC)
    clock = time.monotonic()
    ctx = multiprocessing.get_context("spawn")
    process = ctx.Process(
        target=_child_main,
        kwargs={
            "run_file": str(run_file),
            "config": config.settings,
            "seed": config.seed,
            "run_id": run_id,
            "raw_dir": str(raw_dir),
            "output_dir": str(output_dir),
            "state_path": str(state_path),
        },
    )
    process.start()
    process.join(timeout=limit)
    duration = time.monotonic() - clock
    status = "completed"
    error: str | None = None
    if process.is_alive():
        _stop(process)
        status = "timed_out"
        error = f"Run stopped after the time limit of {limit} seconds"
    finished = datetime.now(UTC)

    state: dict[str, Any] = {}
    if state_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8"))
    if status != "timed_out" and process.exitcode != 0:
        status = "failed"
        error = state.get("error") or f"Process exited with code {process.exitcode}"

    record = {
        "experiment": name,
        "run_id": run_id,
        "command": f"micometeo run {name}",
        "status": status,
        "error": error,
        "started_at": _iso(started),
        "finished_at": _iso(finished),
        "duration_seconds": round(duration, 3),
        "time_limit_seconds": limit,
        "seed": config.seed,
        "config": config.as_dict(),
        "git": git,
        "versions": _versions(),
        "computer": _computer(),
        "inputs": [
            {**item, "path": _relative_path(path=item["path"], root=root)}
            for item in state.get("inputs", [])
        ],
        "sources": state.get("sources", []),
        "outputs": [
            _relative_path(path=item, root=root) for item in state.get("outputs", [])
        ],
    }
    record_path = root / "reports" / "runs" / name / f"{run_id}.json"
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    shutil.rmtree(temp_dir, ignore_errors=True)
    return record_path
