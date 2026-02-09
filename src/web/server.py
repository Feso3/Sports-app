"""Lightweight local web server for player card visualization.

Run with: python -m src.web.server
"""

import json
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from src.cards.builder import build_card, get_available_seasons, get_player_list
from src.database.db import get_database

STATIC_DIR = Path(__file__).parent / "static"
PORT = 8050


class CardHandler(SimpleHTTPRequestHandler):
    """HTTP handler with JSON API routes + static file serving."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self._serve_file("index.html", "text/html")
        elif path == "/style.css":
            self._serve_file("style.css", "text/css")
        elif path == "/app.js":
            self._serve_file("app.js", "application/javascript")
        elif path == "/api/players":
            self._handle_players()
        elif path == "/api/seasons":
            self._handle_seasons()
        elif path.startswith("/api/card/"):
            self._handle_card(path, parsed.query)
        else:
            self.send_error(404)

    def _serve_file(self, filename: str, content_type: str):
        filepath = STATIC_DIR / filename
        if not filepath.exists():
            self.send_error(404)
            return
        content = filepath.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, data):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, code: int, message: str):
        body = json.dumps({"error": message}).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_players(self):
        try:
            players = get_player_list()
            self._send_json(players)
        except Exception as e:
            self._send_error_json(500, str(e))

    def _handle_seasons(self):
        try:
            seasons = get_available_seasons()
            self._send_json(seasons)
        except Exception as e:
            self._send_error_json(500, str(e))

    def _handle_card(self, path: str, query: str):
        try:
            parts = path.rstrip("/").split("/")
            player_id = int(parts[-1])
        except (IndexError, ValueError):
            self._send_error_json(400, "Invalid player ID")
            return

        # Parse optional season from query string
        params = urllib.parse.parse_qs(query)
        season = None
        if "season" in params:
            try:
                season = int(params["season"][0])
            except ValueError:
                pass

        try:
            card = build_card(player_id, season=season)
            self._send_json(card.model_dump())
        except ValueError as e:
            self._send_error_json(404, str(e))
        except Exception as e:
            self._send_error_json(500, str(e))

    def log_message(self, format, *args):
        """Quieter logging -- only log errors and API calls."""
        msg = format % args
        if "/api/" in msg or "404" in msg or "500" in msg:
            super().log_message(format, *args)


def run(port: int = PORT):
    """Start the card server."""
    # Initialize database on startup
    db = get_database()
    stats = db.get_database_stats()
    print(f"Database: {stats['active_players']} players, "
          f"{stats['total_games']} games, "
          f"{stats['total_shots']} shots")
    print(f"Seasons: {stats['seasons']}")
    print(f"\nPlayer Cards server running at http://localhost:{port}")
    print("Press Ctrl+C to stop.\n")

    server = HTTPServer(("localhost", port), CardHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    run()
