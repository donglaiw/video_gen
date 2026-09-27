#!/usr/bin/env python3
"""Local video browser for video_gen outputs.

Stdlib only. Binds to 127.0.0.1; reach it from the Mac with
    ssh -N -L 8765:localhost:8765 donglai@cajal
then open http://localhost:8765.

Routes:
    /                    single-page UI (viewer/index.html)
    /api/runs            JSON: runs grouped by top-level folder, with videos + metadata
    /api/text?path=...   small text file (prompt.txt, cmd.txt, run.log tail)
    /media/<relpath>     file bytes, with HTTP Range (Safari needs it to play/seek)
    /browser/<relpath>   H.264 copy of a non-browser-playable video, transcoded on demand
"""
import argparse
import json
import mimetypes
import os
import re
import subprocess
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
VIDEO_EXT = {".mp4", ".webm", ".mov", ".mkv", ".avi", ".gif", ".m4v"}
RUN_FILES = ("prompt.txt", "cmd.txt", "run.log", "vram.csv", "skyreels_commit.txt")
BROWSER_CODECS = {"h264", "vp8", "vp9", "av1"}
SKIP_DIRS = {".git", "env", "SkyReels-V2", "models", "__pycache__", ".viewer_cache", "node_modules"}
CACHE = REPO / ".viewer_cache"
TEXT_LIMIT = 64 * 1024


def find_ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


FFMPEG = find_ffmpeg()
_meta_cache = {}
_meta_lock = threading.Lock()
_transcode_locks = {}


def probe(path: Path):
    """Parse `ffmpeg -i` stderr for codec/size/fps/duration. Cached by (path, mtime, size)."""
    st = path.stat()
    key = (str(path), st.st_mtime_ns, st.st_size)
    with _meta_lock:
        if key in _meta_cache:
            return _meta_cache[key]
    meta = {"codec": None, "width": None, "height": None, "fps": None, "duration": None}
    try:
        err = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path)],
                             capture_output=True, text=True, timeout=15).stderr
        m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
        if m:
            h, mi, s = m.groups()
            meta["duration"] = int(h) * 3600 + int(mi) * 60 + float(s)
        m = re.search(r"Video: (\w+).*?, (\d{2,5})x(\d{2,5})", err)
        if m:
            meta["codec"], meta["width"], meta["height"] = m.group(1), int(m.group(2)), int(m.group(3))
        m = re.search(r"([\d.]+) fps", err)
        if m:
            meta["fps"] = float(m.group(1))
    except Exception:
        pass
    with _meta_lock:
        _meta_cache[key] = meta
    return meta


def is_playable(path: Path, meta):
    if path.suffix.lower() == ".gif":
        return True
    if path.suffix.lower() in {".avi", ".mkv"}:
        return False
    return meta["codec"] in BROWSER_CODECS


def safe_path(root: Path, rel: str):
    p = (root / urllib.parse.unquote(rel)).resolve()
    if p != root and root not in p.parents:
        return None
    return p


def scan(roots):
    """Group videos by run = first two path components under each root (e.g. outputs/<run>)."""
    runs = {}
    for root in roots:
        base = REPO / root
        if not base.is_dir():
            continue
        for run_dir in sorted(p for p in base.iterdir() if p.is_dir()):
            if run_dir.name in SKIP_DIRS:
                continue
            rel_run = run_dir.relative_to(REPO).as_posix()
            videos, latest = [], run_dir.stat().st_mtime
            for dirpath, dirnames, filenames in os.walk(run_dir):
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
                for fn in filenames:
                    fp = Path(dirpath) / fn
                    try:
                        st = fp.stat()
                    except OSError:
                        continue
                    latest = max(latest, st.st_mtime)
                    if fp.suffix.lower() not in VIDEO_EXT or st.st_size == 0:
                        continue
                    meta = probe(fp)
                    videos.append({
                        "path": fp.relative_to(REPO).as_posix(),
                        "name": fp.relative_to(run_dir).as_posix(),
                        "size": st.st_size,
                        "mtime": st.st_mtime,
                        "playable": is_playable(fp, meta),
                        **meta,
                    })
            files = [f for f in RUN_FILES if (run_dir / f).is_file()]
            if not videos and not files:
                continue
            log = run_dir / "run.log"
            active = log.is_file() and time.time() - log.stat().st_mtime < 120
            videos.sort(key=lambda v: v["mtime"], reverse=True)
            runs[rel_run] = {"id": rel_run, "root": root, "name": run_dir.name,
                             "mtime": latest, "files": files, "videos": videos,
                             "active": active}
    return sorted(runs.values(), key=lambda r: r["mtime"], reverse=True)


def transcode(src: Path):
    """Return an H.264/yuv420p copy in .viewer_cache, building it once."""
    rel = src.relative_to(REPO)
    dst = CACHE / rel.with_suffix(".h264.mp4")
    lock = _transcode_locks.setdefault(str(dst), threading.Lock())
    with lock:
        if dst.is_file() and dst.stat().st_mtime >= src.stat().st_mtime:
            return dst
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_suffix(".tmp.mp4")
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(src),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                        "-preset", "veryfast", "-movflags", "+faststart", "-an", str(tmp)],
                       check=True, timeout=3600)
        tmp.replace(dst)
        return dst


class Handler(BaseHTTPRequestHandler):
    server_version = "video-viewer"
    roots = ("outputs", "projects")

    def log_message(self, fmt, *args):
        if not self.path.startswith(("/media/", "/api/runs")):
            super().log_message(fmt, *args)

    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        q = urllib.parse.parse_qs(url.query)
        try:
            if url.path in ("/", "/index.html"):
                return self.send_file(HERE / "index.html", cache=False)
            if url.path == "/api/runs":
                return self.send_json({"repo": str(REPO), "runs": scan(self.roots)})
            if url.path == "/api/text":
                return self.send_text(q.get("path", [""])[0], tail="tail" in q)
            if url.path.startswith("/media/"):
                p = safe_path(REPO, url.path[len("/media/"):])
                return self.send_file(p) if p and p.is_file() else self.send_error(404)
            if url.path.startswith("/browser/"):
                p = safe_path(REPO, url.path[len("/browser/"):])
                if not p or not p.is_file():
                    return self.send_error(404)
                return self.send_file(transcode(p))
            self.send_error(404)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except subprocess.CalledProcessError:
            self.send_error(500, "transcode failed")

    def send_text(self, rel, tail=False):
        p = safe_path(REPO, rel)
        if not p or not p.is_file():
            return self.send_error(404)
        size = p.stat().st_size
        with open(p, "rb") as f:
            if tail and size > TEXT_LIMIT:
                f.seek(size - TEXT_LIMIT)
            data = f.read(TEXT_LIMIT)
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_file(self, p: Path, cache=True):
        size = p.stat().st_size
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        start, end = 0, size - 1
        rng = self.headers.get("Range")
        status = HTTPStatus.OK
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng)
            if m:
                a, b = m.groups()
                if a == "":
                    start = max(0, size - int(b))
                else:
                    start = int(a)
                    end = min(int(b), size - 1) if b else size - 1
                if start > end or start >= size:
                    self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                status = HTTPStatus.PARTIAL_CONTENT
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "max-age=60" if cache else "no-store")
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with open(p, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(1 << 20, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1",
                    help="keep localhost; reach it through an SSH tunnel, never expose publicly")
    ap.add_argument("--roots", nargs="+", default=["outputs", "projects"],
                    help="folders under video_gen/ to scan")
    args = ap.parse_args()
    Handler.roots = tuple(args.roots)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"serving {REPO} ({', '.join(args.roots)}) on http://{args.host}:{args.port}", flush=True)
    print(f"from the Mac: ssh -N -L {args.port}:localhost:{args.port} donglai@cajal", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
