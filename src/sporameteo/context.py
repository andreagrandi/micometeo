"""Run context handed to each experiment.

Every add call saves the collected data to disk, so the parent can read it after a kill.
"""

import hashlib
import json
import os
import random
from pathlib import Path
from typing import Any


def file_sha256(path: Path) -> str:
    """Return the SHA-256 hash of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class RunContext:
    """Settings and recording methods for one experiment run."""

    def __init__(
        self,
        *,
        config: dict[str, Any],
        seed: int,
        run_id: str,
        raw_dir: Path,
        output_dir: Path,
        state_path: Path,
    ) -> None:
        self.config = config
        self.seed = seed
        self.run_id = run_id
        self.raw_dir = raw_dir
        self.output_dir = output_dir
        self._state_path = state_path
        self._state: dict[str, Any] = {
            "sources": [],
            "inputs": [],
            "outputs": [],
            "error": None,
        }
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        random.seed(seed)
        self.save_state()

    def add_source(
        self,
        name: str,
        url: str,
        licence: str,
        version: str,
        downloaded_at: str,
        query: dict[str, Any],
    ) -> None:
        """Record a download with its licence, version, date and query settings."""
        self._state["sources"].append(
            {
                "name": name,
                "url": url,
                "licence": licence,
                "version": version,
                "downloaded_at": downloaded_at,
                "query": query,
            }
        )
        self.save_state()

    def add_input(self, path: Path | str) -> None:
        """Record a file the experiment reads, with its hash and size."""
        file_path = Path(path)
        self._state["inputs"].append(
            {
                "path": str(file_path),
                "sha256": file_sha256(file_path),
                "size_bytes": file_path.stat().st_size,
            }
        )
        self.save_state()

    def add_output(self, path: Path | str) -> None:
        """Record a file the experiment wrote."""
        self._state["outputs"].append(str(path))
        self.save_state()

    def set_error(self, message: str) -> None:
        """Save the error message of a failed run."""
        self._state["error"] = message
        self.save_state()

    def save_state(self) -> None:
        """Write the collected data to the temporary run folder."""
        temp_path = self._state_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
        os.replace(temp_path, self._state_path)
