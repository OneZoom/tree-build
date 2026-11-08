"""
Local web app for hand-labelling ideal square crops of the image sets in evaluate.py,
and for browsing the crops from runs/.

Usage: python data/crop_experiment/labeller/server.py [--port 8765]
"""

import argparse
import json
import re
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPERIMENT_DIR = HERE.parent
sys.path.insert(0, str(EXPERIMENT_DIR))
import evaluate  # noqa: E402

INDEX_HTML = HERE / "index.html"
KEY_RE = re.compile(r"^[a-z]+/\d+$")

IMAGES = [
    {
        "key": im["key"],
        "set": im["set"],
        "id": im["src_id"],
        "bucket": im["bucket"],
        "name": im.get("name", ""),
        "width": int(im["width"]),
        "height": int(im["height"]),
    }
    for im in evaluate.images()
]
IMAGES_BY_KEY = {im["key"]: im for im in IMAGES}


def as_dict(box):
    return None if box is None else dict(zip(("x", "y", "width", "height"), box))


def list_runs():
    runs = []
    for path in sorted(evaluate.RUNS_DIR.glob("*/run.json")):
        info = json.loads(path.read_text())
        results_path = path.parent / "results.json"
        if results_path.exists():
            results = json.loads(results_path.read_text())
            info["mean_iou"] = results["mean_iou"]
        runs.append(info)
    return runs


def run_data(name):
    """The run's crop for each image, plus any per-image extras (e.g. a judge's boxes) from details.json."""
    run_dir = evaluate.RUNS_DIR / name
    predictions = evaluate.read_predictions(run_dir / "predictions.tsv")
    details_path = run_dir / "details.json"
    details = json.loads(details_path.read_text()) if details_path.exists() else {}
    return {"predictions": {k: as_dict(v) for k, v in predictions.items()}, "details": details}


def sniff_content_type(head):
    if head.startswith(b"\x89PNG"):
        return "image/png"
    if head.startswith(b"GIF8"):
        return "image/gif"
    return "image/jpeg"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_body(self, status, body, content_type, cache=False):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=86400, immutable" if cache else "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, obj, status=HTTPStatus.OK):
        self.send_body(status, json.dumps(obj).encode(), "application/json")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send_body(HTTPStatus.OK, INDEX_HTML.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/images":
            self.send_json([{**im, "label": as_dict(evaluate.read_label(im["key"]))} for im in IMAGES])
        elif self.path == "/api/runs":
            self.send_json(list_runs())
        elif self.path.startswith("/api/runs/"):
            name = self.path[len("/api/runs/") :]
            if not evaluate.RUN_NAME_RE.match(name) or not (evaluate.RUNS_DIR / name / "predictions.tsv").is_file():
                return self.send_error(HTTPStatus.NOT_FOUND)
            self.send_json(run_data(name))
        elif self.path.startswith("/img/"):
            key = self._key("/img/")
            if key is None:
                return
            data = evaluate.original_path(key).read_bytes()
            self.send_body(HTTPStatus.OK, data, sniff_content_type(data[:8]), cache=True)
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_PUT(self):
        key = self._key("/api/label/")
        if key is None:
            return
        im = IMAGES_BY_KEY[key]
        try:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            x, y, side = int(body["x"]), int(body["y"]), int(body["width"])
        except (KeyError, TypeError, ValueError):
            return self.send_error(HTTPStatus.BAD_REQUEST)
        if side <= 0 or x < 0 or y < 0 or x + side > im["width"] or y + side > im["height"]:
            return self.send_error(HTTPStatus.BAD_REQUEST, "crop box out of bounds")
        path = evaluate.label_path(key)
        path.parent.mkdir(exist_ok=True)
        path.write_text(f"{x},{y},{side},{side}")
        self.send_json(as_dict(evaluate.read_label(key)))

    def do_DELETE(self):
        key = self._key("/api/label/")
        if key is None:
            return
        evaluate.label_path(key).unlink(missing_ok=True)
        self.send_json(None)

    def _key(self, prefix):
        key = self.path[len(prefix) :] if self.path.startswith(prefix) else ""
        if not KEY_RE.match(key) or key not in IMAGES_BY_KEY:
            self.send_error(HTTPStatus.NOT_FOUND)
            return None
        return key


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    counts = ", ".join(f"{s}: {sum(im['set'] == s for im in IMAGES)}" for s in evaluate.SETS)
    print(f"Crop labeller on http://127.0.0.1:{args.port} ({counts})")
    server.serve_forever()


if __name__ == "__main__":
    main()
