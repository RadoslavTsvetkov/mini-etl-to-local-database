"""Local-only web server for `manage.py serve`: the one way the HTML
dashboard's Delete / Clear-all-surveys buttons can actually change the
database. A dashboard opened as a plain file (double-clicked, or opened by
`run.bat`/`manage.py dashboard`) has no server behind it, so those buttons
are disabled there -- static HTML has nowhere to send a DELETE. This module
serves the same dashboard over http://127.0.0.1 instead, with two small
JSON endpoints that do the actual database work, reusing load.py/backup.py
so the logic matches the CLI (`delete-survey` / `clear-surveys`) exactly.

Security, since this does bind a socket (even if only to localhost):
- Bound to 127.0.0.1 only -- never reachable from the network.
- Every mutating request must carry the per-server-start random token
  embedded in the page (`X-Dashboard-Token` header). A malicious site open
  in another tab cannot read that token (same-origin policy blocks it from
  reading this page's contents), so it can't forge a valid request even
  though the browser would let it *attempt* one (classic CSRF shape).
- No directory listing; static file serving is restricted to exact
  filenames inside reports/, rejecting any path traversal attempt.

Zero third-party dependencies: stdlib http.server only.
"""

import json
import os
import secrets
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import backup
import generate_dashboard
import load
from colors import BOLD, CYAN, RED, RESET, YELLOW
from db.setup_db import get_connection
from logger import get_logger

logger = get_logger()

TOKEN = ""  # set by run(); module-level so the handler class can read it


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _handle_delete_survey(body: dict) -> dict:
    survey_id = str(body.get("survey_id") or "").strip()
    if not survey_id:
        raise ApiError(400, "Missing survey_id")

    conn = get_connection()
    try:
        record = load.fetch_survey(conn, survey_id)
        if record is None:
            raise ApiError(404, f"Survey {survey_id} not found (already deleted?)")
        backup_path = backup.backup_survey(record)
        load.delete_survey(conn, survey_id)
    finally:
        conn.close()

    logger.warning("Deleted survey %s via manage.py serve web UI (backup: %s)", survey_id, backup_path)
    new_path = generate_dashboard.generate(server_token=TOKEN)
    return {"ok": True, "redirect": "/" + os.path.basename(new_path)}


def _handle_clear_surveys(body: dict) -> dict:
    if body.get("confirm") != "DELETE ALL":
        raise ApiError(400, 'Confirmation phrase must be exactly "DELETE ALL"')
    expected_count = body.get("expected_count")

    conn = get_connection()
    try:
        actual = load.count_surveys(conn)
        if actual == 0:
            raise ApiError(409, "No surveys to clear.")
        if not isinstance(expected_count, int) or expected_count != actual:
            raise ApiError(409, f"Row count changed (now {actual}) — reload the dashboard and try again.")
        records = load.fetch_all_surveys(conn)
        backup_path = backup.backup_all_surveys(records)
        deleted = load.clear_all_surveys(conn)
    finally:
        conn.close()

    logger.warning("Cleared ALL %d surveys via manage.py serve web UI (backup: %s)", deleted, backup_path)
    new_path = generate_dashboard.generate(server_token=TOKEN)
    return {"ok": True, "redirect": "/" + os.path.basename(new_path)}


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "ShopmetricsDashboard/1.0"

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self, max_bytes: int = 65536) -> dict:
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > max_bytes:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def _serve_file(self, name: str) -> None:
        # Only an exact filename directly inside reports/ -- no traversal,
        # no subdirectories, no listing.
        basename = os.path.basename(name)
        reports_dir = os.path.realpath(generate_dashboard.REPORTS_DIR)
        full = os.path.realpath(os.path.join(reports_dir, basename))
        if basename != name or not basename or not full.startswith(reports_dir + os.sep):
            self.send_error(403, "Forbidden")
            return
        if not os.path.isfile(full):
            self.send_error(404, "Not found")
            return
        try:
            with open(full, "rb") as f:
                content = f.read()
        except OSError as e:
            self.send_error(500, str(e))
            return
        content_type = "text/html; charset=utf-8" if basename.lower().endswith(".html") else "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:  # noqa: N802 (stdlib method name)
        path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
        if path == "/":
            latest = generate_dashboard.latest_report_filename()
            if not latest:
                self.send_error(404, "No dashboard generated yet")
                return
            self.send_response(302)
            self.send_header("Location", "/" + latest)
            self.end_headers()
            return
        self._serve_file(path.lstrip("/"))

    def do_POST(self) -> None:  # noqa: N802 (stdlib method name)
        path = urllib.parse.urlsplit(self.path).path
        if path not in ("/api/delete-survey", "/api/clear-surveys"):
            self._send_json(404, {"ok": False, "error": "Unknown endpoint"})
            return
        if self.headers.get("X-Dashboard-Token") != TOKEN:
            self._send_json(403, {"ok": False, "error": "Missing or invalid dashboard token — reload the page and try again."})
            return

        body = self._read_json_body()
        try:
            handler = _handle_delete_survey if path == "/api/delete-survey" else _handle_clear_surveys
            self._send_json(200, handler(body))
        except ApiError as e:
            self._send_json(e.status, {"ok": False, "error": str(e)})
        except Exception as e:
            self._send_json(500, {"ok": False, "error": f"Internal error: {e}"})

    def log_message(self, format: str, *args) -> None:
        print(f"  {self.address_string()} {format % args}")


def _open_url(url: str) -> bool:
    try:
        if os.name == "nt":
            os.startfile(url)  # noqa: S606 -- identical to double-clicking a link
            return True
        import webbrowser

        return webbrowser.open(url)
    except Exception:
        return False


def run(port: int = 8765, no_open: bool = False) -> int:
    global TOKEN
    TOKEN = secrets.token_hex(16)

    try:
        generate_dashboard.generate(server_token=TOKEN)
    except Exception as e:
        print(f"{RED}Could not generate the initial dashboard: {e}{RESET}")
        return 1

    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port), DashboardHandler)
    except OSError as e:
        print(f"{RED}Could not start the server on 127.0.0.1:{port}: {e}{RESET}")
        print(f"{RED}Something else may be using that port — try `manage.py serve --port <other>`.{RESET}")
        return 1

    url = f"http://127.0.0.1:{port}/"
    print(f"\n{BOLD}{CYAN}Serving the dashboard at {url}{RESET}")
    print("Delete / Clear-all-surveys are live for this session (bound to 127.0.0.1 only).")
    print(f"{YELLOW}Press Ctrl+C to stop.{RESET}\n")

    if not no_open:
        _open_url(url)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        httpd.server_close()
    return 0
