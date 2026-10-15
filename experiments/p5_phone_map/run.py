"""P5: measure the demo API for the map views a phone asks for.

Starts the API as its own program, asks for squares at several zoom levels and records size, time and memory.
"""

import csv
import gzip
import json
import math
import os
import socket
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from sporameteo.context import RunContext

ROOT = Path(__file__).resolve().parents[2]
TILE_SIZE = 512
TIMEOUT_SECONDS = 30
REQUEST_COLUMNS = [
    "zoom",
    "days_ahead",
    "status",
    "square_count",
    "plain_bytes",
    "gzip_bytes",
    "median_ms",
    "max_ms",
]
MEMORY_COLUMNS = ["moment", "rss_mb"]


def view_bbox(*, longitude: float, latitude: float, zoom: int, width: int, height: int) -> tuple[float, float, float, float]:
    """Return the west, south, east and north edges of a map window.

    Uses the zoom levels of MapLibre, which count 512 pixels per tile.
    """
    scale = TILE_SIZE * 2**zoom
    centre_x = (longitude + 180) / 360 * scale
    sin_lat = math.sin(math.radians(latitude))
    centre_y = (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * scale

    def lon_of(x: float) -> float:
        return x / scale * 360 - 180

    def lat_of(y: float) -> float:
        n = math.pi - 2 * math.pi * y / scale
        return math.degrees(math.atan(math.sinh(n)))

    return (
        lon_of(centre_x - width / 2),
        lat_of(centre_y + height / 2),
        lon_of(centre_x + width / 2),
        lat_of(centre_y - height / 2),
    )


def free_port() -> int:
    """Ask the system for a free local port."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def rss_mb(*, pid: int) -> float:
    """Return the resident memory of a process in megabytes."""
    output = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True, check=True)
    return round(int(output.stdout.strip()) / 1024, 1)


def fetch(*, url: str, use_gzip: bool) -> tuple[int, bytes, float]:
    """Return status, body as sent and time in milliseconds for one GET."""
    headers = {"Accept-Encoding": "gzip"} if use_gzip else {}
    request = urllib.request.Request(url, headers=headers)
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as reply:
            body = reply.read()
            status = reply.status
    except urllib.error.HTTPError as error:
        body = error.read()
        status = error.code
    return status, body, (time.perf_counter() - start) * 1000


def wait_until_up(*, base: str, process: subprocess.Popen) -> None:
    """Wait until the API answers its health address."""
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"API stopped with code {process.returncode}")
        try:
            fetch(url=f"{base}/health", use_gzip=False)
            return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("API did not answer within 20 seconds")


def measure(*, settings: dict[str, Any], base: str, pid: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Ask for every view and day and return request rows and memory rows."""
    memory = [{"moment": "after start", "rss_mb": rss_mb(pid=pid)}]
    status, body, _ = fetch(url=f"{base}/info", use_gzip=False)
    info = json.loads(body)
    assessment_date = info["assessment_dates"][0]
    rows = []
    for zoom in settings["views"]["zooms"]:
        bbox = view_bbox(
            longitude=settings["centre"]["longitude"],
            latitude=settings["centre"]["latitude"],
            zoom=zoom,
            width=settings["window"]["width"],
            height=settings["window"]["height"],
        )
        for days_ahead in settings["days_ahead"]:
            target_date = (date.fromisoformat(assessment_date) + timedelta(days=days_ahead)).isoformat()
            query = urllib.parse.urlencode(
                {
                    "species": settings["species"],
                    "assessment_date": assessment_date,
                    "target_date": target_date,
                    "bbox": ",".join(f"{value:.5f}" for value in bbox),
                }
            )
            url = f"{base}/squares?{query}"
            status, plain, _ = fetch(url=url, use_gzip=False)
            times = []
            for _ in range(settings["repeats"]):
                _, packed, ms = fetch(url=url, use_gzip=True)
                times.append(ms)
            body = json.loads(plain)
            if status == 200:
                assert json.loads(gzip.decompress(packed)) == body
            rows.append(
                {
                    "zoom": zoom,
                    "days_ahead": days_ahead,
                    "status": status,
                    "square_count": body.get("square_count", 0),
                    "plain_bytes": len(plain),
                    "gzip_bytes": len(packed),
                    "median_ms": round(statistics.median(times), 1),
                    "max_ms": round(max(times), 1),
                }
            )
        memory.append({"moment": f"after zoom {zoom}", "rss_mb": rss_mb(pid=pid)})
    return rows, memory


def write_csv(*, rows: list[dict[str, Any]], columns: list[str], path: Path) -> None:
    """Write rows to a CSV file with the given columns."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def run(context: RunContext) -> None:
    """Start the API, measure it and write the two report tables."""
    settings = context.config
    api_dir = ROOT / settings["api_dir"]
    port = free_port()
    environment = {**os.environ, "SPORAMETEO_API_HOST": "127.0.0.1", "SPORAMETEO_API_PORT": str(port)}
    process = subprocess.Popen(
        [sys.executable, "-m", "sporameteo_api"],
        cwd=api_dir,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}/api/v1"
    try:
        wait_until_up(base=base, process=process)
        rows, memory = measure(settings=settings, base=base, pid=process.pid)
    finally:
        process.terminate()
        process.wait(timeout=10)

    context.add_input(api_dir / "sporameteo_api" / "demo_grid.json.gz")
    reports_dir = ROOT / settings["reports_dir"]
    outputs = {
        "p5_api_requests.csv": (rows, REQUEST_COLUMNS),
        "p5_api_memory.csv": (memory, MEMORY_COLUMNS),
    }
    for filename, (table, columns) in outputs.items():
        path = reports_dir / filename
        write_csv(rows=table, columns=columns, path=path)
        context.add_output(path)

    for row in rows:
        print(row)
    for row in memory:
        print(row)
