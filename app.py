import base64
import os

import cv2
import numpy as np
from flask import Flask, jsonify, render_template, request, send_from_directory

from cell_counter import count_cells

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
SAMPLE_EXTS = {".jpg", ".jpeg", ".png"}


def _to_data_uri(img_bgr, fmt=".jpg"):
    ok, buf = cv2.imencode(fmt, img_bgr)
    if not ok:
        raise RuntimeError("Image encoding failed")
    b64 = base64.b64encode(buf.tobytes()).decode()
    mime = "image/jpeg" if fmt == ".jpg" else "image/png"
    return f"data:{mime};base64,{b64}"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/samples")
def samples():
    files = sorted(
        f for f in os.listdir(DATA_DIR)
        if os.path.splitext(f)[1].lower() in SAMPLE_EXTS
    )
    return jsonify(files)


@app.route("/data/<filename>")
def sample_file(filename):
    return send_from_directory(DATA_DIR, filename)


@app.route("/segment", methods=["POST"])
def segment():
    if "image" not in request.files:
        return jsonify({"error": "No file was uploaded."}), 400

    file = request.files["image"]
    if file.filename == "":
        return jsonify({"error": "No file was selected."}), 400

    if file.filename.rsplit(".", 1)[-1].lower() not in {"png", "jpg", "jpeg"}:
        return jsonify({"error": "Unsupported file type."}), 400

    raw = file.read()
    arr = np.frombuffer(raw, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return jsonify({"error": "Could not decode image."}), 400

    MAX_DIM = 1024
    h, w = img.shape[:2]
    if max(h, w) > MAX_DIM:
        scale = MAX_DIM / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    try:
        out = count_cells(img)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        app.logger.exception("Segmentation failed")
        return jsonify({"error": f"Processing failed: {exc}"}), 500

    labels_bgr = out["labels_img"]
    cell_mask = (labels_bgr.sum(axis=2) > 0).astype(np.uint8)[:, :, np.newaxis]
    overlay = np.where(cell_mask, cv2.addWeighted(img, 0.4, labels_bgr, 0.6, 0), img)

    per_cell = out["per_cell"]
    areas = [c["area"] for c in per_cell]
    radii = [c["equivalent_diameter"] / 2 for c in per_cell]
    metrics = {
        "cell_count": out["num_cells"],
        "mean_area": round(float(np.mean(areas)), 1) if areas else 0,
        "avg_radius": round(float(np.mean(radii)), 1) if radii else 0,
        "min_distance": out["min_distance"],
        "per_cell": per_cell,
    }

    binary_3ch = cv2.cvtColor(out["binary_img"], cv2.COLOR_GRAY2BGR)

    return jsonify({
        "original": _to_data_uri(img),
        "overlay": _to_data_uri(overlay),
        "labels": _to_data_uri(overlay),
        "distance": _to_data_uri(out["dist_img"]),
        "binary": _to_data_uri(binary_3ch),
        "metrics": metrics,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
