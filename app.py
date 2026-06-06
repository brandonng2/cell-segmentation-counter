import io
import cv2
import numpy as np
from flask import Flask, render_template, request, send_file
from cell_counter import count_cells

app = Flask(__name__)

_result_img_bytes = None

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload():
    global _result_img_bytes
    file = request.files["image"]
    img_array = np.frombuffer(file.read(), np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

    num_cells, result_array = count_cells(img)

    _, buffer = cv2.imencode(".png", result_array)
    _result_img_bytes = io.BytesIO(buffer.tobytes())

    return render_template("index.html", result=f"{num_cells} cells detected")

@app.route("/result-image")
def result_image():
    _result_img_bytes.seek(0)
    return send_file(_result_img_bytes, mimetype="image/png")
