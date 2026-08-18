"""Local upload server, so anyone can review their own pair of documents.

Built on http.server from the standard library rather than Flask or FastAPI:
the tool's whole install story is "python, one dependency", and a single-user
local review app does not need an ASGI stack. Files arrive base64-encoded
inside a JSON body, because the cgi module that used to parse multipart forms
was removed in Python 3.13.

Binds to 127.0.0.1 by default. This is a desk tool, not a service: it has no
authentication, and the documents it handles are usually confidential.
"""

from __future__ import annotations

import base64
import json
import re
import shutil
import traceback
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional, Tuple

from .ai.client import AIUnavailable, client_from_env
from .pipeline import review
from .render import ASSETS, to_html, to_json
from .table import TableParseError
from .verify import CitationError

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
RUN_ID = re.compile(r"^[0-9a-f]{12}$")


@dataclass
class Config:
    runs_dir: Path
    host: str = "127.0.0.1"
    port: int = 8000


def _upload_page() -> str:
    css = (ASSETS / "review-app.css").read_text(encoding="utf-8")
    html = (ASSETS / "upload.html").read_text(encoding="utf-8")
    return html.replace("/*__CSS__*/", css)


def _decode(part: dict, label: str) -> Tuple[str, bytes]:
    name = str(part.get("name") or f"{label}.pdf")
    name = Path(name).name  # no directory components from the client
    try:
        blob = base64.b64decode(part.get("data") or "", validate=True)
    except Exception as exc:
        raise ValueError(f"{label}: could not decode the uploaded file ({exc})")
    if not blob:
        raise ValueError(f"{label}: file is empty")
    if len(blob) > MAX_UPLOAD_BYTES:
        raise ValueError(f"{label}: file is larger than {MAX_UPLOAD_BYTES // (1024*1024)} MB")
    if not blob.startswith(b"%PDF"):
        raise ValueError(f"{label}: this is not a PDF (no %PDF header)")
    return name, blob


class Handler(BaseHTTPRequestHandler):
    config: Config = Config(runs_dir=Path("runs"))
    server_version = "protocolqc"

    # ---- plumbing -----------------------------------------------------
    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} {fmt % args}")

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict) -> None:
        self._send(code, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

    def _html(self, code: int, text: str) -> None:
        self._send(code, text.encode("utf-8"), "text/html; charset=utf-8")

    # ---- routes -------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path == "/":
            return self._html(200, _upload_page())
        if path == "/api/ai-status":
            return self._json(200, self._ai_status())

        m = re.fullmatch(r"/r/([0-9a-f]{12})(/findings\.json)?", path)
        if m:
            run_dir = self.config.runs_dir / m.group(1)
            if m.group(2):
                target, ctype = run_dir / "findings.json", "application/json; charset=utf-8"
            else:
                target, ctype = run_dir / "review-sheet.html", "text/html; charset=utf-8"
            if not target.exists():
                return self._html(404, "<h1>404</h1><p>No such review.</p>")
            return self._send(200, target.read_bytes(), ctype)

        self._html(404, "<h1>404</h1>")

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/api/review":
            return self._json(404, {"error": "unknown endpoint"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._json(400, {"error": "bad Content-Length"})
        if length <= 0 or length > MAX_UPLOAD_BYTES * 3:
            return self._json(413, {"error": "request too large"})

        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return self._json(400, {"error": "body must be JSON"})

        try:
            p_name, p_bytes = _decode(body.get("protocol") or {}, "protocol")
            r_name, r_bytes = _decode(body.get("report") or {}, "report")
        except ValueError as exc:
            return self._json(400, {"error": str(exc)})

        want_ai = bool(body.get("ai"))
        want_suggest = bool(body.get("suggest"))
        ai_client = None
        warning = None
        if want_ai or want_suggest:
            try:
                ai_client = client_from_env(body.get("model") or None)
                ai_client.notify = lambda msg: print(f"  ai: {msg}", flush=True)
            except AIUnavailable as exc:
                warning = str(exc)

        run_id = uuid.uuid4().hex[:12]
        run_dir = self.config.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        protocol_path = run_dir / f"protocol-{p_name}"
        report_path = run_dir / f"report-{r_name}"
        protocol_path.write_bytes(p_bytes)
        report_path.write_bytes(r_bytes)

        try:
            result = review(protocol_path, report_path, ai_client=ai_client,
                            want_suggestions=want_suggest)
        except TableParseError as exc:
            shutil.rmtree(run_dir, ignore_errors=True)
            return self._json(422, {
                "error": str(exc),
                "hint": ("The parser stops rather than guess at a layout it does not "
                         "recognise. Turn on AI assistance to let a model locate the "
                         "structure instead — every quote it produces is still checked "
                         "against the source."),
                "ai_would_help": ai_client is None,
            })
        except CitationError as exc:
            shutil.rmtree(run_dir, ignore_errors=True)
            return self._json(500, {"error": f"citation verification failed: {exc}"})
        except Exception as exc:  # unexpected: keep the server up, report honestly
            traceback.print_exc()
            shutil.rmtree(run_dir, ignore_errors=True)
            return self._json(500, {"error": f"{type(exc).__name__}: {exc}"})

        (run_dir / "findings.json").write_text(
            to_json(result.findings, result.outcomes, result.limits, result.manifest_data,
                    result.repairer, result.suggestions), encoding="utf-8")
        (run_dir / "review-sheet.html").write_text(
            to_html(result.findings, result.outcomes, result.limits, result.manifest_data,
                    result.doc_names, result.repairer, result.suggestions), encoding="utf-8")

        return self._json(200, {
            "run_id": run_id,
            "url": f"/r/{run_id}",
            "findings": len(result.findings),
            "high": sum(1 for f in result.findings if f.priority == "high"),
            "suggestions": len(result.suggestions),
            "notes": result.ai_notes,
            "warning": warning,
        })

    def _ai_status(self) -> dict:
        """Whether a key is *configured* -- deliberately not whether it works.
        Confirming that needs a live call, and one on every page load would be
        slow and would spend someone's quota to render a status line. The
        wording downstream says "loaded", not "working", and
        `python -m protocolqc.ai.check` is the thing that actually proves it.

        Resolved per request rather than cached, so a key written into .env
        while the server is running is picked up on the next page load."""
        try:
            client = client_from_env()
            return {"available": True, "provider": "NVIDIA NIM",
                    "model": client.model, "key": client.describe_key()}
        except AIUnavailable as exc:
            return {"available": False, "reason": str(exc)}


def serve(host: str = "127.0.0.1", port: int = 8000, runs_dir: str | Path = "runs") -> None:
    Handler.config = Config(runs_dir=Path(runs_dir), host=host, port=port)
    Handler.config.runs_dir.mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer((host, port), Handler)
    status = Handler._ai_status(Handler)  # type: ignore[arg-type]
    print("=" * 72)
    print(f"  protocolqc upload server   http://{host}:{port}")
    print(f"  runs are written to        {Handler.config.runs_dir.resolve()}")
    print(f"  AI assistance              "
          + (f"key loaded, {status['model']}" if status.get("available")
             else "off (no key — write one into .env and reload the page)"))
    if status.get("key"):
        print(f"                             {status['key']}")
    print("  decision support only — this tool does not determine pass or fail")
    print("=" * 72)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        prog="protocolqc-server",
        description="Local web app for uploading a protocol and its verification report.",
    )
    ap.add_argument("--host", default="127.0.0.1",
                    help="bind address (default 127.0.0.1 — local only)")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--runs", default="runs", help="where completed reviews are stored")
    args = ap.parse_args(argv)
    serve(args.host, args.port, args.runs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
