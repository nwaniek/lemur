"""lmranim — a viewer for designing ``lemur.anim`` animations.

    lmranim flow.py                  # serve flow.py's animation, rebuild on save
    lmranim flow.py --class Frame    # a module with several Anim classes
    lmranim flow.py --editor "vim --servername lemur --remote-silent +{line} {file}"

It runs the animation module the way a deck would, shows it on a slide-sized
stage in the browser, and adds what designing needs:

* a timeline: play / pause, scrub, step a frame or a beat, loop a beat, slow
  motion; the playhead stays where it was when the module is rebuilt;
* rebuild on save of the module, of anything it imports from your folders, and
  of the shaders, images and style next to it;
* the Python traceback and whatever the module printed, in the page;
* an inspector: hover a shape to see where your code made it, click to open
  that line in your editor (``--editor``, or ``$LEMUR_EDITOR``);
* a coordinate grid with the pointer's position in animation units, and a
  switch between the live (GPU) and the printed (vector) rendering.

Nothing here is needed to build decks; the viewer uses the same emitter as
``lmr2svg``, so what you see is what the deck will show.
"""

from __future__ import annotations

import argparse
import contextlib
import html
import io
import json
import os
import queue
import shlex
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

__all__ = ["AnimViewer", "main"]

POLL = 0.25
WATCH_EXT = {".py", ".lmr", ".glsl", ".wgsl", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".tex", ".css"}
ASSETS = Path(__file__).resolve().parent / "assets" / "svg"


class AnimViewer:
    """Builds the viewer page for one animation module and pushes rebuilds."""

    def __init__(self, module: Path, cls_name=None, theme=None, style=None, aspect=None, editor=None):
        self.module = Path(module).resolve()
        self.cls_name = cls_name
        self.theme = theme
        self.style = style
        self.aspect = aspect
        self.editor = editor or os.environ.get("LEMUR_EDITOR")
        self.lock = threading.Lock()
        self.page: "str | None" = None
        self.clients: list = []
        self.imported: set = set()
        self.tmp = Path(tempfile.mkdtemp(prefix="lmranim-"))

    # -- building -------------------------------------------------------------

    def build(self) -> bool:
        from .anim import mobject
        from .emit import svg

        t0 = time.perf_counter()
        before = set(sys.modules)
        out = io.StringIO()
        mobject.TRACK_SOURCE = True
        err = None
        ir = None
        try:
            with contextlib.redirect_stdout(out):
                ir = svg._load_anim(str(self.module), self.cls_name)
        except Exception:
            err = traceback.format_exc()
        finally:
            mobject.TRACK_SOURCE = False
        self.imported = {Path(m.__file__).resolve() for k in set(sys.modules) - before
                         if (m := sys.modules.get(k)) is not None and getattr(m, "__file__", None)}
        log = out.getvalue()
        if log:
            sys.stdout.write(log)
        if err is not None:
            print(f"  {self.module.name}: the animation failed\n{err}")
            self.set_page(self.error_page(err, log))
            return False
        # the stage: a one-slide deck with the animation full-bleed
        deck = self.tmp / "view.lmr"
        head = []
        if self.theme:
            head.append(f"!theme {self.theme}")
        if self.aspect:
            head.append(f"!aspect {self.aspect}")
        deck.write_text("\n".join(head + ["!slide[.plain]", "", "!anim", f"\t!src {self.module}",
                                          "\t!viewport full", ""]), encoding="utf-8")
        style = self.style or (str(self.module.parent / "style.py")
                               if (self.module.parent / "style.py").exists() and not self.theme else None)
        try:
            page, _stats = svg.build_html(str(deck), live_reload=True, style=style,
                                          preload={("anim", str(self.module)): ir})
        except Exception:
            err = traceback.format_exc()
            print(f"  building the stage failed\n{err}")
            self.set_page(self.error_page(err, log))
            return False
        info = {
            "file": str(self.module),
            "name": self.module.name,
            "beats": ir.get("beats", []),
            "duration": ir.get("duration", 0.0),
            "nodes": [{"i": n["i"], "k": n.get("k"), "wk": n.get("wk"), "src": n.get("at")}
                      for n in ir.get("nodes", [])],
            "log": log,
            "warnings": list(svg.LAST_WARNINGS),
            "ms": round((time.perf_counter() - t0) * 1000),
            "editor": bool(self.editor),
            "gpu": any(v.get("gpu") for v in ir.get("views") or []),
        }
        inject = ("<script>window.LMR_VIEW = " + json.dumps(info).replace("</", "<\\/") + ";</script>"
                  "<style>" + (ASSETS / "animview.css").read_text(encoding="utf-8") + "</style>"
                  "<script>" + (ASSETS / "animview.js").read_text(encoding="utf-8") + "</script>")
        page = page.replace("</body>", inject + "</body>", 1) if "</body>" in page else page + inject
        self.set_page(page)
        print(f"  built {self.module.name} in {info['ms'] / 1000:.2f}s  "
              f"({len(info['nodes'])} shapes, {len(info['beats'])} beats, {info['duration']:.1f}s)")
        for w in info["warnings"]:
            print(f"  warning: {w}")
        return True

    def set_page(self, page: str) -> None:
        with self.lock:
            self.page = page
        self.publish("reload")

    def error_page(self, err: str, log: str) -> str:
        def link(line: str) -> str:
            e = html.escape(line)
            if line.strip().startswith('File "') and ", line " in line:
                try:
                    f = line.split('"')[1]
                    n = int(line.split(", line ")[1].split(",")[0])
                    return f'<a href="#" data-file="{html.escape(f)}" data-line="{n}">{e}</a>'
                except (IndexError, ValueError):
                    pass
            return e
        body = "\n".join(link(ln) for ln in err.splitlines())
        out = ("<h2>printed</h2><pre>" + html.escape(log) + "</pre>") if log else ""
        return (
            "<!doctype html><meta charset='utf-8'><title>lmranim — error</title>"
            "<style>body{background:#16110f;color:#f0d6d0;font:13px/1.5 ui-monospace,monospace;padding:24px 32px}"
            "h1{font:600 16px system-ui;color:#fff}h2{font:600 13px system-ui;color:#caa}pre{white-space:pre-wrap}"
            "a{color:#ffb4ae}</style>"
            f"<h1>{html.escape(self.module.name)} failed</h1><pre>{body}</pre>{out}"
            "<p style='font:12px system-ui;color:#a99'>Fix it and save: the viewer reloads by itself."
            + (" Click a line to open it in your editor." if self.editor else "") + "</p>"
            "<script>var es=new EventSource('/__lemur/events');"
            "es.addEventListener('reload',function(){location.reload();});"
            "document.addEventListener('click',function(e){var a=e.target.closest('a[data-file]');if(!a)return;"
            "e.preventDefault();fetch('/__lemur/open?file='+encodeURIComponent(a.dataset.file)+'&line='+a.dataset.line);});"
            "</script>")

    # -- editor ---------------------------------------------------------------------

    def open_in_editor(self, file: str, line: int) -> str:
        """Open ``file:line`` with the configured editor command (files under the
        module's folder or among its imports only)."""
        f = Path(file).resolve()
        roots = [self.module.parent]
        if not (f in self.imported or f == self.module or any(r in f.parents for r in roots)):
            return "refused: not a file of this animation"
        where = f"{f}:{line}"
        print(f"  → {where}")
        if not self.editor:
            return where
        cmd = [part.replace("{file}", str(f)).replace("{line}", str(line)) for part in shlex.split(self.editor)]
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            return f"editor failed: {exc}"
        return where

    # -- watching and pushing -------------------------------------------------------

    def watched(self) -> list:
        files = {self.module}
        try:
            for p in self.module.parent.rglob("*"):
                if p.suffix.lower() in WATCH_EXT and p.is_file() and "__pycache__" not in p.parts:
                    files.add(p)
        except OSError:
            pass
        home = Path(sys.prefix).resolve()
        for p in self.imported:                     # imported helpers outside the folder, not libraries
            if home not in p.parents and "site-packages" not in p.parts and p.suffix == ".py":
                files.add(p)
        return sorted(files)

    def stamps(self) -> dict:
        out = {}
        for p in self.watched():
            try:
                out[p] = p.stat().st_mtime_ns
            except OSError:
                pass
        return out

    def watch(self, stop: threading.Event) -> None:
        seen = self.stamps()
        while not stop.wait(POLL):
            now = self.stamps()
            if now != seen:
                changed = sorted({p.name for p in set(now) ^ set(seen)} |
                                 {p.name for p in now if p in seen and now[p] != seen[p]})
                seen = now
                print(f"\n{', '.join(changed) or 'a file'} changed, rebuilding…")
                self.publish("building")
                self.build()
                seen = self.stamps()                  # new imports may have joined the watch

    def subscribe(self):
        q: queue.Queue = queue.Queue(maxsize=8)
        with self.lock:
            self.clients.append(q)
        return q

    def unsubscribe(self, q) -> None:
        with self.lock:
            if q in self.clients:
                self.clients.remove(q)

    def publish(self, event: str) -> None:
        with self.lock:
            targets = list(self.clients)
        for q in targets:
            try:
                q.put_nowait(event)
            except queue.Full:
                pass


def _handler(viewer: AnimViewer):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def _send(self, body: bytes, ctype: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            url = urlparse(self.path)
            if url.path in ("/", "/index.html"):
                with viewer.lock:
                    page = viewer.page or "<p>building…</p>"
                return self._send(page.encode("utf-8"), "text/html; charset=utf-8")
            if url.path == "/__lemur/events":
                return self._events()
            if url.path == "/favicon.ico":                 # the lemur, for the browser tab
                try:
                    mark = (ASSETS.parent / "logo.svg").read_text(encoding="utf-8")
                except OSError:
                    return self._send(b"", "image/x-icon", 204)
                return self._send(mark.replace("currentColor", "#2e5e6e").encode("utf-8"), "image/svg+xml")
            if url.path == "/__lemur/open":
                q = parse_qs(url.query)
                try:
                    msg = viewer.open_in_editor(q["file"][0], int(q.get("line", ["1"])[0]))
                except (KeyError, ValueError):
                    msg = "bad request"
                return self._send(msg.encode("utf-8"), "text/plain; charset=utf-8")
            self._send(b"not found", "text/plain", 404)

        def _events(self) -> None:
            q = viewer.subscribe()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                self.wfile.write(b"event: hello\ndata: \n\n")
                self.wfile.flush()
                while True:
                    try:
                        ev = q.get(timeout=15)
                        self.wfile.write(f"event: {ev}\ndata: \n\n".encode("utf-8"))
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                viewer.unsubscribe(q)

    return Handler


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="lmranim", description="design a lemur.anim animation: a live viewer "
                                 "with a timeline, rebuild on save, and jump-to-source")
    ap.add_argument("module", help="the animation module (.py) — the one a deck's !anim !src names")
    ap.add_argument("-c", "--class", dest="cls", help="the Anim class to show (default: the last one defined)")
    ap.add_argument("-t", "--theme", help="a shipped theme or themes/<name>/ (default: style.py next to the "
                    "module, if there is one, else clean)")
    ap.add_argument("-s", "--style", help="a style.py for the stage")
    ap.add_argument("--aspect", choices=["16:9", "4:3"], help="the slide format")
    ap.add_argument("-e", "--editor", help="command to open a file at a line, with {file} and {line} "
                    "(default: $LEMUR_EDITOR); e.g. \"vim --servername lemur --remote-silent +{line} {file}\"")
    ap.add_argument("-p", "--port", type=int, default=8100, help="port (default 8100)")
    ap.add_argument("--no-open", action="store_true", help="don't open a browser")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):
        pass
    if not os.path.exists(args.module):
        print(f"lmranim: no such file: {args.module}", file=sys.stderr)
        return 1
    here = str(Path(args.module).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    viewer = AnimViewer(Path(args.module), args.cls, args.theme, args.style, args.aspect, args.editor)
    print(f"lmranim: building {args.module} …")
    viewer.build()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), _handler(viewer))
    server.daemon_threads = True
    stop = threading.Event()
    threading.Thread(target=viewer.watch, args=(stop,), daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"\n  viewer   {url}\n  watching {Path(args.module).resolve().parent}  (save to rebuild)")
    print("  editor   " + (viewer.editor or "none — set --editor or $LEMUR_EDITOR to open files from the "
                            "viewer") + "\n  press Ctrl-C to stop\n")
    if not args.no_open:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        stop.set()
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
