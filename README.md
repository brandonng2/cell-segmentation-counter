# CellScope — Cell Image Segmentation & Counter

A web app for microscopy image analysis. Upload a cell image and CellScope segments it, separates touching cells using a watershed algorithm, and returns per-cell morphometric measurements.

**Live demo:** https://cell-segmentation-counter.onrender.com/

---

## Features

- Upload microscopy images (PNG, JPG) or select from built-in samples
- Automatic background detection (warm/cool tone) for adaptive thresholding
- Multi-Otsu thresholding + CLAHE contrast enhancement
- Watershed segmentation to separate touching cells
- Distance transform visualization (Viridis colormap)
- Interactive before/after comparison slider
- Per-cell metrics table: area, perimeter, equivalent diameter, eccentricity
- Summary statistics: cell count, mean area, average radius, minimum distance

## How it works

1. **Preprocessing** — converts to LAB color space, applies CLAHE, detects background type
2. **Thresholding** — multi-Otsu threshold separates foreground cells from background
3. **Morphology** — removes noise, closes broken outlines, fills contours
4. **Watershed** — distance transform peaks seed watershed markers to split touching cells
5. **Filtering** — rejects regions > 5× the median area (splotches/artifacts)
6. **Measurement** — `skimage.measure.regionprops` computes per-cell shape descriptors

## Tech stack

| Layer | Library |
|---|---|
| Web framework | Flask |
| Image processing | OpenCV, scikit-image, NumPy |
| Server | Gunicorn |
| Deployment | Render |

## Local setup

```bash
# Clone and install
git clone https://github.com/brandonng2/cell-segmentation-counter.git
cd cell-segmentation-counter
pip install -r requirements.txt

# Run
python app.py
```

App starts on `http://localhost:3000` by default.

### Conda environment

```bash
conda env create -f environment.yml
conda activate cell-segmentation-counter
python app.py
```

## API

### `POST /segment`

Upload an image file as `multipart/form-data` with field name `image`.

**Response:**
```json
{
  "original": "<data URI>",
  "overlay": "<data URI>",
  "distance": "<data URI>",
  "binary": "<data URI>",
  "metrics": {
    "cell_count": 42,
    "mean_area": 312.5,
    "avg_radius": 9.8,
    "min_distance": 12,
    "per_cell": [...]
  }
}
```

### `GET /samples`

Returns a list of available sample image filenames.

### `GET /data/<filename>`

Serves a sample image by filename.
