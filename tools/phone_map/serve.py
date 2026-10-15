"""Serve saved national map responses and collect local device measurements."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4


def main() -> None:
    """Start the local measurement server with an explicit asset allowlist."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8769)
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed/map_checks"))
    parser.add_argument(
        "--forest-layer", type=Path,
        help="Measure this gzip forest layer instead of the three estimate views.",
    )
    parser.add_argument("--results-dir", type=Path, default=Path("data/processed/phone_map_checks"))
    args = parser.parse_args()
    assets: dict[str, tuple[bytes, str, bool]] = {
        "/": (Path(__file__).with_name("index.html").read_bytes(), "text/html; charset=utf-8", False),
    }
    manifest = {}
    if args.forest_layer:
        compressed = args.forest_layer.read_bytes()
        raw = gzip.decompress(data=compressed)
        assets["/forest.geojson"] = (compressed, "application/geo+json", True)
        manifest["forest"] = {
            "raw_bytes": len(raw), "gzip_bytes": len(compressed),
            "sha256": hashlib.sha256(string=compressed).hexdigest(),
        }
    else:
        for name in ("northern_apennines", "alps", "calabria"):
            raw = (args.data_dir / f"sporameteo-map-{name}.geojson").read_bytes()
            compressed = gzip.compress(data=raw, mtime=0)
            assets[f"/{name}.geojson"] = (compressed, "application/geo+json", True)
            manifest[name] = {"raw_bytes": len(raw), "gzip_bytes": len(compressed)}
    assets["/manifest.json"] = (json.dumps(obj=manifest).encode(), "application/json", False)
    args.results_dir.mkdir(parents=True, exist_ok=True)

    class Handler(BaseHTTPRequestHandler):
        """Serve only measurement assets and save bounded JSON reports."""

        def send_data(self, *, body: bytes, content_type: str, compressed: bool = False) -> None:
            self.send_response(code=200)
            self.send_header(keyword="Content-Type", value=content_type)
            self.send_header(keyword="Content-Length", value=str(len(body)))
            self.send_header(keyword="Cache-Control", value="no-store")
            if compressed:
                self.send_header(keyword="Content-Encoding", value="gzip")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            asset = assets.get(self.path)
            if asset is None:
                self.send_error(code=404)
                return
            body, content_type, compressed = asset
            self.send_data(body=body, content_type=content_type, compressed=compressed)

        def do_POST(self) -> None:
            if self.path != "/results":
                self.send_error(code=404)
                return
            host = self.headers.get("Host")
            if self.headers.get("Origin") != f"http://{host}":
                self.send_error(code=403)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 100_000:
                    raise ValueError("Invalid report size.")
                report = json.loads(s=self.rfile.read(length))
                if not isinstance(report, dict) or len(report.get("results", [])) != 3 * len(manifest):
                    raise ValueError("Expected three measurements per map view.")
            except (ValueError, TypeError):
                self.send_error(code=400)
                return
            report["received_at"] = datetime.now(tz=timezone.utc).isoformat()
            name = f"{uuid4().hex}.json"
            (args.results_dir / name).write_text(data=json.dumps(obj=report, indent=2) + "\n")
            print(f"Saved device report: {args.results_dir / name}", flush=True)
            self.send_data(body=json.dumps(obj={"saved": name}).encode(), content_type="application/json")

    server = ThreadingHTTPServer(server_address=(args.host, args.port), RequestHandlerClass=Handler)
    print(f"Listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
