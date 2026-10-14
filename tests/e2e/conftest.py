"""Start a local Django server for browser checks without a test database."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest
from playwright.sync_api import Page


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANAGE_PY = PROJECT_ROOT / "apps" / "application" / "manage.py"


def _server_ready(*, url: str) -> bool:
    try:
        with urlopen(url=f"{url}/map/", timeout=1) as response:
            return response.status == 200
    except (OSError, URLError):
        return False


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture(scope="session")
def app_server() -> Iterator[str]:
    """Provide a local app URL, starting Django when one is not already running."""
    configured_url = os.environ.get("MICOMETEO_BASE_URL")
    if configured_url:
        base_url = configured_url.rstrip("/")
        for _ in range(75):
            if _server_ready(url=base_url):
                yield base_url
                return
            time.sleep(0.2)
        raise RuntimeError(f"Configured Django server did not answer at {base_url}")

    configured_e2e_url = os.environ.get("MICOMETEO_E2E_URL")
    if configured_e2e_url:
        base_url = configured_e2e_url.rstrip("/")
    else:
        base_url = f"http://127.0.0.1:{_free_port()}"

    host_port = base_url.rsplit(":", maxsplit=1)[-1]
    server_environment = os.environ.copy()
    server_environment.update(
        {
            "MICOMETEO_DEBUG": "true",
            "MICOMETEO_UI_FIXTURE_PAGES": "true",
        }
    )
    # A pipe fills during the full browser suite and blocks Django's request log.
    server_log = tempfile.TemporaryFile(mode="w+")
    process = subprocess.Popen(
        [
            sys.executable,
            str(MANAGE_PY),
            "runserver",
            f"127.0.0.1:{host_port}",
            "--noreload",
        ],
        cwd=PROJECT_ROOT,
        env=server_environment,
        stdout=server_log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        for _ in range(75):
            if _server_ready(url=base_url):
                yield base_url
                return
            if process.poll() is not None:
                process.wait(timeout=1)
                server_log.seek(0)
                output = server_log.read()
                raise RuntimeError(f"Django browser server exited early:\n{output}")
            time.sleep(0.2)
        raise RuntimeError(f"Django browser server did not answer at {base_url}")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        server_log.close()


@pytest.fixture(scope="session")
def base_url(app_server: str) -> str:
    """Return the server URL used by browser checks."""
    return app_server


@pytest.fixture
def page(page: Page) -> Page:
    """Slow down chromium when MICOMETEO_E2E_CPU_SLOWDOWN is set, for example to 4.

    This reproduces slow CI timing locally. Webkit ignores the setting.
    """
    rate = os.environ.get("MICOMETEO_E2E_CPU_SLOWDOWN")
    if rate and page.context.browser.browser_type.name == "chromium":
        session = page.context.new_cdp_session(page)
        session.send("Emulation.setCPUThrottlingRate", {"rate": float(rate)})
    return page
