"""Live-reloading preview server for the SVG emitter.

Watches the deck's folder (its `.lmr` files, animation and plot modules,
shaders, images, style) and pushes a rebuild to the browser over Server-Sent
Events. SSE is one-directional and in
the standard library on both ends, so this needs no WebSocket dependency and no
client-side framework.

Nothing here cares which editor you use: it is the *file on disk* that is
watched. Save from anywhere and the browser catches up within a few hundred
milliseconds.
"""

from __future__ import annotations

import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import queue

from .emit.svg import build_html

__all__ = ["serve", "DeckBuilder"]

POLL_INTERVAL = 0.3


class DeckBuilder:
    """Rebuilds the deck on demand and fans changes out to browsers."""

    def __init__(self, source: Path, design=None, style=None):
        self.source = Path(source).resolve()
        self.design = design
        self.style = style
        self.lock = threading.Lock()
        self.html: str | None = None
        self.error: str | None = None
        self.generation = 0
        self.clients: list[queue.Queue] = []

    # -- building ----------------------------------------------------------

    def build(self) -> bool:
        t0 = time.perf_counter()
        # A style.py is re-imported by build_html on every build (and watched), so
        # editing the design live-reloads without any extra work here.
        try:
            html, (placements, distinct) = build_html(str(self.source), live_reload=True,
                                                       design=self.design, style=self.style)
        except Exception:
            self.error = traceback.format_exc()
            print(f"  build failed:\n{self.error}")
            self.publish("error-report", "")
            return False
        with self.lock:
            self.html = html
            self.error = None
            self.generation += 1
        print(f"  built in {time.perf_counter() - t0:.2f}s  ({placements} placements, {distinct} distinct)")
        self.publish("reload", "")
        return True

    # -- SSE fan-out -------------------------------------------------------

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=8)
        with self.lock:
            self.clients.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self.lock:
            if q in self.clients:
                self.clients.remove(q)

    def publish(self, event: str, data: str) -> None:
        with self.lock:
            targets = list(self.clients)
        for q in targets:
            try:
                q.put_nowait((event, data))
            except queue.Full:
                pass

    # -- watching ----------------------------------------------------------

    #: what a deck is made of: its sources, animation and plot modules, shaders,
    #: images, a style and a LaTeX preamble
    WATCH_EXT = {".lmr", ".py", ".glsl", ".wgsl", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp",
                 ".tex", ".css"}

    def watched_files(self) -> list[Path]:
        files = {self.source}
        sp = self.style or (self.source.parent / "style.py")   # editing style.py live-reloads
        if Path(sp).exists():
            files.add(Path(sp))
        try:
            for p in self.source.parent.rglob("*"):
                if (p.suffix.lower() in self.WATCH_EXT and "__pycache__" not in p.parts
                        and not p.name.endswith(".html") and p.is_file()):
                    files.add(p)
        except OSError:
            pass
        return sorted(files)

    def watch(self, stop: threading.Event) -> None:
        stamps = self._stamps()
        while not stop.wait(POLL_INTERVAL):
            current = self._stamps()
            if current != stamps:
                stamps = current
                print("\nchange detected, rebuilding…")
                self.build()

    def _stamps(self) -> dict:
        out = {}
        for p in self.watched_files():
            try:
                out[p] = p.stat().st_mtime_ns
            except OSError:
                pass
        return out


def _make_handler(builder: DeckBuilder):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # keep the console for build output
            pass

        def _send(self, body: bytes, content_type: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                return self._serve_page()
            if path == "/__lemur/events":
                return self._serve_events()
            self._send(b"not found", "text/plain", 404)

        def _serve_page(self) -> None:
            with builder.lock:
                html, error = builder.html, builder.error
            if html is None:
                self._send(_error_page(error or "no deck yet").encode("utf-8"), "text/html; charset=utf-8")
                return
            self._send(html.encode("utf-8"), "text/html; charset=utf-8")

        def _serve_events(self) -> None:
            q = builder.subscribe()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                self._sse("hello", "")
                while True:
                    try:
                        event, data = q.get(timeout=15)
                        self._sse(event, data)
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")  # keep proxies awake
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                builder.unsubscribe(q)

        def _sse(self, event: str, data: str) -> None:
            payload = data.replace("\r\n", "\n").replace("\n", "\\n")
            self.wfile.write(f"event: {event}\ndata: {payload}\n\n".encode("utf-8"))
            self.wfile.flush()

    return Handler


def _error_page(message: str) -> str:
    esc = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        "<!doctype html><meta charset='utf-8'><title>lemur — build error</title>"
        "<style>body{background:#180c0c;color:#ffb4ae;font:13px ui-monospace,monospace;padding:24px;"
        "white-space:pre-wrap}h1{font:600 15px system-ui;color:#fff}</style>"
        f"<h1>Build failed</h1>{esc}"
        "<script>var es=new EventSource('/__lemur/events');"
        "es.addEventListener('reload',function(){location.reload();});</script>"
    )


def serve(source: str, host: str = "127.0.0.1", port: int = 8000, open_browser: bool = True, design=None, style=None) -> None:
    builder = DeckBuilder(Path(source), design=design, style=style)
    print(f"lemur: building {source} …")
    builder.build()

    server = ThreadingHTTPServer((host, port), _make_handler(builder))
    server.daemon_threads = True

    stop = threading.Event()
    watcher = threading.Thread(target=builder.watch, args=(stop,), daemon=True)
    watcher.start()

    url = f"http://{host}:{server.server_address[1]}/"
    print(f"\n  serving {url}")
    print(f"  watching {builder.source.parent}  (save any of its files to rebuild)")
    print("  press Ctrl-C to stop\n")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        stop.set()
        server.shutdown()
        server.server_close()
