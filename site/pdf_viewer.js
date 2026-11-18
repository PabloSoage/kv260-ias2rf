import * as pdfjsLib from "./vendor/pdfjs-4.10.38/pdf.min.mjs";

pdfjsLib.GlobalWorkerOptions.workerSrc = "./vendor/pdfjs-4.10.38/pdf.worker.min.mjs";

const $ = (s) => document.querySelector(s);
const pagesContainer = $("#pdf-pages");
const tocList = $("#toc-list");
const inpPage = $("#inp-page");
const lblPages = $("#lbl-pages");
const statusEl = $("#pdf-status");
const selPdf = $("#sel-pdf");
const btnRaw = $("#btn-raw");
const pdfMain = $("#pdf-main");

let pdfDoc = null;
let currentPage = 1;
let zoomFactor = 1.0; // relative to fit-width
let fitMode = true;
let pageSlots = [];
let renderObserver = null;
const renderingPages = new Set();
const renderedZoom = new Map();
const tStart = performance.now();

function parseParams() {
  const qs = new URLSearchParams(location.search);
  const file = qs.get("file") || "docs/KV260-IAS2RF_Documentation.pdf";
  const hashP = new URLSearchParams(location.hash.replace(/^#/, ""));
  const pageRaw = hashP.get("page") || qs.get("page") || "1";
  const page = Math.max(1, parseInt(pageRaw, 10) || 1);
  return { file, page };
}

function updateHash(pg) {
  const clean = `#page=${pg}`;
  if (location.hash !== clean) history.replaceState(null, "", `${location.pathname}?file=${encodeURIComponent(selPdf.value)}${clean}`);
}

async function computeViewportForPage(pgNum) {
  const page = await pdfDoc.getPage(pgNum);
  const unscaled = page.getViewport({ scale: 1.0 });
  const availW = Math.max(260, pagesContainer.clientWidth - 28);
  const baseScale = availW / unscaled.width;
  const scale = fitMode ? Math.min(2.2, baseScale) : Math.min(3.0, Math.max(0.4, baseScale * zoomFactor));
  return { page, viewport: page.getViewport({ scale }), scale };
}

async function renderSlot(pgNum) {
  const slot = pageSlots[pgNum - 1];
  if (!slot) return;
  const targetKey = `${fitMode ? "fit" : zoomFactor.toFixed(2)}@${pagesContainer.clientWidth}`;
  if (renderedZoom.get(pgNum) === targetKey || renderingPages.has(pgNum)) return;
  renderingPages.add(pgNum);

  try {
    const t0 = performance.now();
    const { page, viewport } = await computeViewportForPage(pgNum);
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    slot.style.width = `${Math.round(viewport.width)}px`;
    slot.style.height = `${Math.round(viewport.height)}px`;

    let canvas = slot.querySelector("canvas");
    if (!canvas) {
      canvas = document.createElement("canvas");
      slot.appendChild(canvas);
    }
    canvas.width = Math.round(viewport.width * dpr);
    canvas.height = Math.round(viewport.height * dpr);
    const ctx = canvas.getContext("2d", { alpha: false });
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    await page.render({ canvasContext: ctx, viewport }).promise;
    renderedZoom.set(pgNum, targetKey);
    const ms = (performance.now() - t0).toFixed(0);
    if (!window.__PDF_READY_MS && pgNum === currentPage) {
      window.__PDF_READY_MS = +(performance.now() - tStart).toFixed(0);
      statusEl.textContent = `Page ${pgNum} streamed & rendered in ${window.__PDF_READY_MS} ms (tile ${ms} ms)`;
    }
  } finally {
    renderingPages.delete(pgNum);
  }
}

function goToPage(pgNum, smooth = false) {
  if (!pdfDoc) return;
  const clamped = Math.max(1, Math.min(pdfDoc.numPages, pgNum));
  currentPage = clamped;
  inpPage.value = String(clamped);
  updateHash(clamped);
  const slot = pageSlots[clamped - 1];
  if (slot) {
    slot.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "start" });
    renderSlot(clamped);
    if (clamped + 1 <= pdfDoc.numPages) renderSlot(clamped + 1);
  }
}

async function buildOutline() {
  tocList.innerHTML = "";
  const outline = await pdfDoc.getOutline().catch(() => null);
  if (!outline || !outline.length) {
    tocList.innerHTML = `<div style="font-size:11px;color:var(--text-muted)">No embedded bookmarks</div>`;
    return;
  }
  const addItems = async (items, depth) => {
    for (const it of items) {
      if (depth > 1) continue;
      let pg = null;
      try {
        const d = typeof it.dest === "string" ? await pdfDoc.getDestination(it.dest) : it.dest;
        if (d) pg = (await pdfDoc.getPageIndex(d[0])) + 1;
      } catch {}
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `pdf-toc-btn ${depth > 0 ? "sub" : ""}`;
      btn.innerHTML = `<span>${it.title.replace(/</g, "&lt;")}</span><span class="mono" style="color:var(--cyan)">${pg || ""}</span>`;
      if (pg) {
        btn.addEventListener("click", () => {
          goToPage(pg, false);
          if (window.innerWidth <= 820) pdfMain.classList.add("toc-closed");
        });
      }
      tocList.appendChild(btn);
      if (it.items?.length) await addItems(it.items, depth + 1);
    }
  };
  await addItems(outline, 0);
}

async function loadPdf(fileUrl, initialPage = 1) {
  window.__PDF_READY_MS = 0;
  statusEl.textContent = "Opening via HTTP Range streaming...";
  if (renderObserver) renderObserver.disconnect();
  pagesContainer.innerHTML = "";
  pageSlots = [];
  renderedZoom.clear();

  const task = pdfjsLib.getDocument({
    url: fileUrl,
    rangeChunkSize: 65536,
    disableAutoFetch: true,
    disableStream: false,
  });
  pdfDoc = await task.promise;
  lblPages.textContent = `/ ${pdfDoc.numPages}`;
  inpPage.max = String(pdfDoc.numPages);

  // Measure page 1 aspect ratio for compact vertical placeholders
  const { viewport: vp1 } = await computeViewportForPage(Math.min(initialPage, pdfDoc.numPages));
  const phW = Math.round(vp1.width);
  const phH = Math.round(vp1.height);

  for (let i = 1; i <= pdfDoc.numPages; i++) {
    const slot = document.createElement("div");
    slot.className = "pdf-page-slot";
    slot.dataset.page = String(i);
    slot.style.width = `${phW}px`;
    slot.style.height = `${phH}px`;
    const badge = document.createElement("div");
    badge.className = "pdf-page-badge";
    badge.textContent = `p. ${i}`;
    slot.appendChild(badge);
    pagesContainer.appendChild(slot);
    pageSlots.push(slot);
  }

  renderObserver = new IntersectionObserver(
    (entries) => {
      let topMostVisible = null;
      for (const en of entries) {
        const pg = Number(en.target.dataset.page);
        if (en.isIntersecting) {
          renderSlot(pg);
          if (topMostVisible === null || pg < topMostVisible) topMostVisible = pg;
        }
      }
      if (topMostVisible !== null && document.activeElement !== inpPage) {
        currentPage = topMostVisible;
        inpPage.value = String(topMostVisible);
        updateHash(topMostVisible);
      }
    },
    { root: pagesContainer, rootMargin: "320px 0px" }
  );
  pageSlots.forEach((s) => renderObserver.observe(s));

  await buildOutline();
  goToPage(initialPage, false);
  await renderSlot(Math.max(1, Math.min(pdfDoc.numPages, initialPage)));
}

function wireEvents() {
  if (window.innerWidth <= 820) pdfMain.classList.add("toc-closed");
  $("#btn-toc").addEventListener("click", () => pdfMain.classList.toggle("toc-closed"));
  $("#btn-prev").addEventListener("click", () => goToPage(currentPage - 1, false));
  $("#btn-next").addEventListener("click", () => goToPage(currentPage + 1, false));
  inpPage.addEventListener("change", () => goToPage(Number(inpPage.value) || 1, false));
  selPdf.addEventListener("change", () => {
    btnRaw.href = selPdf.value;
    loadPdf(selPdf.value, 1).catch((e) => {
      statusEl.textContent = `Error: ${e.message}`;
    });
  });
  $("#btn-zin").addEventListener("click", () => {
    fitMode = false;
    zoomFactor = Math.min(2.4, zoomFactor * 1.2);
    renderedZoom.clear();
    renderSlot(currentPage);
  });
  $("#btn-zout").addEventListener("click", () => {
    fitMode = false;
    zoomFactor = Math.max(0.5, zoomFactor / 1.2);
    renderedZoom.clear();
    renderSlot(currentPage);
  });
  $("#btn-zfit").addEventListener("click", () => {
    fitMode = true;
    zoomFactor = 1.0;
    renderedZoom.clear();
    renderSlot(currentPage);
  });
  window.addEventListener("hashchange", () => {
    const { page } = parseParams();
    goToPage(page, false);
  });
}

window.__PDF_API = {
  isReady: () => Boolean(pdfDoc && window.__PDF_READY_MS > 0),
  getState: () => ({
    currentPage,
    numPages: pdfDoc ? pdfDoc.numPages : 0,
    readyMs: window.__PDF_READY_MS || 0,
    renderedPages: renderedZoom.size,
    file: selPdf.value,
  }),
  getStats: () => ({
    currentPage,
    numPages: pdfDoc ? pdfDoc.numPages : 0,
    readyMs: window.__PDF_READY_MS || 0,
    renderedPages: renderedZoom.size,
    file: selPdf.value,
  }),
  goToPage,
};

wireEvents();
const { file, page } = parseParams();
if ([...selPdf.options].some((o) => o.value === file)) selPdf.value = file;
btnRaw.href = file;
loadPdf(file, page).catch((err) => {
  console.error(err);
  statusEl.textContent = `PDF error: ${err.message}`;
});
