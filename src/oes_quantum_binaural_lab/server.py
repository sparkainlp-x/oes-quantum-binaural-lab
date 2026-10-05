"""Local-only dashboard server and experiment API."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path

from .app import LabConfig, run_lab
from .audio import AudioSettings


class LabHandler(BaseHTTPRequestHandler):
    server_version = "OESQuantumBinauralLab/0.1"

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/", "/index.html"}:
            page = Path(__file__).parent / "web" / "index.html"
            self._send(200, page.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/health":
            self._send(200, b'{"ok":true,"scope":"local synthetic simulation"}', "application/json")
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/run":
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 32_000:
                raise ValueError("request body must be between 1 and 32,000 bytes")
            payload = json.loads(self.rfile.read(length))
            audio_payload = payload.get("audio", {})
            allowed_audio = set(AudioSettings.__dataclass_fields__)
            if set(audio_payload) - allowed_audio:
                raise ValueError("unknown audio setting")
            config = LabConfig(
                pair_count=int(payload.get("pair_count", 512)),
                calibration_shots_per_state=int(payload.get("calibration_shots_per_state", 64)),
                sweep_shots_per_pair=tuple(int(x) for x in payload.get("sweep_shots_per_pair", [4, 8, 16])),
                seed=int(payload.get("seed", 1731)),
                audio=AudioSettings(**audio_payload),
            )
            result = run_lab(config)
            self._send(200, json.dumps(result, separators=(",", ":")).encode(), "application/json; charset=utf-8")
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            self._send(400, json.dumps({"error": str(exc)}).encode(), "application/json; charset=utf-8")
        except Exception as exc:  # return a useful local error instead of dropping the request
            self._send(500, json.dumps({"error": f"simulation failed: {exc}"}).encode(), "application/json; charset=utf-8")

    def log_message(self, fmt: str, *args) -> None:
        print("[lab-server] " + (fmt % args))


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("for safety this prototype server binds to loopback only")
    server = ThreadingHTTPServer((host, port), LabHandler)
    print(f"Open http://{host}:{port} — local synthetic prototype; press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping local prototype server.")
    finally:
        server.server_close()
