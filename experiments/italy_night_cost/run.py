"""Italy night cost: measure one night for all Italy on a disposable local database.

The script runs on the laptop. It copies the national builds into a new database, starts the app image once per phase
and records time, memory, exit code and database growth of each phase. It calls no weather API. The weather comes from
the Open-Meteo files, read by the app code inside the container.

Run all steps with `uv run sporameteo run italy_night_cost`. The whole sequence takes longer than the 30 minute limit of one run,
so start it in parts with `steps` in config.toml, or run `uv run python experiments/italy_night_cost/run.py --steps weather`.
"""

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
EXPERIMENT_DIR = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "reports" / "runs" / "italy_night_cost"
JRC_DIR = ROOT / "data" / "raw" / "jrc_host_trees"
WORK_ROOT = ROOT / "data" / "processed" / "italy_night_cost" / "work"
REQUIRED_NAME_PART = "estimate_benchmark"
KILLED_EXIT_CODE = 137
DEFAULT_PASSWORD = "replace-with-a-local-password"
STEP_NAMES = (
    "database",
    "weather",
    "first_night",
    "night",
    "warmup_unlimited",
    "night_384mb",
    "warmup_384mb",
    "tuscany",
    "tuscany_old",
    "weather_night",
    "weather_night_384mb",
    "weather_first_load_384mb",
)
# Tables whose rows are counted in every size snapshot, besides the host tree and map cache tables.
COUNTED_TABLES = ("estimate_updates_estimateresult", "weather_summaries_weatherdaily")


def now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(text: str) -> None:
    print(f"[{datetime.now(UTC).strftime('%H:%M:%S')}] {text}", flush=True)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


def check_database_name(*, settings: dict[str, Any]) -> None:
    """Refuse any target name that is not a disposable benchmark database."""
    name = settings["database"]
    if not re.fullmatch(r"[a-z0-9_]+", name) or REQUIRED_NAME_PART not in name:
        raise ValueError(f"The database name {name!r} must be lowercase letters, digits and underscores, and contain {REQUIRED_NAME_PART}.")
    if name == settings["source_database"]:
        raise ValueError("The target database cannot be the source database.")


def psql(*, settings: dict[str, Any], sql: str, database: str | None = None) -> str:
    """Run one SQL statement in the database container and return its plain output."""
    command = [
        "docker", "exec", "-i", settings["database_container"],
        "psql", "-U", settings["database_user"], "-d", database or "postgres",
        "-v", "ON_ERROR_STOP=1", "-At", "-F", "|", "-c", sql,
    ]  # fmt: skip
    done = subprocess.run(command, capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"psql failed: {done.stderr.strip()}")
    return done.stdout.strip()


def truncate_tables(*, settings: dict[str, Any], groups: list[str]) -> None:
    """Empty the tables of the groups with TRUNCATE, so the sizes of later snapshots stay comparable."""
    tables = [table for group in groups for table in (settings[group] if isinstance(settings[group], list) else [settings[group]])]
    psql(settings=settings, database=settings["database"], sql=f"TRUNCATE {', '.join(tables)} RESTART IDENTITY")


def create_database(*, settings: dict[str, Any]) -> dict[str, Any]:
    """Copy the source database into the target and empty the weather, estimate and map cache tables."""
    check_database_name(settings=settings)
    name, source = settings["database"], settings["source_database"]
    busy = int(psql(settings=settings, sql=f"SELECT count(*) FROM pg_stat_activity WHERE datname = '{source}'"))
    if busy:
        raise RuntimeError(f"{busy} connections are open on {source}. Close them first, createdb -T needs none.")
    exists = psql(settings=settings, sql=f"SELECT 1 FROM pg_database WHERE datname = '{name}'") == "1"
    if exists:
        if not settings["drop_existing_database"]:
            raise RuntimeError(f"The database {name} exists. Set drop_existing_database to replace it.")
        log(f"Dropping {name}")
        psql(settings=settings, sql=f"DROP DATABASE {name} WITH (FORCE)")
    log(f"Creating {name} from {source}")
    started = time.monotonic()
    done = subprocess.run(
        ["docker", "exec", settings["database_container"], "createdb", "-U", settings["database_user"], "-T", source, name],
        capture_output=True,
        text=True,
    )
    if done.returncode != 0:
        raise RuntimeError(f"createdb failed: {done.stderr.strip()}")
    seconds = round(time.monotonic() - started, 1)
    truncate_tables(settings=settings, groups=["weather_tables", "estimate_tables", "map_cache_table"])
    return {"seconds_create": seconds}


def size_snapshot(*, settings: dict[str, Any]) -> dict[str, Any]:
    """Return the size in bytes of the tables by group, the database size and some row counts."""
    rows = psql(
        settings=settings,
        database=settings["database"],
        sql="SELECT relname, pg_total_relation_size(oid) FROM pg_class WHERE relkind = 'r' AND relnamespace = 'public'::regnamespace",
    )
    sizes = {name: int(size) for name, size in (line.split("|") for line in rows.splitlines())}

    def total(prefixes: list[str], names: list[str]) -> int:
        return sum(size for name, size in sizes.items() if name in names or any(name.startswith(prefix) for prefix in prefixes))

    groups = {
        "weather": total(["weather_summaries_", "weather_on_demand_", "weather_requests_"], []),
        "estimates": total(["estimate_updates_estimate", "estimate_updates_forecast", "estimate_updates_published"], settings["estimate_tables"]),
        "host_trees": total([], [settings["host_tree_table"]]),
        "map_cache": total([], [settings["map_cache_table"]]),
    }
    counts = {
        table: int(psql(settings=settings, database=settings["database"], sql=f"SELECT count(*) FROM {table}"))
        for table in (*COUNTED_TABLES, settings["host_tree_table"], settings["map_cache_table"])
    }
    return {
        "taken_at": now_utc(),
        "database_bytes": int(psql(settings=settings, sql=f"SELECT pg_database_size('{settings['database']}')")),
        "groups_bytes": groups,
        "row_counts": counts,
        "tables_bytes": {name: size for name, size in sizes.items() if name in COUNTED_TABLES or name.startswith(("weather_", "estimate_updates_", "sporameteo_map"))},
    }


# ---------------------------------------------------------------------------
# Container
# ---------------------------------------------------------------------------


def ensure_image(*, settings: dict[str, Any]) -> None:
    """Build the app image from the Dockerfile unless it exists and a rebuild is not asked."""
    present = subprocess.run(["docker", "image", "inspect", settings["image"]], capture_output=True).returncode == 0
    if present and not settings["rebuild_image"]:
        log(f"Image {settings['image']} exists")
        return
    log(f"Building image {settings['image']}")
    subprocess.run(["docker", "build", "-t", settings["image"], str(ROOT)], check=True)


def run_phase(*, settings: dict[str, Any], work_dir: Path, name: str, arguments: list[str], limited: bool) -> dict[str, Any]:
    """Run one phase in a container and return its exit code, the JSON it printed and the size snapshots."""
    container = f"italy-night-{name}"
    password = os.environ.get("SPORAMETEO_DB_PASSWORD", DEFAULT_PASSWORD)
    command = ["docker", "run", "--rm", "--name", container, "--network", settings["docker_network"], "--cpus", str(settings["cpus"])]
    if limited:
        command += ["--memory", settings["limited_memory"], "--memory-swap", settings["limited_memory"]]
    command += [
        "-e", "DATABASE_URL",
        "-e", "SPORAMETEO_DJANGO_SECRET_KEY=italy-night-cost-secret",
        "-e", "SPORAMETEO_DEBUG=0",
        "-e", f"SPORAMETEO_FOREST_BUILD_VERSION={settings['forest_build_version']}",
        "-e", f"SPORAMETEO_TERRAIN_BUILD_VERSION={settings['terrain_build_version']}",
        "-e", "SPORAMETEO_JRC_DIRECTORY=/jrc",
        "-v", f"{EXPERIMENT_DIR}:/experiment:ro",
        "-v", f"{JRC_DIR}:/jrc:ro",
        "-v", f"{work_dir}:/output",
        settings["image"],
        "python", "/experiment/phase.py", *arguments,
        "--assessment-date", settings["assessment_date"],
        "--forest-build-version", settings["forest_build_version"],
    ]  # fmt: skip
    environment = {
        **os.environ,
        "DATABASE_URL": f"postgres://{settings['database_user']}:{password}@database:5432/{settings['database']}",
    }
    (work_dir / "logs").mkdir(parents=True, exist_ok=True)
    log_path = work_dir / "logs" / f"{name}.log"
    before = size_snapshot(settings=settings)
    log(f"Phase {name}: {' '.join(arguments)}{' with ' + settings['limited_memory'] if limited else ''}")
    started_at, started = now_utc(), time.monotonic()
    result: dict[str, Any] | None = None
    try:
        process = subprocess.Popen(command, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        with log_path.open("w", encoding="utf-8") as log_file:
            for line in process.stdout:
                log_file.write(line)
                log_file.flush()
                print(f"    {line}", end="", flush=True)
                if line.startswith("{"):
                    try:
                        result = json.loads(line)
                    except json.JSONDecodeError:
                        pass
        exit_code = process.wait()
    finally:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True)
    seconds = round(time.monotonic() - started, 1)
    killed = exit_code == KILLED_EXIT_CODE
    status = "killed_for_memory" if killed and limited else (result or {}).get("status", "no_result")
    log(f"Phase {name} ended with exit code {exit_code}, status {status}, {seconds} s")
    return {
        "name": name,
        "arguments": arguments,
        "memory_limit": settings["limited_memory"] if limited else None,
        "started_at": started_at,
        "wall_seconds": seconds,
        "exit_code": exit_code,
        "killed_for_memory": killed and limited,
        "status": status,
        "result": result,
        "log": str(log_path.relative_to(ROOT)),
        "size_before": before,
        "size_after": size_snapshot(settings=settings),
    }


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


def estimate_arguments(*, settings: dict[str, Any], label: str, region: str | None = None) -> list[str]:
    return ["estimates", "--region", region or settings["estimate_region"], "--label", label, "--limit-cells", str(settings["limit_cells"])]


def warmup_arguments(*, settings: dict[str, Any], mode: str) -> list[str]:
    return ["warmup", "--mode", mode, "--region", settings["estimate_region"], "--limit-tiles", str(settings["limit_tiles"])]


def step_plan(*, settings: dict[str, Any], step: str, results: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the phases of a step, each with its container name, arguments, memory limit and tables to empty first."""
    if step == "weather":
        arguments = ["weather", "--region", settings["weather_region"], "--limit-cells", str(settings["limit_cells"])]
        return [{"name": "weather", "arguments": arguments, "limited": False}]
    if step == "first_night":
        return [{"name": "first_night", "arguments": estimate_arguments(settings=settings, label="first_night"), "limited": False}]
    if step == "night":
        return [{"name": "night", "arguments": estimate_arguments(settings=settings, label="night"), "limited": False, "empty": True}]
    if step == "warmup_unlimited":
        return [
            {"name": "warmup_cold", "arguments": warmup_arguments(settings=settings, mode="cold"), "limited": False},
            {"name": "warmup_night", "arguments": warmup_arguments(settings=settings, mode="night"), "limited": False},
        ]
    if step == "night_384mb":
        return [{"name": "night_384mb", "arguments": estimate_arguments(settings=settings, label="night_384mb"), "limited": True, "empty": True}]
    if step == "warmup_384mb":
        phases = []
        previous = results.get("night_384mb", {}).get("phases", [])
        if not previous or previous[-1]["status"] != "completed":
            # The 384 MB estimates did not finish, so the warm-up needs a run from an unlimited pass.
            phases.append({"name": "night_rerun", "arguments": estimate_arguments(settings=settings, label="night_rerun"), "limited": False, "empty": True})
        phases += [
            {"name": "warmup_cold_384mb", "arguments": warmup_arguments(settings=settings, mode="cold"), "limited": True},
            {"name": "warmup_night_384mb", "arguments": warmup_arguments(settings=settings, mode="night"), "limited": True},
        ]
        return phases
    if step == "tuscany":
        return [{"name": "tuscany", "arguments": estimate_arguments(settings=settings, label="tuscany", region="09"), "limited": False, "empty": True}]
    if step == "tuscany_old":
        # The image holds the master code, so the speed shows what the VPS ran on 17 October.
        return [
            {
                "name": "tuscany_old",
                "arguments": estimate_arguments(settings=settings, label="tuscany_old", region="09"),
                "limited": False,
                "empty": True,
                "override": {"image": settings["master_image"]},
            }
        ]
    if step in ("weather_night", "weather_night_384mb"):
        night = {"assessment_date": settings["night_assessment_date"]}
        limited = step == "weather_night_384mb"
        arguments = ["weather", "--region", settings["weather_region"], "--limit-cells", str(settings["limit_cells"])]
        return [
            # Delete the night of an earlier try, so the read starts from the state after the 17 October night.
            {"name": f"{step}_rewind", "arguments": ["rewind"], "limited": False, "override": night},
            {"name": step, "arguments": arguments, "limited": limited, "override": night},
        ]
    if step == "weather_first_load_384mb":
        # Empty all weather and estimates, so the read has to download the whole window of 38 days.
        arguments = ["weather", "--region", settings["weather_region"], "--limit-cells", str(settings["limit_cells"])]
        return [{"name": step, "arguments": arguments, "limited": True, "empty_weather": True}]
    raise ValueError(f"Unknown step {step!r}.")


def ensure_master_image(*, settings: dict[str, Any]) -> None:
    """Build an image from the master branch in a temporary git worktree, so working tree changes stay out."""
    present = subprocess.run(["docker", "image", "inspect", settings["master_image"]], capture_output=True).returncode == 0
    if present and not settings["rebuild_image"]:
        log(f"Image {settings['master_image']} exists")
        return
    tree = Path(settings["master_worktree"])
    log(f"Building {settings['master_image']} from {settings['master_branch']} in {tree}")
    subprocess.run(["git", "worktree", "add", "--detach", str(tree), settings["master_branch"]], cwd=ROOT, check=True)
    try:
        subprocess.run(["docker", "build", "-t", settings["master_image"], str(tree)], check=True)
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(tree)], cwd=ROOT, check=False)


def run_step(*, settings: dict[str, Any], work_dir: Path, step: str, results: dict[str, Any]) -> dict[str, Any]:
    """Run the phases of one step and return its record."""
    started_at = now_utc()
    if step == "database":
        extra = create_database(settings=settings)
        return {"step": step, "started_at": started_at, **extra, "phases": [], "size_after": size_snapshot(settings=settings)}
    before = size_snapshot(settings=settings)
    phases: list[dict[str, Any]] = []
    for phase in step_plan(settings=settings, step=step, results=results):
        if phase.get("empty"):
            truncate_tables(settings=settings, groups=["estimate_tables"])
        if phase.get("empty_weather"):
            truncate_tables(settings=settings, groups=["weather_tables", "estimate_tables"])
        if "image" in phase.get("override", {}):
            ensure_master_image(settings=settings)
        phase_settings = {**settings, **phase.get("override", {})}
        phases.append(run_phase(settings=phase_settings, work_dir=work_dir, name=phase["name"], arguments=phase["arguments"], limited=phase["limited"]))
    return {"step": step, "started_at": started_at, "phases": phases, "size_before": before, "size_after": size_snapshot(settings=settings)}


def vps_comparison(*, settings: dict[str, Any], results: dict[str, Any]) -> dict[str, Any]:
    """Scale the VPS Tuscany night to Italy by forest squares, and by the local speed ratio when the local Tuscany pass exists."""
    vps = settings["vps"]

    def estimates_of(step: str, name: str) -> dict[str, Any] | None:
        for phase in results.get(step, {}).get("phases", []):
            if phase["name"] == name and phase["status"] == "completed":
                return phase["result"]
        return None

    italy, tuscany = estimates_of("night", "night"), estimates_of("tuscany", "tuscany")
    comparison: dict[str, Any] = {"vps": vps}
    if italy:
        comparison["by_squares_seconds"] = round(vps["forecast_seconds"] * italy["squares"] / vps["forecast_squares"], 1)
    if italy and tuscany:
        comparison["by_local_speed_seconds"] = round(vps["forecast_seconds"] * italy["seconds"] / tuscany["seconds"], 1)
        comparison["local_tuscany_seconds"] = tuscany["seconds"]
        comparison["local_tuscany_squares"] = tuscany["squares"]
    return comparison


def run_sequence(*, settings: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    """Run the wanted steps in order, keep one result file per step, and return all results found so far."""
    check_database_name(settings=settings)
    unknown = [step for step in [*settings["steps"], *settings["rerun_steps"]] if step not in STEP_NAMES]
    if unknown:
        raise ValueError(f"Unknown steps {unknown}. Valid steps are {list(STEP_NAMES)}.")
    results_dir = work_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(1))
    wanted = [step for step in STEP_NAMES if step in settings["steps"]]
    creates_database = "database" in wanted and ("database" in settings["rerun_steps"] or not (results_dir / "database.json").exists())
    if not creates_database:
        exists = psql(settings=settings, sql=f"SELECT 1 FROM pg_database WHERE datname = '{settings['database']}'") == "1"
        if not exists:
            raise RuntimeError(f"The database {settings['database']} does not exist. Run the database step first.")
    if any(step != "database" for step in wanted):
        ensure_image(settings=settings)

    results: dict[str, Any] = {}
    for step in STEP_NAMES:
        path = results_dir / f"{step}.json"
        if step in wanted and (step in settings["rerun_steps"] or not path.exists()):
            results[step] = run_step(settings=settings, work_dir=work_dir, step=step, results=results)
            path.write_text(json.dumps(results[step], indent=2) + "\n", encoding="utf-8")
        elif path.exists():
            results[step] = json.loads(path.read_text(encoding="utf-8"))
            if step in wanted:
                log(f"Step {step} skipped, its result exists in {path}")
    return {
        "database": settings["database"],
        "assessment_date": settings["assessment_date"],
        "written_at": now_utc(),
        "steps": results,
        "vps_comparison": vps_comparison(settings=settings, results=results),
    }


def load_settings() -> dict[str, Any]:
    with (EXPERIMENT_DIR / "config.toml").open("rb") as handle:
        return tomllib.load(handle)["settings"]


def work_directory(*, settings: dict[str, Any]) -> Path:
    path = WORK_ROOT / settings["database"]
    path.mkdir(parents=True, exist_ok=True)
    return path


def run(context: Any) -> None:
    """Run the wanted steps and write the measurements to reports/runs/italy_night_cost/."""
    settings = dict(context.config)
    summary = run_sequence(settings=settings, work_dir=work_directory(settings=settings))
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"measurements_{settings['database']}.json"
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    context.add_output(path)


def main() -> None:
    """Run the same sequence from the command line, with a few settings changed for a quick check."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", help="Comma separated steps to run, instead of steps in config.toml.")
    parser.add_argument("--rerun", help="Comma separated steps to run again even when they have a result.")
    parser.add_argument("--database")
    parser.add_argument("--weather-region")
    parser.add_argument("--estimate-region")
    parser.add_argument("--limit-cells", type=int)
    parser.add_argument("--limit-tiles", type=int)
    parser.add_argument("--output", help="Write the measurements here instead of reports/runs/italy_night_cost/.")
    options = parser.parse_args()
    settings = load_settings()
    for key, value in (
        ("steps", options.steps.split(",") if options.steps else None),
        ("rerun_steps", options.rerun.split(",") if options.rerun else None),
        ("database", options.database),
        ("weather_region", options.weather_region),
        ("estimate_region", options.estimate_region),
        ("limit_cells", options.limit_cells),
        ("limit_tiles", options.limit_tiles),
    ):
        if value is not None:
            settings[key] = value
    summary = run_sequence(settings=settings, work_dir=work_directory(settings=settings))
    path = Path(options.output) if options.output else REPORTS_DIR / f"measurements_{settings['database']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    log(f"Measurements written to {path}")


if __name__ == "__main__":
    main()
