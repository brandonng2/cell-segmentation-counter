"""Cell counter algorithm module."""

import numpy as np
import cv2
import skimage as ski
from skimage import filters
from skimage.feature import peak_local_max

clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

def detect_background_type(img, fov_mask, l_channel, b_channel):
    r_masked = img[:, :, 2][fov_mask == 255]
    b_masked = img[:, :, 0][fov_mask == 255]
    is_warm = np.median(r_masked) > np.median(b_masked)
    return (l_channel, 0) if is_warm else (b_channel, 2)

def count_cells(img):
    h, w = img.shape[:2]
    cx, cy, radius = w // 2, h // 2, h // 2

    fov_mask = np.zeros((h, w), dtype=np.uint8)
    cv2.circle(fov_mask, (cx, cy), radius, 255, -1)
    l_channel, a_channel, b_channel = cv2.split(cv2.cvtColor(img, cv2.COLOR_BGR2LAB))

    channel, region_idx = detect_background_type(img, fov_mask, l_channel, b_channel)
    channel_clahe = clahe.apply(channel)
    channel_masked = channel_clahe[fov_mask == 255]
    thresholds = filters.threshold_multiotsu(channel_masked, classes=3)
    regions = np.digitize(channel_clahe, bins=thresholds)
    binary = ((regions == region_idx) & (fov_mask == 255)).astype(np.uint8) * 255

    # dynamic noise threshold based on image resolution
    noise_size = int(np.pi * (h * 0.005) ** 2)

    # remove noise
    cleaned = ski.morphology.remove_small_objects(binary.astype(bool), max_size=noise_size)

    # seal broken ring outlines before contouring
    close_radius = max(2, int(h * 0.005 * 0.5))
    sealed = ski.morphology.closing(cleaned, ski.morphology.disk(close_radius))

    # solidify: fill enclosed regions (handles both solid blobs and closed/sealed rings)
    sealed_uint8 = sealed.astype(np.uint8) * 255
    contours, _ = cv2.findContours(sealed_uint8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(sealed_uint8)
    cv2.drawContours(filled, contours, -1, 255, thickness=cv2.FILLED)

    # crop to FOV aperture
    prepped = (filled.astype(bool) & fov_mask.astype(bool)).astype(np.uint8) * 255

    # distance transform
    dist = cv2.distanceTransform(prepped, cv2.DIST_L2, 3)
    cv2.normalize(dist, dist, 0, 1.0, cv2.NORM_MINMAX)

    # dynamic min_distance from cell size
    labeled_est, _ = ski.measure.label(prepped, return_num=True)
    props_est = ski.measure.regionprops(labeled_est)
    typical_area = np.percentile([p.area for p in props_est], 25)
    typical_radius = int(np.sqrt(typical_area / np.pi))
    min_distance = max(10, int(typical_radius * 0.6))

    coords = peak_local_max(dist, min_distance=min_distance, threshold_abs=0.1, exclude_border=False)
    peaks = np.zeros_like(dist, dtype=np.uint8)
    peaks[tuple(coords.T)] = 1
    peaks = cv2.dilate(peaks, np.ones((5, 5), dtype=np.uint8))

    # build markers
    peaks_8u = peaks.astype(np.uint8)
    contours_ws, _ = cv2.findContours(peaks_8u, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    markers = np.zeros(dist.shape, dtype=np.int32)
    for i, cnt in enumerate(contours_ws):
        cv2.drawContours(markers, contours_ws, i, i + 1, -1)
    cv2.circle(markers, (5, 5), 3, len(contours_ws) + 1, -1)

    # watershed
    img_bgr = img.copy()
    cv2.watershed(img_bgr, markers)
    markers[prepped == 0] = 0

    # remove splotch-sized regions
    unique_labels = set(np.unique(markers)) - {-1, 0, len(contours_ws) + 1}

    # get area of each label
    label_areas = {}
    for label_id in unique_labels:
        label_areas[label_id] = np.sum(markers == label_id)

    # typical cell area = median of all watershed regions
    median_label_area = np.median(list(label_areas.values()))

    # reject regions larger than 5x median (splotches)
    valid_labels = {lbl for lbl, area in label_areas.items() if area < median_label_area * 5}

    # zero out rejected labels
    valid_mask = np.isin(markers, list(valid_labels))
    markers = np.where(valid_mask, markers, 0)

    num_cells = len(valid_labels)

    # colorize watershed regions
    colors = np.random.randint(50, 255, size=(len(contours_ws) + 2, 3), dtype=np.uint8)
    result = colors[np.clip(markers, 0, len(contours_ws) + 1)]
    result[markers <= 0] = 0
    result[fov_mask == 0] = 0

    # per-cell measurements via regionprops
    label_map = np.zeros_like(markers, dtype=np.int32)
    for new_id, old_id in enumerate(sorted(valid_labels), start=1):
        label_map[markers == old_id] = new_id
    props = ski.measure.regionprops(label_map)
    per_cell = [
        {
            "id": i + 1,
            "area": int(p.area),
            "perimeter": round(p.perimeter, 1),
            "equivalent_diameter": round(p.equivalent_diameter, 1),
            "eccentricity": round(p.eccentricity, 3),
            "centroid_x": round(p.centroid[1], 1),
            "centroid_y": round(p.centroid[0], 1),
        }
        for i, p in enumerate(props)
    ]

    # distance transform colorized for visualization
    dist_vis = (dist * 255).astype(np.uint8)
    dist_color = cv2.applyColorMap(dist_vis, cv2.COLORMAP_VIRIDIS)
    dist_color[fov_mask == 0] = 0

    return {
        "num_cells": num_cells,
        "min_distance": min_distance,
        "labels_img": result,
        "dist_img": dist_color,
        "binary_img": prepped,
        "per_cell": per_cell,
    }