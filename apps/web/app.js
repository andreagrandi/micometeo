(function () {
  "use strict";

  const API = window.MICOMETEO_CONFIG.apiBase;
  const DEBOUNCE_MS = 250;
  const OUTLINE_MIN_ZOOM = 13;
  const SCORE_COLOURS = ["#fff3b0", "#ffd166", "#f4a259", "#e0603c", "#9b1d20"];
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  const el = {
    species: document.getElementById("species"),
    assessment: document.getElementById("assessment-date"),
    days: document.getElementById("days-ahead"),
    hint: document.getElementById("hint"),
    noticeText: document.getElementById("notice-text"),
    sheet: document.getElementById("sheet"),
    sheetTitle: document.getElementById("sheet-title"),
    sheetBody: document.getElementById("sheet-body"),
    sheetClose: document.getElementById("sheet-close"),
  };

  const state = {
    info: null,
    map: null,
    timer: null,
    controller: null,
    firstDrawn: false,
    usableReported: false,
    selectedId: null,
  };

  function setHint(text, isError) {
    el.hint.textContent = text || "";
    el.hint.hidden = !text;
    el.hint.classList.toggle("error", Boolean(isError));
  }

  // Dates are handled as UTC calendar days so the time zone never shifts them.
  function addDays(isoDate, n) {
    const d = new Date(isoDate + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() + n);
    return d.toISOString().slice(0, 10);
  }

  function shortDate(isoDate) {
    const d = new Date(isoDate + "T00:00:00Z");
    return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
  }

  function fillDaysAhead() {
    const assessment = el.assessment.value;
    const previous = el.days.value || "0";
    el.days.innerHTML = "";
    for (let n = 0; n <= state.info.max_days_ahead; n++) {
      const opt = document.createElement("option");
      opt.value = String(n);
      const date = assessment ? shortDate(addDays(assessment, n)) : "";
      // Short labels fit three pickers side by side on a 390 px wide phone.
      opt.textContent = n === 0 ? date : `${date} +${n}`;
      el.days.appendChild(opt);
    }
    el.days.value = previous;
  }

  function currentTargetDate() {
    return addDays(el.assessment.value, Number(el.days.value));
  }

  function scoreColourExpression() {
    return [
      "step", ["get", "score"], SCORE_COLOURS[0],
      20, SCORE_COLOURS[1], 40, SCORE_COLOURS[2], 60, SCORE_COLOURS[3], 80, SCORE_COLOURS[4],
    ];
  }

  function emptyCollection() {
    return { type: "FeatureCollection", features: [] };
  }

  function clearSquares() {
    const source = state.map.getSource("squares");
    if (source) source.setData(emptyCollection());
    closeSheet();
  }

  function scheduleFetch() {
    clearTimeout(state.timer);
    state.timer = setTimeout(fetchSquares, DEBOUNCE_MS);
  }

  async function fetchSquares() {
    if (!state.info || !state.map.getSource("squares")) return;
    if (state.controller) state.controller.abort();

    if (state.map.getZoom() < state.info.min_zoom) {
      state.controller = null;
      clearSquares();
      setHint("Zoom in to see squares");
      return;
    }

    const b = state.map.getBounds();
    const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map((v) => v.toFixed(5)).join(",");
    const params = new URLSearchParams({
      species: el.species.value,
      assessment_date: el.assessment.value,
      target_date: currentTargetDate(),
      bbox,
    });
    const url = `${API}/squares?${params}`;
    const controller = new AbortController();
    state.controller = controller;
    const started = performance.now();

    try {
      const response = await fetch(url, { signal: controller.signal });
      const text = await response.text();
      const bytes = new TextEncoder().encode(text).length;
      let body = null;
      try { body = JSON.parse(text); } catch (e) { /* handled below */ }

      if (!response.ok) {
        const message = body && body.error ? body.error : `The API answered with status ${response.status}.`;
        clearSquares();
        setHint(message, true);
        return;
      }
      if (!body || !Array.isArray(body.features)) {
        clearSquares();
        setHint("The API sent an answer this page cannot read.", true);
        return;
      }

      window.micometeoLastRequest = {
        url,
        bytes,
        squares: body.features.length,
        ms: Math.round(performance.now() - started),
      };
      state.map.getSource("squares").setData(body);
      if (state.selectedId !== null) {
        const stillThere = body.features.some((f) => f.id === state.selectedId);
        if (!stillThere) closeSheet();
      }
      setHint(body.features.length === 0 ? "No squares in this view" : "");
      markFirstDraw();
    } catch (err) {
      if (err.name === "AbortError") return;
      clearSquares();
      setHint(`Cannot reach the API at ${API}. Is it running?`, true);
    }
  }

  function markFirstDraw() {
    if (state.firstDrawn) return;
    state.firstDrawn = true;
    // The map goes idle after the new data is drawn.
    state.map.once("idle", () => {
      if (state.usableReported) return;
      state.usableReported = true;
      performance.mark("micometeo-usable");
      window.micometeoUsableMs = performance.now();
    });
  }

  function speciesName(id) {
    const s = state.info.species.find((item) => item.id === id);
    return s ? s.name : id;
  }

  function parseSources(value) {
    if (Array.isArray(value)) return value;
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed : [String(value)];
    } catch (e) {
      return value ? [String(value)] : [];
    }
  }

  function addRow(label, value) {
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = value;
    el.sheetBody.append(dt, dd);
  }

  function openSheet(props) {
    el.sheetTitle.textContent = `Square ${props.cell_id}`;
    el.sheetBody.innerHTML = "";
    addRow("Species", speciesName(props.species));
    addRow("Assessment date", props.assessment_date);
    addRow("Target date", props.target_date);
    addRow("Days ahead", String(props.days_ahead));
    addRow("Score type", props.score_type === "forecast" ? "Forecast" : "Conditions today");
    addRow("Score", `${props.score} out of 100`);
    addRow("Reliability", props.reliability);
    addRow("Sources", parseSources(props.sources).join(", ") || "none listed");
    el.sheet.hidden = false;
  }

  function closeSheet() {
    el.sheet.hidden = true;
    state.selectedId = null;
    if (state.map && state.map.getLayer("squares-selected")) {
      state.map.setFilter("squares-selected", ["==", ["get", "cell_id"], ""]);
    }
  }

  function selectSquare(feature) {
    state.selectedId = feature.id !== undefined ? feature.id : feature.properties.cell_id;
    state.map.setFilter("squares-selected", ["==", ["get", "cell_id"], feature.properties.cell_id]);
    openSheet(feature.properties);
  }

  function addLayers() {
    const map = state.map;
    map.addSource("squares", { type: "geojson", data: emptyCollection(), promoteId: "cell_id" });
    map.addLayer({
      id: "squares-fill",
      type: "fill",
      source: "squares",
      paint: { "fill-color": scoreColourExpression(), "fill-opacity": 0.55 },
    });
    map.addLayer({
      id: "squares-outline",
      type: "line",
      source: "squares",
      minzoom: OUTLINE_MIN_ZOOM,
      paint: { "line-color": "#5a4a3a", "line-width": 0.6, "line-opacity": 0.7 },
    });
    map.addLayer({
      id: "squares-selected",
      type: "line",
      source: "squares",
      filter: ["==", ["get", "cell_id"], ""],
      paint: { "line-color": "#0b3d91", "line-width": 3 },
    });

    map.on("click", (e) => {
      const hits = map.queryRenderedFeatures(e.point, { layers: ["squares-fill"] });
      if (hits.length) selectSquare(hits[0]);
      else closeSheet();
    });
    map.on("mouseenter", "squares-fill", () => { map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseleave", "squares-fill", () => { map.getCanvas().style.cursor = ""; });
    map.on("moveend", scheduleFetch);
    scheduleFetch();
  }

  function fillSelect(select, items) {
    select.innerHTML = "";
    items.forEach(({ value, label }) => {
      const opt = document.createElement("option");
      opt.value = value;
      opt.textContent = label;
      select.appendChild(opt);
    });
  }

  function startMap(info) {
    const a = info.area;
    const padX = (a.east - a.west) * 0.25;
    const padY = (a.north - a.south) * 0.25;
    state.map = new maplibregl.Map({
      container: "map",
      style: "https://tiles.openfreemap.org/styles/liberty",
      center: [(a.west + a.east) / 2, (a.south + a.north) / 2],
      zoom: 12,
      maxBounds: [[a.west - padX, a.south - padY], [a.east + padX, a.north + padY]],
      attributionControl: false,
    });
    state.map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
    state.map.on("load", addLayers);
  }

  async function init() {
    el.sheetClose.addEventListener("click", closeSheet);
    try {
      const response = await fetch(`${API}/info`);
      if (!response.ok) throw new Error(`status ${response.status}`);
      state.info = await response.json();
    } catch (err) {
      setHint(`Cannot reach the API at ${API}. Is it running?`, true);
      return;
    }
    const info = state.info;
    // The bold label already says the data is made up, so drop that part of the API notice.
    if (info.notice) el.noticeText.textContent = info.notice.replace(/^Made-up demo data\.\s*/, "");

    fillSelect(el.species, info.species.map((s) => ({ value: s.id, label: s.name })));
    fillSelect(el.assessment, info.assessment_dates.map((d) => ({ value: d, label: d })));
    fillDaysAhead();

    el.species.addEventListener("change", scheduleFetch);
    el.assessment.addEventListener("change", () => { fillDaysAhead(); scheduleFetch(); });
    el.days.addEventListener("change", scheduleFetch);

    startMap(info);
  }

  init();
})();
