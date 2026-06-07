"use strict";

const form = document.getElementById("upload-form");
const fileInput = document.getElementById("file-input");
const dropzone = document.getElementById("dropzone");
const fileNameEl = document.getElementById("file-name");
const analyzeBtn = document.getElementById("analyze-btn");
const spinner = analyzeBtn.querySelector(".spinner");
const btnLabel = analyzeBtn.querySelector(".btn-label");
const errorEl = document.getElementById("error");

const emptyState = document.getElementById("empty-state");
const resultsContent = document.getElementById("results-content");

let cellData = [];

// --- File selection + name display ---
function showFileName(file) {
  if (file) {
    fileNameEl.textContent = file.name;
    fileNameEl.hidden = false;
  }
}

fileInput.addEventListener("change", () => {
  if (fileInput.files.length) showFileName(fileInput.files[0]);
});

// --- Drag and drop ---
["dragenter", "dragover"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.add("dragging");
  }),
);

["dragleave", "drop"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragging");
  }),
);

dropzone.addEventListener("drop", (e) => {
  const files = e.dataTransfer.files;
  if (files.length) {
    fileInput.files = files;
    showFileName(files[0]);
  }
});

dropzone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    fileInput.click();
  }
});

// --- Shared segmentation runner ---
async function runSegmentation(file) {
  errorEl.hidden = true;
  const data = new FormData();
  data.append("image", file);
  setLoading(true);
  try {
    const res = await fetch("/segment", { method: "POST", body: data });
    const payload = await res.json();
    if (!res.ok) throw new Error(payload.error || "Something went wrong.");
    renderResults(payload);
  } catch (err) {
    showError(err.message);
  } finally {
    setLoading(false);
  }
}

// --- Submit ---
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!fileInput.files.length) {
    showError("Please choose an image first.");
    return;
  }
  await runSegmentation(fileInput.files[0]);
  fileInput.value = "";
  fileNameEl.hidden = true;
});

function setLoading(loading) {
  analyzeBtn.disabled = loading;
  spinner.hidden = !loading;
  btnLabel.textContent = loading ? "Processing…" : "Run segmentation";
}

function showError(msg) {
  errorEl.textContent = msg;
  errorEl.hidden = false;
}

// --- Render results ---
function renderResults(data) {
  const m = data.metrics;

  // Metric cards
  const grid = document.getElementById("metrics-grid");
  grid.innerHTML = "";
  const cards = [
    { value: m.cell_count, label: "Cells detected", accent: true },
    { value: m.mean_area, label: "Mean area (px²)" },
    { value: m.avg_radius, label: "Avg radius (px)" },
    { value: m.min_distance, label: "Min distance (px)" },
  ];
  for (const c of cards) {
    const el = document.createElement("div");
    el.className = "metric-card" + (c.accent ? " accent" : "");
    el.innerHTML = `<span class="value">${c.value}</span><span class="label">${c.label}</span>`;
    grid.appendChild(el);
  }

  // Comparison slider (srcs set now; initCompare called after panel is visible)
  document.getElementById("cmp-before").src = data.original;
  const cmpAfter = document.getElementById("cmp-after");
  cmpAfter.src = data.overlay;
  cmpAfter.dataset.overlay = data.overlay;

  // Gallery
  document.getElementById("img-labels").src = data.labels;
  document.getElementById("img-distance").src = data.distance;
  document.getElementById("img-binary").src = data.binary;
  document
    .querySelectorAll(".shot")
    .forEach((s) => s.classList.remove("active"));
  document.querySelector(".shot").classList.add("active");

  // Per-cell table
  cellData = m.per_cell;
  clearHighlight();
  const tbody = document.getElementById("cell-tbody");
  tbody.innerHTML = "";
  for (const cell of m.per_cell) {
    const tr = document.createElement("tr");
    tr.dataset.cellId = cell.id;
    tr.innerHTML = `
      <td>${cell.id}</td>
      <td>${cell.area}</td>
      <td>${cell.perimeter}</td>
      <td>${cell.equivalent_diameter}</td>
      <td>${cell.eccentricity}</td>`;
    tbody.appendChild(tr);
  }

  emptyState.hidden = true;
  resultsContent.hidden = false;
  initCompare();
  resultsContent.scrollIntoView({ behavior: "smooth", block: "start" });
}

// --- Per-cell row highlight ---
document.getElementById("cell-tbody").addEventListener("click", (e) => {
  const tr = e.target.closest("tr");
  if (!tr) return;
  const id = parseInt(tr.dataset.cellId);
  const cell = cellData.find(c => c.id === id);
  if (!cell) return;

  const wasSelected = tr.classList.contains("selected");
  document.querySelectorAll("#cell-tbody tr").forEach(r => r.classList.remove("selected"));
  clearHighlight();
  if (!wasSelected) {
    tr.classList.add("selected");
    drawHighlight(cell.centroid_x, cell.centroid_y);
  }
});

function drawHighlight(cx, cy) {
  const canvas = document.getElementById("cell-highlight");
  const compare = document.getElementById("compare");
  const img = document.getElementById("cmp-after");

  canvas.width = compare.clientWidth;
  canvas.height = compare.clientHeight;

  const x = cx * (compare.clientWidth / img.naturalWidth);
  const y = cy * (compare.clientHeight / img.naturalHeight);

  const ctx = canvas.getContext("2d");
  ctx.beginPath();
  ctx.arc(x, y, 16, 0, Math.PI * 2);
  ctx.strokeStyle = "rgba(255,255,255,0.9)";
  ctx.lineWidth = 3;
  ctx.stroke();

  ctx.beginPath();
  ctx.arc(x, y, 12, 0, Math.PI * 2);
  ctx.strokeStyle = "#16a571";
  ctx.lineWidth = 2;
  ctx.stroke();
}

function clearHighlight() {
  const canvas = document.getElementById("cell-highlight");
  canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
}

// --- Gallery toggles comparison slider ---
document.querySelector(".gallery").addEventListener("click", (e) => {
  const shot = e.target.closest(".shot");
  if (!shot) return;
  document
    .querySelectorAll(".shot")
    .forEach((s) => s.classList.remove("active"));
  shot.classList.add("active");
  document.getElementById("cmp-after").src = shot.querySelector("img").src;
  document.querySelector(".cmp-tag-right").textContent = shot.dataset.label;
});

// --- Comparison slider behavior ---
let compareController = null;

function initCompare() {
  if (compareController) compareController.abort();
  compareController = new AbortController();
  const { signal } = compareController;

  const compare = document.getElementById("compare");
  const clip = document.getElementById("cmp-clip");
  const handle = document.getElementById("cmp-handle");
  const beforeImg = document.getElementById("cmp-before");

  function setWidth() {
    beforeImg.style.setProperty("--cmp-w", `${compare.clientWidth}px`);
  }

  function setPosition(clientX) {
    const rect = compare.getBoundingClientRect();
    const pct = Math.max(
      0,
      Math.min(100, ((clientX - rect.left) / rect.width) * 100),
    );
    clip.style.width = `${pct}%`;
    handle.style.left = `${pct}%`;
  }

  beforeImg.style.width = "var(--cmp-w, 100%)";

  handle.addEventListener(
    "pointerdown",
    (e) => {
      handle.setPointerCapture(e.pointerId);
      setPosition(e.clientX);
    },
    { signal },
  );

  handle.addEventListener(
    "pointermove",
    (e) => {
      if (handle.hasPointerCapture(e.pointerId)) setPosition(e.clientX);
    },
    { signal },
  );

  window.addEventListener("resize", setWidth, { signal });

  requestAnimationFrame(() => {
    setWidth();
    setPosition(compare.getBoundingClientRect().left + compare.clientWidth / 2);
  });
}

// --- Sample carousel ---
async function initCarousel() {
  const res = await fetch("/samples");
  const files = await res.json();
  if (!files.length) return;

  const track = document.getElementById("sample-track");

  files.forEach(name => {
    const btn = document.createElement("button");
    btn.className = "sample-card";
    btn.dataset.filename = name;
    btn.innerHTML = `<img src="/data/${name}" alt="${name}"><span>${name}</span>`;
    btn.addEventListener("click", async () => {
      document.querySelectorAll(".sample-card").forEach(c => c.classList.remove("active"));
      btn.classList.add("active");
      const blob = await (await fetch(`/data/${name}`)).blob();
      await runSegmentation(new File([blob], name, { type: blob.type }));
    });
    track.appendChild(btn);
  });
}

initCarousel();
