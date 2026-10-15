// SporaMeteo map app prototype. Everything is simulated locally except the map tiles.
// Query string: lang, state, and for screenshots: date, view, select, sheet, panel, bg, overlay, opacity.
(function () {
  "use strict";

  var SAMPLE = window.SPORAMETEO_SAMPLE;
  var STRINGS = window.STRINGS;
  var params = new URLSearchParams(window.location.search);

  var ABETONE_ID = SAMPLE.selected_square_id;
  var REP_POINT = { lat: 44.1318, lon: 10.6625 };
  var FAVORITES_KEY = "sporameteo.favorites";
  var DETAIL_KM = 60;
  var LESS_FOREST_KM = 15;
  var LOADING_MS = 600;
  // Squares get a hairline border only once they are this wide on screen.
  var HAIRLINE_PX = 16;
  // The 11 by 8 km weather areas are laid out so that the Abetone square sits inside one of them.
  var AREA_COLS = 22;
  var AREA_ROWS = 16;
  var AREA_COL_OFFSET = 9;
  var AREA_ROW_OFFSET = 11;
  // After a search or a favorite the map zooms so that a square is about this wide on screen.
  var FOCUS_SQUARE_PX = 40;
  var FOCUS_KM_MAX = 13;
  var FOCUS_KM_MIN = 3;
  var STATES_WITH_SQUARE = [
    "loading", "first_fetch", "missing_data", "older_update", "request_error", "less_forest", "storage_unavailable"
  ];
  var COLOURS = [
    { id: "green", hex: "#2F7D4A" },
    { id: "blue", hex: "#2B6CB0" },
    { id: "orange", hex: "#C2570C" },
    { id: "purple", hex: "#7B3FA0" },
    { id: "red", hex: "#B3261E" }
  ];
  var PLACES = [
    { key: "abetone", en: "Abetone, Tuscany", it: "Abetone, Toscana", square_id: ABETONE_ID }
  ];
  var RAIN_TOTALS = [[7, 18], [14, 37], [21, 54]];

  var scenario = params.get("state") || "none";
  var needsSquare = STATES_WITH_SQUARE.indexOf(scenario) !== -1 || params.get("select") === "1";

  var state = {
    lang: params.get("lang") || (navigator.language || "en").slice(0, 2),
    dateIdx: needsSquare ? 3 : 0,
    shownIdx: needsSquare ? 3 : 0,
    squareId: needsSquare ? ABETONE_ID : null,
    detailsOpen: needsSquare,
    sheetSize: ["short", "half", "tall"].indexOf(params.get("sheet")) !== -1 ? params.get("sheet") : "short",
    background: params.get("bg") === "contrast" ? "contrast" : "light",
    overlayOn: params.get("overlay") !== "off",
    opacity: params.get("opacity") ? Number(params.get("opacity")) : 60,
    panel: null,
    loading: scenario === "loading",
    loadToken: 0,
    denied: scenario === "location_denied",
    position: null,
    favEdit: null,
    favMessage: null,
    legendMore: false,
    folded: { layers: false, legend: false }
  };
  if (state.lang !== "it") {
    state.lang = "en";
  }
  if (params.get("date")) {
    state.dateIdx = state.shownIdx = Number(params.get("date"));
  }

  var $ = function (id) { return document.getElementById(id); };
  var phoneQuery = window.matchMedia("(max-width: 899px)");
  var els = {
    main: $("main"), dates: $("dates"), dateHint: $("date-hint"), details: $("details"),
    sheetwrap: $("sheetwrap"), mapmsgs: $("mapmsgs"), progress: $("progress"), centreBtn: $("centre-btn"),
    searchForm: $("search-form"), searchInput: $("search-input"), searchResults: $("search-results"),
    live: $("live"), toast: $("toast"), legendBody: $("legend-body"), overlayToggle: $("overlay-toggle"),
    opacity: $("opacity"), opacityValue: $("opacity-value"), favBtn: $("fav-btn"), favCount: $("fav-count"),
    dateAssess: $("date-assess"), zoomIn: $("zoom-in"), zoomOut: $("zoom-out"),
    layersPanel: $("layers-panel"), legendPanel: $("legend-panel"),
    layersBtn: $("layers-btn"), legendBtn: $("legend-btn"),
    favDialog: $("fav-dialog"), saveDialog: $("save-dialog"), navDialog: $("nav-dialog")
  };

  // ---------- Text and dates ----------

  function t(key, vars) {
    var text = STRINGS[state.lang][key];
    if (text === undefined) {
      text = STRINGS.en[key] || key;
    }
    Object.keys(vars || {}).forEach(function (name) {
      text = text.split("{" + name + "}").join(vars[name]);
    });
    return text;
  }

  function esc(value) {
    return String(value).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[c];
    });
  }

  function locale() {
    return state.lang === "it" ? "it-IT" : "en-GB";
  }

  function format(date, options) {
    options.timeZone = "UTC";
    return new Intl.DateTimeFormat(locale(), options).format(date).replace(",", "");
  }

  function capitalise(text) {
    return text.charAt(0).toUpperCase() + text.slice(1);
  }

  function dateAt(index) {
    return new Date(SAMPLE.dates[index] + "T00:00:00Z");
  }

  function longDate(index) {
    return capitalise(format(dateAt(index), { weekday: "long", day: "numeric", month: "long" }));
  }

  function fullDate(index) {
    return capitalise(format(dateAt(index), { weekday: "long", day: "numeric", month: "long", year: "numeric" }));
  }

  function dayMonthYear(date) {
    return format(date, { day: "numeric", month: "long", year: "numeric" });
  }

  function isOlderResult() {
    return scenario === "older_update" || scenario === "request_error";
  }

  function assessmentDate() {
    var date = dateAt(0);
    if (isOlderResult()) {
      date.setUTCDate(date.getUTCDate() - 1);
    }
    return date;
  }

  function updateText() {
    return t("update_value", { date: dayMonthYear(assessmentDate()) });
  }

  // Italian needs "al" or "all'" before a day number.
  function toWord(date, withMonth) {
    var day = date.getUTCDate();
    var text = withMonth ? format(date, { day: "numeric", month: "long" }) : String(day);
    if (state.lang !== "it") {
      return text;
    }
    return (day === 8 || day === 11 ? "all'" : "al ") + text;
  }

  function rainRange(days) {
    var end = assessmentDate();
    end.setUTCDate(end.getUTCDate() - 1);
    var start = new Date(end.getTime());
    start.setUTCDate(start.getUTCDate() - (days - 1));
    if (start.getUTCMonth() === end.getUTCMonth()) {
      return t("rain_range_same", {
        from: start.getUTCDate(), to: toWord(end, false), month: format(end, { month: "long" })
      });
    }
    return t("rain_range_diff", {
      from: format(start, { day: "numeric", month: "long" }), to: toWord(end, true)
    });
  }

  function forestText(share) {
    if (state.lang !== "it") {
      return share + "%";
    }
    var elide = share === 8 || share === 11 || (share >= 80 && share <= 89);
    return (elide ? "l'" : "il ") + share + "%";
  }

  // ---------- Sample data ----------

  var squares = SAMPLE.squares.map(function (square) {
    var bounds = L.latLngBounds(square.bounds);
    return { data: square, id: square.id, bounds: bounds, centre: bounds.getCenter(), layer: null };
  });
  var squaresById = {};
  squares.forEach(function (square) { squaresById[square.id] = square; });

  // The state picker changes how the sample square behaves.
  function effective(square) {
    var data = square.data;
    if (square.id !== ABETONE_ID) {
      return data;
    }
    if (scenario === "missing_data") {
      return Object.assign({}, data, { estimates: null, no_estimate_reason: "missing_data" });
    }
    if (scenario === "less_forest") {
      return Object.assign({}, data, { forest_share: 6, estimates: null, no_estimate_reason: "less_forest" });
    }
    return data;
  }

  function estimateAt(square, index) {
    var data = effective(square);
    if (!data.estimates || data.no_estimate_reason) {
      return null;
    }
    return data.estimates[index];
  }

  function selectedSquare() {
    return state.squareId ? squaresById[state.squareId] : null;
  }

  function pointOf(square) {
    if (square.id === ABETONE_ID) {
      return REP_POINT;
    }
    return { lat: square.centre.lat, lon: square.centre.lng };
  }

  function placeName(square) {
    return t(square.id === ABETONE_ID ? "place_abetone" : "place_near");
  }

  // ---------- Map ----------

  var cssVar = function (name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  };
  var SCALE = [0, 1, 2, 3, 4].map(function (step) { return cssVar("--scale-" + step); });
  var SQUARE_BORDER = "rgba(17, 34, 27, 0.08)";
  var GREY = "#5d6666";

  function hatchPattern() {
    var tile = document.createElement("canvas");
    tile.width = tile.height = 8;
    var ctx = tile.getContext("2d");
    ctx.fillStyle = "rgba(255, 255, 255, 0.8)";
    ctx.fillRect(0, 0, 8, 8);
    ctx.strokeStyle = "#7d8585";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(-2, 10);
    ctx.lineTo(10, -2);
    ctx.moveTo(-2, 2);
    ctx.lineTo(2, -2);
    ctx.moveTo(6, 10);
    ctx.lineTo(10, 6);
    ctx.stroke();
    return ctx.createPattern(tile, "repeat");
  }

  var map = L.map("map", {
    zoomSnap: 0.25,
    zoomDelta: 0.5,
    minZoom: 4,
    maxZoom: 17,
    attributionControl: false,
    zoomControl: false,
    worldCopyJump: false
  });
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19 }).addTo(map);

  var canvas = L.canvas({ padding: 0.3 });
  // The squares sit in their own pane and multiply with the map, so low values leave roads and names readable.
  map.createPane("squares").style.zIndex = 350;
  map.getPane("squares").style.mixBlendMode = "multiply";
  var squaresCanvas = L.canvas({ padding: 0.3, pane: "squares" });
  var HATCH = hatchPattern();
  var forestLayer = L.imageOverlay(SAMPLE.national_forest.url, SAMPLE.national_forest.bounds, {
    interactive: false, opacity: 0.9
  });
  var haloLayer = L.rectangle([[0, 0], [0, 0]], {
    renderer: canvas, interactive: false, color: "#ffffff", weight: 7, fill: false
  });
  var outlineLayer = L.rectangle([[0, 0], [0, 0]], {
    renderer: canvas, interactive: false, color: cssVar("--pine-600"), weight: 3, fill: false
  });
  var areaLayer = L.rectangle([[0, 0], [0, 0]], {
    renderer: canvas, interactive: false, color: cssVar("--pine-600"), weight: 2, dashArray: "8 6", fill: false
  });
  var positionMarker = null;
  var mode = { detail: null, near: null, hairline: false, km: 0 };

  squares.forEach(function (square) {
    square.layer = L.rectangle(square.bounds, { renderer: squaresCanvas, interactive: false, weight: 1 });
  });

  function mapWidthKm() {
    var bounds = map.getBounds();
    var lat = map.getCenter().lat;
    return map.distance(L.latLng(lat, bounds.getWest()), L.latLng(lat, bounds.getEast())) / 1000;
  }

  function zoomForWidthKm(lat, km) {
    var metresPerPixel = (km * 1000) / map.getSize().x;
    return Math.log2((156543.03 * Math.cos(lat * Math.PI / 180)) / metresPerPixel);
  }

  function squareStyle(square) {
    var data = effective(square);
    if (!data.estimates && !data.no_estimate_reason) {
      data = Object.assign({}, data, { no_estimate_reason: "missing_data" });
    }
    var style = {
      stroke: mode.hairline, weight: 1, color: SQUARE_BORDER, opacity: 1, dashArray: null,
      fill: true, fillColor: SCALE[0], fillOpacity: state.opacity / 100
    };
    if (data.no_estimate_reason === "missing_data") {
      return Object.assign(style, { stroke: true, color: GREY, dashArray: "5 3", fillColor: HATCH, fillOpacity: 0.95 });
    }
    if (data.no_estimate_reason === "less_forest") {
      var drawn = mode.km <= LESS_FOREST_KM;
      return Object.assign(style, { stroke: drawn, color: GREY, weight: 2, dashArray: "1 4", fill: false });
    }
    var value = data.estimates[state.shownIdx];
    style.fillColor = SCALE[Math.min(4, Math.floor(value / 20))];
    return style;
  }

  function restyleSquares() {
    squares.forEach(function (square) { square.layer.setStyle(squareStyle(square)); });
    drawSelection();
  }

  function setSquaresVisible(visible) {
    squares.forEach(function (square) {
      var onMap = map.hasLayer(square.layer);
      if (visible && !onMap) {
        square.layer.addTo(map);
      } else if (!visible && onMap) {
        square.layer.remove();
      }
    });
  }

  function drawSelection() {
    var square = selectedSquare();
    if (!square || !mode.detail) {
      haloLayer.remove();
      outlineLayer.remove();
      areaLayer.remove();
      drawDecor();
      return;
    }
    haloLayer.setBounds(square.bounds);
    outlineLayer.setBounds(square.bounds);
    areaLayer.setBounds(weatherAreaOf(square));
    areaLayer.addTo(map);
    haloLayer.addTo(map).bringToFront();
    outlineLayer.addTo(map).bringToFront();
    drawDecor();
  }

  // ---------- Percentages and weather area label ----------

  var gridOrigin = (function () {
    var first = squares[0].bounds;
    return {
      south: first.getSouth(), west: first.getWest(),
      latStep: first.getNorth() - first.getSouth(), lonStep: first.getEast() - first.getWest()
    };
  }());
  var areaLabel = document.createElement("div");
  areaLabel.className = "area-label";
  areaLabel.hidden = true;
  map.getContainer().appendChild(areaLabel);

  // The sample has no real weather grid, so the area is a block of 22 by 16 squares around the selection.
  function weatherAreaOf(square) {
    var row = Math.round((square.bounds.getSouth() - gridOrigin.south) / gridOrigin.latStep);
    var col = Math.round((square.bounds.getWest() - gridOrigin.west) / gridOrigin.lonStep);
    var firstRow = AREA_ROW_OFFSET + Math.floor((row - AREA_ROW_OFFSET) / AREA_ROWS) * AREA_ROWS;
    var firstCol = AREA_COL_OFFSET + Math.floor((col - AREA_COL_OFFSET) / AREA_COLS) * AREA_COLS;
    var south = gridOrigin.south + firstRow * gridOrigin.latStep;
    var west = gridOrigin.west + firstCol * gridOrigin.lonStep;
    return L.latLngBounds(
      [south, west],
      [south + AREA_ROWS * gridOrigin.latStep, west + AREA_COLS * gridOrigin.lonStep]
    );
  }

  function drawAreaLabel() {
    var square = selectedSquare();
    if (!square || !mode.detail) {
      areaLabel.hidden = true;
      return;
    }
    var bounds = weatherAreaOf(square);
    var nw = map.latLngToContainerPoint(bounds.getNorthWest());
    var se = map.latLngToContainerPoint(bounds.getSouthEast());
    var size = map.getSize();
    areaLabel.hidden = false;
    areaLabel.textContent = t("area_label");
    var width = areaLabel.offsetWidth;
    var height = areaLabel.offsetHeight;
    // On phones the zoom buttons take the top left corner of the map.
    var edge = phoneQuery.matches ? 64 : 8;
    var left = Math.min(Math.max(nw.x + 8, edge), se.x - width - 8);
    var top = Math.min(Math.max(nw.y + 8, 8), se.y - height - 8);
    var fits = left >= edge && top >= 8 && left <= size.x - width - 8 && top <= size.y - height - 8;
    areaLabel.hidden = !fits;
    areaLabel.style.left = Math.round(left) + "px";
    areaLabel.style.top = Math.round(top) + "px";
  }

  var decorFrame = 0;
  function scheduleDecor() {
    if (!decorFrame) {
      decorFrame = window.requestAnimationFrame(function () {
        decorFrame = 0;
        drawDecor();
      });
    }
  }

  function drawDecor() {
    drawAreaLabel();
  }

  function forestOpacity() {
    return Math.min(1, (state.opacity / 100) * 1.5);
  }

  function refreshMapMode() {
    var km = mapWidthKm();
    var detail = km <= DETAIL_KM;
    var near = km <= LESS_FOREST_KM;
    var sample = squares[0].bounds;
    var squarePx = Math.abs(map.latLngToContainerPoint(sample.getNorthEast()).x -
      map.latLngToContainerPoint(sample.getSouthWest()).x);
    var hairline = squarePx >= HAIRLINE_PX;
    var changed = detail !== mode.detail || near !== mode.near || hairline !== mode.hairline;
    mode.hairline = hairline;
    mode.km = km;
    mode.detail = detail;
    mode.near = near;
    if (changed) {
      setSquaresVisible(detail && state.overlayOn);
      if (detail || !state.overlayOn) {
        forestLayer.remove();
      } else {
        forestLayer.addTo(map);
      }
      restyleSquares();
    }
    els.centreBtn.hidden = !detail;
    renderMessages();
  }

  function applyOverlayVisibility() {
    mode.detail = null;
    refreshMapMode();
    forestLayer.setOpacity(forestOpacity());
    drawDecor();
  }

  function applyBackground() {
    var container = map.getContainer();
    container.classList.toggle("bg-light", state.background === "light");
    container.classList.toggle("bg-contrast", state.background === "contrast");
  }

  function focusKm() {
    var km = map.getSize().x * 0.5 / FOCUS_SQUARE_PX;
    return Math.max(FOCUS_KM_MIN, Math.min(FOCUS_KM_MAX, km));
  }

  function flyTo(latlng, km) {
    var zoom = Math.min(map.getMaxZoom(), zoomForWidthKm(latlng.lat, km || focusKm()));
    var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      map.setView(latlng, zoom, { animate: false });
    } else {
      map.flyTo(latlng, zoom, { duration: 1.2 });
    }
  }

  // On a phone the open sheet hides the bottom of the map, so move the square up.
  function keepSquareVisible(square) {
    if (!phoneQuery.matches || !state.detailsOpen) {
      return;
    }
    window.requestAnimationFrame(function () {
      var size = map.getSize();
      var covered = Math.min(els.details.offsetHeight + 60, size.y);
      var visible = size.y - covered;
      var y = map.latLngToContainerPoint(square.centre).y;
      if (y > visible - 20 || y < 30) {
        map.panBy([0, y - Math.max(visible, 80) / 2], { animate: true });
      }
    });
  }

  // ---------- Selecting squares ----------

  function selectableSquares() {
    return squares.filter(function (square) {
      return !(effective(square).no_estimate_reason === "less_forest" && !mode.near);
    });
  }

  function findSquareAt(latlng) {
    var candidates = selectableSquares();
    var inside = candidates.filter(function (square) { return square.bounds.contains(latlng); });
    if (inside.length) {
      return inside[0];
    }
    var point = map.latLngToContainerPoint(latlng);
    var best = null;
    var bestDistance = 22;
    candidates.forEach(function (square) {
      var distance = point.distanceTo(map.latLngToContainerPoint(square.centre));
      if (distance < bestDistance) {
        best = square;
        bestDistance = distance;
      }
    });
    return best;
  }

  function selectSquare(square, options) {
    state.squareId = square.id;
    state.detailsOpen = true;
    if (options && options.size) {
      state.sheetSize = options.size;
    } else if (!options || !options.keepSize) {
      state.sheetSize = "short";
    }
    renderDetails();
    renderDates();
    drawSelection();
    announceSelection();
    keepSquareVisible(square);
    if (options && options.focus) {
      focusDetails();
    }
  }

  function announceSelection() {
    var square = selectedSquare();
    if (!square || !state.detailsOpen) {
      return;
    }
    var pct = estimateAt(square, state.shownIdx);
    var vars = { place: t("place_short"), date: fullDate(state.shownIdx).replace(/^\S+ /, ""), pct: pct };
    var kind = detailsKind(square);
    say(kind === "estimate" ? t("selected_sentence", vars) : t("selected_none_sentence", vars));
  }

  function say(text) {
    els.live.textContent = "";
    window.requestAnimationFrame(function () { els.live.textContent = text; });
  }

  var toastTimer = null;
  function toast(text) {
    els.toast.textContent = text;
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(function () { els.toast.textContent = ""; }, 6000);
  }

  function focusDetails() {
    var heading = $("details-heading");
    if (heading) {
      heading.focus();
    }
  }

  function closeDetails(deselect) {
    state.detailsOpen = false;
    if (deselect) {
      state.squareId = null;
    }
    renderDetails();
    renderDates();
    drawSelection();
  }

  // ---------- Loading ----------

  function isLoading() {
    return state.loading || scenario === "loading";
  }

  function startLoading(done) {
    state.loading = true;
    state.loadToken += 1;
    var token = state.loadToken;
    renderLoading();
    window.setTimeout(function () {
      if (token !== state.loadToken) {
        return;
      }
      state.loading = false;
      done();
      renderLoading();
    }, LOADING_MS);
  }

  function renderLoading() {
    els.progress.hidden = !isLoading();
    renderMessages();
    if (state.detailsOpen) {
      renderDetails();
    }
  }

  function setDate(index) {
    if (index === state.dateIdx && !state.loading) {
      return;
    }
    state.dateIdx = index;
    renderDates();
    startLoading(function () {
      state.shownIdx = state.dateIdx;
      restyleSquares();
      renderDetails();
      announceSelection();
    });
  }

  function retry() {
    startLoading(function () {
      if (scenario === "request_error") {
        scenario = "none";
      }
      restyleSquares();
      renderAll();
      announceSelection();
    });
  }

  // ---------- Dates ----------

  function keepFocus(container, render) {
    var active = document.activeElement;
    var inside = active && container.contains(active);
    var key = inside ? active.getAttribute("data-act") || active.getAttribute("data-i") : null;
    var attr = inside && active.hasAttribute("data-act") ? "data-act" : "data-i";
    var scroll = container.scrollTop;
    render();
    container.scrollTop = scroll;
    if (key !== null) {
      var target = container.querySelector("[" + attr + "=\"" + key + "\"]");
      if (target) {
        target.focus();
      }
    }
  }

  function dateButton(index) {
    var square = selectedSquare();
    var value = square ? estimateAt(square, index) : null;
    var waiting = scenario === "first_fetch";
    var pct = "";
    var spoken = "";
    if (square) {
      if (value !== null && !waiting) {
        pct = value + "%";
        spoken = ", " + value + "%";
      } else {
        pct = "<span aria-hidden=\"true\">-</span>";
        spoken = ", " + t("estimate_unavailable");
      }
    }
    var date = dateAt(index);
    var today = index === 0;
    var weekday = today ? t("today") : capitalise(format(date, { weekday: "short" }).replace(".", ""));
    var dayMonth = format(date, { day: "numeric", month: "short" }).replace(".", "");
    var label = longDate(index) + (today ? ", " + t("today") : "") + spoken;
    return "<li><button type=\"button\" class=\"date-btn\" data-i=\"" + index + "\" aria-pressed=\"" +
      (index === state.dateIdx) + "\" aria-label=\"" + esc(label) + "\">" +
      "<span class=\"d-wd\">" + esc(weekday) + "</span><span class=\"d-dm\">" + esc(dayMonth) + "</span>" +
      "<span class=\"d-pct\">" + pct + "</span></button></li>";
  }

  function renderDates() {
    keepFocus(els.dates, function () {
      els.dates.innerHTML = SAMPLE.dates.map(function (_, index) { return dateButton(index); }).join("");
    });
    els.dateHint.hidden = !!selectedSquare();
    els.dateAssess.textContent = t("assessment_short", { date: dayMonthYear(assessmentDate()) });
    scrollChipIntoView();
  }

  function scrollChipIntoView() {
    var chip = els.dates.querySelector("[aria-pressed=\"true\"]");
    if (!chip || els.dates.scrollWidth <= els.dates.clientWidth) {
      return;
    }
    var left = chip.offsetLeft - (els.dates.clientWidth - chip.offsetWidth) / 2;
    els.dates.scrollTo({ left: left, behavior: "auto" });
  }

  // ---------- Map messages ----------

  var messageSignature = "";

  function messageHtml(kind, html, extraClass) {
    return "<div class=\"msg " + (extraClass || "") + "\" data-kind=\"" + kind + "\">" + html + "</div>";
  }

  function renderMessages() {
    var items = [];
    var km = Math.round(mode.km);
    if (isLoading()) {
      items.push(messageHtml("loading",
        "<span class=\"spinner\" aria-hidden=\"true\"></span><span>" +
        t("loading_date", { date: longDate(state.dateIdx) }) + "</span>", "msg-wait"));
    }
    if (mode.detail === false) {
      items.push(messageHtml("zoom", esc(t("zoom_hint")) +
        "<span class=\"msg-width\" aria-hidden=\"true\"></span>"));
    }
    if (scenario === "older_update") {
      items.push(messageHtml("older", "<strong>" + t("older_title") + "</strong>" + olderText(),
        "msg-older msg-dup"));
    }
    if (scenario === "request_error") {
      var retryButton = state.detailsOpen ? "" : "<br><button type=\"button\" class=\"btn btn-secondary\" " +
        "data-act=\"retry\">" + t("retry") + "</button>";
      items.push(messageHtml("error", "<strong>" + t("error_title") + "</strong>" + t("error_text") + retryButton,
        "msg-error msg-dup"));
    }
    if (state.denied) {
      items.push(messageHtml("denied", "<strong>" + t("location_denied") + "</strong>" + t("location_denied_help") +
        "<br><button type=\"button\" class=\"btn btn-secondary\" data-act=\"focus-search\">" +
        t("search") + "</button>", "msg-error"));
    }
    if (scenario === "storage_unavailable") {
      items.push(messageHtml("storage", "<strong>" + t("unsaved") + "</strong>" + t("unsaved_banner"), "msg-error"));
    }
    var signature = state.lang + "|" + items.join("");
    if (signature !== messageSignature) {
      messageSignature = signature;
      els.mapmsgs.innerHTML = items.join("");
    }
    var width = els.mapmsgs.querySelector(".msg-width");
    if (width) {
      width.textContent = t("map_width", { km: km >= 100 ? Math.round(km / 10) * 10 : km });
    }
  }

  function olderText() {
    return t("older_text", {
      target: fullDate(state.shownIdx).replace(/^\S+ /, ""),
      assessment: dayMonthYear(assessmentDate()),
      update: updateText()
    });
  }

  // ---------- Details ----------

  function detailsKind(square) {
    var reason = effective(square).no_estimate_reason;
    if (reason === "less_forest") {
      return "less_forest";
    }
    if (reason === "missing_data") {
      return "missing";
    }
    return scenario === "first_fetch" ? "waiting" : "estimate";
  }

  function sizeLabel() {
    return { short: "more_details", half: "taller", tall: "less_details" }[state.sheetSize];
  }

  function sizeButton() {
    return "<button type=\"button\" class=\"btn btn-secondary d-size phone-only\" data-act=\"size\">" +
      t(sizeLabel()) + "</button>";
  }

  var INFO_ICON = "<svg class=\"icon\" viewBox=\"0 0 24 24\" aria-hidden=\"true\"><circle cx=\"12\" cy=\"12\" r=\"9\"/>" +
    "<path d=\"M12 11v6M12 7.5v.01\"/></svg>";

  function noticeExperimental() {
    return "<div class=\"notice-experimental\">" + INFO_ICON + "<p><strong>" + t("note_label") + "</strong> " +
      t("note_text") + "</p></div>";
  }

  function dateRow(badge) {
    return "<div class=\"date-row\"><div class=\"date-block\"><span class=\"date-label\">" + t("date_label") +
      "</span><span class=\"date-big\">" + fullDate(state.shownIdx) + "</span></div>" + badge + "</div>";
  }

  function statusHtml(square, kind, pct) {
    var html = "";
    if (scenario === "request_error") {
      html += "<div class=\"callout callout-error\" role=\"alert\"><strong>" + t("error_title") + "</strong>" +
        t("error_text") + "<br><button type=\"button\" class=\"btn btn-secondary\" data-act=\"retry\">" +
        t("retry") + "</button></div>";
    }
    if (scenario === "older_update") {
      html += "<div class=\"callout callout-older\"><strong>" + t("older_title") + "</strong>" +
        olderText() + "</div>";
    }
    if (kind === "estimate") {
      var caption = isOlderResult() ?
        "<span class=\"pct-caption\">" + t("older_percent_caption", { date: fullDate(state.shownIdx) }) + ". " +
        t("updated") + ": " + updateText() + "</span>" : "";
      html += dateRow("<span class=\"pct-badge\"><span class=\"pct\">" + pct + "%</span><span class=\"pct-unit\">" +
        t("pct_unit") + "</span></span>" + sizeButton() + caption) + noticeExperimental();
    } else if (kind === "waiting") {
      html += dateRow(sizeButton()) +
        "<div class=\"callout callout-wait\"><span class=\"spinner\" aria-hidden=\"true\"></span><span>" +
        t("waiting") + "</span></div>";
    } else {
      var message = kind === "missing" ? t("no_estimate") : t("less_forest");
      html += dateRow(sizeButton()) + "<div class=\"callout\"><strong>" + message + "</strong>" +
        (kind === "missing" ? t("no_estimate_help") : "") + "<br>" +
        "<button type=\"button\" class=\"btn btn-primary\" data-act=\"pick\">" + t("pick_another") + "</button>" +
        (kind === "missing" ? "<button type=\"button\" class=\"btn btn-secondary\" data-act=\"retry\">" +
          t("retry") + "</button>" : "") + "</div>";
    }
    return html;
  }

  function kvRow(label, value) {
    return "<div class=\"kv\"><dt>" + label + "</dt><dd>" + value + "</dd></div>";
  }

  function forestTile(share) {
    return "<div class=\"tile\"><span class=\"tile-label\">" + t("forest_heading") + "</span>" +
      "<span class=\"tile-value\">" + share + "%</span><div class=\"forest-bar\" aria-hidden=\"true\">" +
      "<i style=\"width:" + share + "%\"></i></div></div>";
  }

  function weatherHtml(share) {
    return "<section class=\"d-sec\"><h3>" + t("weather_heading") + "</h3><div class=\"tiles\">" +
      forestTile(share) +
      "<div class=\"tile\"><span class=\"tile-label\">" + t("temperature") + "</span><span class=\"tile-value\">" +
      "13°C<small>" + t("minimum", { n: "8°C" }) + "</small></span><span class=\"tile-sub\">" +
      t("drying", { level: t("drying_low") }) + "</span></div>" +
      "<div class=\"tile\"><span class=\"tile-label\">" + t("frost") + "</span><span class=\"tile-text\">" +
      t("frost_none") + "</span></div>" +
      "<div class=\"tile\"><span class=\"tile-label\">" + t("hail") + "</span><span class=\"tile-text\">" +
      t("hail_missing") + "</span></div></div></section>";
  }

  function rainHtml() {
    var rows = RAIN_TOTALS.map(function (pair) {
      return "<div class=\"rain-row\"><dt>" + t("rain_row", { n: pair[0], range: rainRange(pair[0]) }) +
        "</dt><dd>" + pair[1] + " mm</dd></div>";
    }).join("");
    var end = assessmentDate();
    end.setUTCDate(end.getUTCDate() - 1);
    var until = toWord(end, true);
    return "<section class=\"d-sec\"><h3>" + t("rain_heading") + "</h3><dl>" + rows + "</dl><p class=\"rain-note\">" +
      t("rain_note", { until: until }) + "</p></section>";
  }

  function actionsHtml() {
    return "<div class=\"d-more\"><div class=\"d-actions\">" +
      "<button type=\"button\" class=\"btn btn-secondary\" data-act=\"save\">" + t("save_favorite") + "</button>" +
      "<button type=\"button\" class=\"btn btn-primary\" data-act=\"nav\">" + t("open_navigation") + "</button>" +
      "</div></div>";
  }

  function moreHtml(square, kind) {
    var data = effective(square);
    var html = "";
    if (kind === "estimate") {
      html += "<section class=\"d-sec\"><h3>" + t("facts_heading") + "</h3><p class=\"facts\">" +
        t("facts_text", { forest: forestText(data.forest_share) }) + "</p></section>";
      html += weatherHtml(data.forest_share) + rainHtml();
    } else {
      html += "<section class=\"d-sec\"><div class=\"tiles\">" + forestTile(data.forest_share) + "</div></section>";
    }
    html += "<section class=\"d-sec\"><h3>" + t("area_heading") + "</h3><p class=\"callout callout-info\">" +
      t("area_text") + "</p></section>";
    html += "<section class=\"d-sec sources\"><h3>" + t("sources_heading") + "</h3><ul><li>" + t("src_forest") +
      "</li><li>" + t("src_weather") + "</li><li>" + t("src_osm") + "</li></ul><p class=\"muted\">" +
      t("src_dates") + "</p>";
    html += "<dl>" + kvRow(t("target_day"), dayMonthYear(dateAt(state.shownIdx))) +
      kvRow(t("assessment"), dayMonthYear(assessmentDate())) +
      kvRow(t("updated"), updateText()) + "</dl></section>";
    html += "<p class=\"notice-sample d-sample\"><strong>" + t("design_label") + "</strong> " + t("design_text") + "</p>";
    return html;
  }

  function renderDetails() {
    var square = selectedSquare();
    var open = state.detailsOpen && square;
    $("app").classList.toggle("has-overlay", !!open || !!state.panel);
    renderMessages();
    els.details.hidden = !open;
    els.main.classList.toggle("details-open", !!open);
    els.sheetwrap.classList.toggle("is-tall", !!open && state.sheetSize === "tall");
    if (!open) {
      return;
    }
    var kind = detailsKind(square);
    var pct = estimateAt(square, state.shownIdx);
    els.details.dataset.size = state.sheetSize;
    keepFocus(els.details, function () {
      var point = pointOf(square);
      els.details.innerHTML =
        "<div class=\"d-top\"><div><h2 id=\"details-heading\" tabindex=\"-1\">" + placeName(square) + "</h2>" +
        "<p class=\"d-coord\">" + t("point_value", { lat: point.lat.toFixed(4), lon: point.lon.toFixed(4) }) +
        "<span class=\"d-coord-label\">" + t("point_label") + "</span></p></div>" +
        "<button type=\"button\" class=\"btn btn-secondary phone-only\" data-act=\"close\">" + t("back_to_map") +
        "</button><button type=\"button\" class=\"btn btn-secondary btn-icon desktop-only\" data-act=\"close\" " +
        "aria-label=\"" + t("close_details") + "\" title=\"" + t("close_details") + "\">" +
        "<svg class=\"icon\" viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M6 6l12 12M18 6L6 18\"/></svg>" +
        "</button></div>" + actionsHtml() +
        "<div class=\"d-status\">" + statusHtml(square, kind, pct) + "</div>" +
        "<div class=\"d-more\">" + moreHtml(square, kind) + "</div>";
    });
    els.details.setAttribute("aria-label", t("details_label"));
    els.details.removeAttribute("aria-labelledby");
  }

  function onDetailsClick(event) {
    var button = event.target.closest("[data-act]");
    if (!button) {
      return;
    }
    var act = button.getAttribute("data-act");
    if (act === "close") {
      closeDetails(false);
      document.getElementById("map").focus();
    } else if (act === "size") {
      var order = ["short", "half", "tall"];
      state.sheetSize = order[(order.indexOf(state.sheetSize) + 1) % order.length];
      renderDetails();
    } else if (act === "save") {
      openSaveDialog();
    } else if (act === "nav") {
      openNavDialog();
    } else if (act === "retry") {
      retry();
    } else if (act === "pick") {
      closeDetails(true);
      toast(t("pick_prompt"));
      document.getElementById("map").focus();
    }
  }

  // ---------- Layers and legend ----------

  function legendRow(swatchClass, style, label) {
    return "<div class=\"legend-row\"><span class=\"sw " + swatchClass + "\"" + (style ? " style=\"" + style + "\"" : "") +
      " aria-hidden=\"true\"></span><span>" + label + "</span></div>";
  }

  function renderLegend() {
    var scale = SCALE.map(function (colour, step) {
      return legendRow("", "background:" + colour, t("range_" + step));
    }).join("");
    var chips = SCALE.map(function (colour, step) {
      return "<span class=\"lg-chip\" title=\"" + t("range_" + step) + "\"><i style=\"background:" + colour +
        "\"></i>" + t("range_short_" + step) + "</span>";
    }).join("");
    var more = state.legendMore;
    var compact = "<div class=\"lg-compact\"><p class=\"legend-title\">" + t("legend_scale_short") + "</p>" +
      "<div class=\"lg-scale\">" + chips + "</div><div class=\"lg-pair\">" +
      "<span class=\"lg-item\"><i class=\"sw sw-missing\"></i>" + t("legend_missing_short") + "</span>" +
      "<span class=\"lg-item\"><i class=\"sw sw-less\"></i>" + t("legend_less_short") + "</span></div>" +
      "<button type=\"button\" class=\"lg-toggle\" data-lg-toggle aria-expanded=\"" + more + "\">" +
      t(more ? "legend_fewer" : "legend_more") + "</button>" +
      (more ? "<div class=\"lg-extra\">" + legendRow("sw-selected", "", t("legend_selected")) +
        legendRow("sw-area", "", t("legend_area")) + legendRow("sw-forest", "", t("legend_forest")) +
        "<p class=\"legend-note\">" + t("legend_note") + "</p></div>" : "") + "</div>";
    els.legendBody.innerHTML = compact + "<div class=\"lg-full\">" +
      "<div class=\"legend-group\"><p class=\"legend-title\">" + t("legend_scale") + "</p>" + scale + "</div>" +
      "<div class=\"legend-group\"><p class=\"legend-title\">" + t("legend_other") + "</p>" +
      legendRow("sw-missing", "", t("legend_missing")) + legendRow("sw-less", "", t("legend_less_forest")) +
      legendRow("sw-selected", "", t("legend_selected")) + legendRow("sw-area", "", t("legend_area")) + "</div>" +
      "<div class=\"legend-group\">" + legendRow("sw-forest", "", t("legend_forest")) + "</div>" +
      "<p class=\"legend-note\">" + t("legend_note") + "</p></div>";
  }

  function applyFold() {
    document.querySelectorAll("[data-fold]").forEach(function (button) {
      var name = button.getAttribute("data-fold");
      var folded = !!state.folded[name];
      $(name + "-body").hidden = folded;
      $(name + "-panel").classList.toggle("is-folded", folded);
      button.setAttribute("aria-expanded", String(!folded));
      button.title = button.ariaLabel = t(folded ? "fold_show" : "fold_hide");
    });
  }

  function renderLayers() {
    els.overlayToggle.setAttribute("aria-checked", String(state.overlayOn));
    els.opacity.value = state.opacity;
    els.opacityValue.textContent = state.opacity + "%";
    document.querySelectorAll("input[name=\"background\"]").forEach(function (input) {
      input.checked = input.value === state.background;
    });
  }

  var panelOpeners = { layers: els.layersBtn, legend: els.legendBtn };

  function setPanel(name, focusOpener) {
    var previous = state.panel;
    state.panel = name;
    $("app").classList.toggle("has-overlay", !!name || (state.detailsOpen && !!state.squareId));
    els.layersPanel.classList.toggle("is-open", name === "layers");
    els.legendPanel.classList.toggle("is-open", name === "legend");
    els.layersBtn.setAttribute("aria-expanded", String(name === "layers"));
    els.legendBtn.setAttribute("aria-expanded", String(name === "legend"));
    if (name && phoneQuery.matches) {
      var panel = name === "layers" ? els.layersPanel : els.legendPanel;
      panel.querySelector(".panel-close").focus();
    } else if (!name && previous && focusOpener) {
      panelOpeners[previous].focus();
    }
  }

  function togglePanel(name) {
    setPanel(state.panel === name ? null : name, true);
  }

  // ---------- Search and location ----------

  function matchPlaces(query) {
    var text = query.trim().toLowerCase();
    if (!text) {
      return [];
    }
    return PLACES.filter(function (place) {
      return place.en.toLowerCase().indexOf(text) !== -1 || place.it.toLowerCase().indexOf(text) !== -1;
    });
  }

  function renderSearchResults() {
    var query = els.searchInput.value;
    if (!query.trim()) {
      els.searchResults.hidden = true;
      return;
    }
    var matches = matchPlaces(query);
    els.searchResults.hidden = false;
    if (matches.length) {
      els.searchResults.innerHTML = matches.map(function (place) {
        return "<button type=\"button\" class=\"result\" data-place=\"" + place.key + "\">" +
          esc(place[state.lang]) + "</button>";
      }).join("");
    } else {
      els.searchResults.innerHTML = "<div class=\"result-empty\" role=\"status\"><strong>" + t("no_results") +
        "</strong><p>" + t("no_results_hint") + "</p></div>";
    }
  }

  function choosePlace(key) {
    var place = PLACES.filter(function (item) { return item.key === key; })[0];
    var square = squaresById[place.square_id];
    els.searchInput.value = place[state.lang];
    els.searchResults.hidden = true;
    flyTo(L.latLng(REP_POINT.lat, REP_POINT.lon));
    selectSquare(square, { keepSize: false });
  }

  function useLocation() {
    if (scenario === "location_denied") {
      state.denied = true;
      renderMessages();
      say(t("location_denied") + ". " + t("location_denied_help"));
      return;
    }
    state.denied = false;
    state.position = L.latLng(44.1215, 10.6598);
    placePositionMarker();
    flyTo(state.position);
    renderMessages();
    toast(t("sim_location_status"));
  }

  function placePositionMarker() {
    if (!state.position) {
      return;
    }
    var icon = L.divIcon({
      className: "pos-marker",
      html: "<span>" + t("sim_location_label") + "</span><i></i>",
      iconSize: [0, 0]
    });
    if (positionMarker) {
      positionMarker.setIcon(icon);
    } else {
      positionMarker = L.marker(state.position, { icon: icon, interactive: false, keyboard: false }).addTo(map);
    }
  }

  // ---------- Favorites ----------

  function readFavorites() {
    try {
      return JSON.parse(window.localStorage.getItem(FAVORITES_KEY) || "[]");
    } catch (error) {
      return [];
    }
  }

  // Returns true only when the browser really stored the list.
  function writeFavorites(list) {
    try {
      if (scenario === "storage_unavailable") {
        throw new Error("storage unavailable");
      }
      window.localStorage.setItem(FAVORITES_KEY, JSON.stringify(list));
      return true;
    } catch (error) {
      return false;
    }
  }

  function colourById(id) {
    return COLOURS.filter(function (colour) { return colour.id === id; })[0] || COLOURS[0];
  }

  function colourName(id) {
    return t("colour_" + id);
  }

  function colourDot(id) {
    return "<span class=\"dot\" style=\"background:" + colourById(id).hex + "\" aria-hidden=\"true\"></span>";
  }

  function renderFavCount() {
    var count = readFavorites().length;
    els.favCount.textContent = count ? String(count) : "";
  }

  function modalHead(headingId, title) {
    return "<div class=\"modal-head\"><h2 id=\"" + headingId + "\" tabindex=\"-1\">" + title + "</h2>" +
      "<button type=\"button\" class=\"btn btn-secondary\" data-close>" + t("close") + "</button></div>";
  }

  function favPercent(item) {
    var square = squaresById[item.square_id];
    var value = square ? estimateAt(square, 0) : null;
    return value === null ? t("fav_no_estimate") : t("fav_today", { pct: value });
  }

  function favItemHtml(item) {
    var editing = state.favEdit && state.favEdit.id === item.id ? state.favEdit.mode : null;
    var id = esc(item.id);
    var coordinate = "<p class=\"fav-coord\">" + t("point_value", { lat: item.lat.toFixed(4), lon: item.lon.toFixed(4) }) +
      "</p>";
    var body = "<div class=\"fav-top\"><span class=\"fav-name\">" + colourDot(item.colour) + "<span>" +
      esc(item.name) + "</span></span><span class=\"fav-pct\">" + favPercent(item) + "</span></div>" + coordinate +
      "<p class=\"fav-colour\">" + colourName(item.colour) + "</p>";
    var buttons = "";
    if (editing === "edit") {
      body = "<div class=\"field\"><label for=\"rename-" + id + "\">" + t("fav_name") + "</label>" +
        "<input type=\"text\" id=\"rename-" + id + "\" value=\"" + esc(item.name) + "\" data-field=\"name\"></div>" +
        "<div class=\"field\"><label for=\"colour-" + id + "\">" + t("fav_colour") + "</label>" +
        "<select id=\"colour-" + id + "\" data-field=\"colour\">" + COLOURS.map(function (colour) {
          return "<option value=\"" + colour.id + "\"" + (colour.id === item.colour ? " selected" : "") + ">" +
            colourName(colour.id) + "</option>";
        }).join("") + "</select></div>";
      buttons = "<button type=\"button\" class=\"btn btn-primary\" data-fav-act=\"apply\">" + t("save") +
        "</button><button type=\"button\" class=\"btn btn-secondary\" data-fav-act=\"cancel\">" + t("cancel") +
        "</button>";
    } else if (editing === "remove") {
      body += "<p><strong>" + t("remove_confirm", { name: esc(item.name) }) + "</strong></p>";
      buttons = "<button type=\"button\" class=\"btn btn-danger\" data-fav-act=\"confirm-remove\">" + t("remove") +
        "</button><button type=\"button\" class=\"btn btn-secondary\" data-fav-act=\"cancel\">" + t("keep") + "</button>";
    } else {
      buttons = [["open", "open", "btn-primary"], ["edit", "edit_fav", "btn-secondary"],
        ["remove", "remove", "btn-remove"]].map(function (spec) {
        return "<button type=\"button\" class=\"btn " + spec[2] + "\" data-fav-act=\"" + spec[0] + "\" aria-label=\"" +
          t(spec[1]) + ": " + esc(item.name) + "\">" + t(spec[1]) + "</button>";
      }).join("");
    }
    return "<li class=\"fav-item\" data-fav=\"" + id + "\">" + body + "<div class=\"fav-buttons\">" + buttons +
      "</div></li>";
  }

  var CLOSE_ICON = "<svg class=\"icon\" viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M6 6l12 12M18 6L6 18\"/></svg>";

  function renderFavDialog() {
    var list = readFavorites();
    var canSave = !!selectedSquare();
    var message = state.favMessage ? "<p class=\"callout" + (state.favMessage.error ? " callout-error" : "") +
      "\" role=\"status\">" + esc(state.favMessage.text) + "</p>" : "";
    els.favDialog.innerHTML = "<div class=\"drawer-inner\"><div class=\"drawer-head\">" +
      "<h2 id=\"fav-heading\" tabindex=\"-1\">" + t("fav_heading") + "</h2>" +
      "<button type=\"button\" class=\"btn btn-dark phone-only\" data-close>" + t("back_to_map") + "</button>" +
      "<button type=\"button\" class=\"btn btn-dark btn-icon desktop-only\" data-close aria-label=\"" + t("close") +
      "\" title=\"" + t("close") + "\">" + CLOSE_ICON + "</button></div>" +
      "<p class=\"drawer-note\">" + t("fav_explain") + "</p>" +
      "<div class=\"drawer-body\">" + message +
      (list.length ? "<ul class=\"fav-list\">" + list.map(favItemHtml).join("") + "</ul>" :
        "<p class=\"callout\">" + t("fav_empty") + "</p>") + "</div>" +
      "<div class=\"drawer-foot\"><button type=\"button\" class=\"btn btn-primary\" data-fav-save" +
      (canSave ? "" : " disabled") + ">" + t("fav_save_selected") + "</button>" +
      (canSave ? "" : "<p>" + t("fav_select_first") + "</p>") + "</div></div>";
  }

  function onFavClick(event) {
    if (event.target.closest("[data-close]")) {
      els.favDialog.close();
      return;
    }
    if (event.target.closest("[data-fav-save]")) {
      els.favDialog.close();
      openSaveDialog();
      return;
    }
    var button = event.target.closest("[data-fav-act]");
    if (!button) {
      return;
    }
    var id = button.closest("[data-fav]").getAttribute("data-fav");
    var act = button.getAttribute("data-fav-act");
    if (act === "open") {
      openFavorite(id);
    } else if (act === "edit" || act === "remove") {
      state.favEdit = { id: id, mode: act };
      renderFavDialog();
      var item = "[data-fav=\"" + id + "\"] ";
      els.favDialog.querySelector(act === "remove" ? item + "[data-fav-act=\"cancel\"]" : item + "[data-field]").focus();
    } else if (act === "cancel") {
      state.favEdit = null;
      renderFavDialog();
      focusFavButton(id);
    } else {
      changeFavorite(id, act);
    }
  }

  function focusFavButton(id, act) {
    var target = els.favDialog.querySelector("[data-fav=\"" + id + "\"] [data-fav-act=\"" + (act || "open") + "\"]");
    if (target) {
      target.focus();
    }
  }

  function changeFavorite(id, act) {
    var list = readFavorites();
    var index = list.map(function (item) { return item.id; }).indexOf(id);
    var item = list[index];
    var message;
    if (act === "confirm-remove") {
      list.splice(index, 1);
      message = t("fav_removed", { name: item.name });
    } else {
      var name = els.favDialog.querySelector("[data-field=\"name\"]").value.trim();
      if (!name) {
        return;
      }
      item.name = name;
      item.colour = els.favDialog.querySelector("[data-field=\"colour\"]").value;
      message = t("fav_updated", { name: name });
    }
    state.favEdit = null;
    var saved = writeFavorites(list);
    state.favMessage = saved ? { text: message, error: false } : { text: t("unsaved"), error: true };
    renderFavDialog();
    renderFavCount();
    say(state.favMessage.text);
    if (act === "confirm-remove" && saved) {
      $("fav-heading").focus();
    } else {
      focusFavButton(id, "edit");
    }
  }

  function openFavorite(id) {
    var item = readFavorites().filter(function (entry) { return entry.id === id; })[0];
    var square = squaresById[item.square_id];
    els.favDialog.close();
    state.favEdit = null;
    flyTo(L.latLng(item.lat, item.lon));
    selectSquare(square, { focus: true });
    toast(t("fav_opened", { name: item.name }));
  }

  var saveStatus = null;

  function renderSaveDialog(name, colour) {
    var square = selectedSquare();
    var point = pointOf(square);
    var failure = saveStatus === "failed" ?
      "<div class=\"callout callout-error\" role=\"alert\"><strong>" + t("unsaved") + "</strong>" +
      t("unsaved_help") + "</div>" : "";
    var radios = COLOURS.map(function (item) {
      return "<label class=\"choice\"><input type=\"radio\" name=\"fav-colour\" value=\"" + item.id + "\"" +
        (item.id === colour ? " checked" : "") + ">" + colourDot(item.id) + "<span>" + colourName(item.id) +
        "</span></label>";
    }).join("");
    els.saveDialog.innerHTML = "<form class=\"modal-inner\" id=\"save-form\">" +
      modalHead("save-heading", t("fav_save_heading")) + failure +
      "<p>" + placeName(square) + ", " + t("point_value", { lat: point.lat.toFixed(4), lon: point.lon.toFixed(4) }) +
      "</p><div class=\"field\"><label for=\"fav-name\">" + t("fav_name") + "</label>" +
      "<input type=\"text\" id=\"fav-name\" name=\"name\" required value=\"" + esc(name) + "\"></div>" +
      "<fieldset><legend>" + t("fav_colour") + "</legend><div class=\"colour-grid\">" + radios + "</div></fieldset>" +
      "<p class=\"muted\">" + t("fav_explain") + "</p>" +
      "<div class=\"modal-actions\"><button type=\"submit\" class=\"btn btn-primary\">" + t("save") + "</button>" +
      "<button type=\"button\" class=\"btn btn-secondary\" data-close>" + t("cancel") + "</button></div></form>";
  }

  function currentSaveValues() {
    var form = $("save-form");
    if (!form) {
      return { name: t("fav_default_name"), colour: "green" };
    }
    return { name: form.elements.name.value, colour: form.elements["fav-colour"].value || "green" };
  }

  function openSaveDialog() {
    saveStatus = null;
    renderSaveDialog(t("fav_default_name"), "green");
    openDialog(els.saveDialog, "[data-act=\"save\"]");
  }

  function submitSave(event) {
    event.preventDefault();
    var values = currentSaveValues();
    var square = selectedSquare();
    var point = pointOf(square);
    var list = readFavorites();
    list.push({
      id: Date.now().toString(36), name: values.name.trim(), colour: values.colour, square_id: square.id,
      lat: point.lat, lon: point.lon
    });
    if (!writeFavorites(list)) {
      saveStatus = "failed";
      renderSaveDialog(values.name, values.colour);
      $("save-heading").focus();
      return;
    }
    saveStatus = null;
    els.saveDialog.close();
    renderFavCount();
    toast(t("fav_saved", { name: values.name.trim() }));
    say(t("fav_saved", { name: values.name.trim() }));
  }

  // ---------- Navigation ----------

  function renderNavDialog() {
    var square = selectedSquare() || squaresById[ABETONE_ID];
    var point = pointOf(square);
    var pair = point.lat.toFixed(4) + "," + point.lon.toFixed(4);
    var links = [
      ["https://www.google.com/maps/dir/?api=1&destination=" + pair, t("nav_google")],
      ["https://maps.apple.com/?daddr=" + pair, t("nav_apple")],
      ["geo:" + pair + "?q=" + pair, t("nav_geo")]
    ].map(function (link) {
      return "<a class=\"btn btn-secondary\" href=\"" + link[0] + "\" target=\"_blank\" rel=\"noopener\">" +
        link[1] + "</a>";
    }).join("");
    els.navDialog.innerHTML = "<div class=\"modal-inner\">" + modalHead("nav-heading", t("nav_heading")) +
      "<p class=\"notice-sample\">" + t("nav_sim") + "</p>" +
      "<p>" + t("nav_text", { lat: point.lat.toFixed(4), lon: point.lon.toFixed(4) }) + "</p>" +
      "<div class=\"nav-links\">" + links + "</div></div>";
  }

  function openNavDialog() {
    renderNavDialog();
    openDialog(els.navDialog, "[data-act=\"nav\"]");
  }

  // Details are re-rendered while a dialog is open, so the opener is found again by selector on close.
  function openDialog(dialog, openerSelector) {
    dialog.dataset.opener = openerSelector;
    dialog.showModal();
  }

  function restoreFocusAfterClose(event) {
    var selector = event.target.dataset.opener;
    window.requestAnimationFrame(function () {
      var active = document.activeElement;
      if (selector && (!active || active === document.body)) {
        var opener = document.querySelector(selector);
        if (opener) {
          opener.focus();
        }
      }
    });
  }

  // ---------- Static text and language ----------

  function applyStaticText() {
    document.documentElement.lang = state.lang;
    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      var key = el.getAttribute("data-i18n");
      el.textContent = t(key);
    });
    document.querySelectorAll("[data-i18n-aria]").forEach(function (el) {
      el.setAttribute("aria-label", t(el.getAttribute("data-i18n-aria")));
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach(function (el) {
      el.setAttribute("placeholder", t(el.getAttribute("data-i18n-placeholder")));
    });
    document.querySelectorAll(".lang button").forEach(function (button) {
      button.setAttribute("aria-pressed", String(button.getAttribute("data-lang") === state.lang));
    });
    document.querySelectorAll("[data-i18n-html]").forEach(function (el) {
      el.innerHTML = t(el.getAttribute("data-i18n-html"));
    });
    els.zoomIn.title = els.zoomIn.ariaLabel = t("zoom_in");
    els.zoomOut.title = els.zoomOut.ariaLabel = t("zoom_out");
    document.title = "SporaMeteo";
  }

  function renderAll() {
    applyStaticText();
    renderDates();
    renderLegend();
    renderLayers();
    applyFold();
    renderMessages();
    renderDetails();
    renderFavCount();
    placePositionMarker();
    if (els.favDialog.open) {
      renderFavDialog();
    }
    if (els.saveDialog.open) {
      var values = currentSaveValues();
      renderSaveDialog(values.name, values.colour);
    }
    if (els.navDialog.open) {
      renderNavDialog();
    }
    if (!els.searchResults.hidden) {
      renderSearchResults();
    }
  }

  function setLanguage(lang) {
    state.lang = lang;
    messageSignature = "";
    var active = document.activeElement;
    renderAll();
    drawDecor();
    if (active && active.getAttribute && active.getAttribute("data-lang")) {
      active.focus();
    }
  }

  // ---------- Events ----------

  function bindEvents() {
    map.on("click", function (event) {
      if (!mode.detail || !state.overlayOn) {
        return;
      }
      var square = findSquareAt(event.latlng);
      if (square) {
        selectSquare(square);
      }
    });
    map.on("moveend zoomend resize", refreshMapMode);
    // The percentages sit on their own canvas, so they follow the map by redrawing.
    map.on("move zoomend viewreset resize", scheduleDecor);
    document.querySelectorAll("[data-fold]").forEach(function (button) {
      button.addEventListener("click", function () {
        var name = button.getAttribute("data-fold");
        state.folded[name] = !state.folded[name];
        applyFold();
      });
    });
    els.legendBody.addEventListener("click", function (event) {
      if (event.target.closest("[data-lg-toggle]")) {
        state.legendMore = !state.legendMore;
        renderLegend();
        els.legendBody.querySelector("[data-lg-toggle]").focus();
      }
    });
    els.zoomIn.addEventListener("click", function () { map.zoomIn(); });
    els.zoomOut.addEventListener("click", function () { map.zoomOut(); });

    els.centreBtn.addEventListener("click", function () {
      var square = findSquareAt(map.getCenter());
      if (square) {
        selectSquare(square, { focus: true });
      } else {
        toast(t("no_square_centre"));
        say(t("no_square_centre"));
      }
    });

    els.dates.addEventListener("click", function (event) {
      var button = event.target.closest("[data-i]");
      if (button) {
        setDate(Number(button.getAttribute("data-i")));
      }
    });
    els.details.addEventListener("click", onDetailsClick);
    els.mapmsgs.addEventListener("click", function (event) {
      var button = event.target.closest("[data-act]");
      if (!button) {
        return;
      }
      if (button.getAttribute("data-act") === "retry") {
        retry();
      } else {
        els.searchInput.focus();
      }
    });

    document.querySelectorAll(".lang button").forEach(function (button) {
      button.addEventListener("click", function () { setLanguage(button.getAttribute("data-lang")); });
    });

    els.searchInput.addEventListener("input", renderSearchResults);
    els.searchInput.addEventListener("keydown", function (event) {
      var first = els.searchResults.querySelector(".result");
      if (event.key === "ArrowDown" && first) {
        event.preventDefault();
        first.focus();
      }
    });
    els.searchForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var matches = matchPlaces(els.searchInput.value);
      if (matches.length) {
        choosePlace(matches[0].key);
      } else {
        renderSearchResults();
      }
    });
    els.searchResults.addEventListener("click", function (event) {
      var button = event.target.closest("[data-place]");
      if (button) {
        choosePlace(button.getAttribute("data-place"));
        els.searchInput.focus();
      }
    });
    document.addEventListener("click", function (event) {
      if (!event.target.closest("#search-form")) {
        els.searchResults.hidden = true;
      }
    });
    $("location-btn").addEventListener("click", useLocation);

    document.querySelectorAll("input[name=\"background\"]").forEach(function (input) {
      input.addEventListener("change", function () {
        state.background = input.value;
        applyBackground();
      });
    });
    els.overlayToggle.addEventListener("click", function () {
      state.overlayOn = !state.overlayOn;
      renderLayers();
      applyOverlayVisibility();
    });
    els.opacity.addEventListener("input", function () {
      state.opacity = Number(els.opacity.value);
      els.opacityValue.textContent = state.opacity + "%";
      forestLayer.setOpacity(forestOpacity());
      restyleSquares();
    });
    els.layersBtn.addEventListener("click", function () { togglePanel("layers"); });
    els.legendBtn.addEventListener("click", function () { togglePanel("legend"); });
    document.querySelectorAll("[data-close-panel]").forEach(function (button) {
      button.addEventListener("click", function () { setPanel(null, true); });
    });

    els.favBtn.addEventListener("click", function () {
      state.favEdit = null;
      state.favMessage = null;
      renderFavDialog();
      openDialog(els.favDialog, "#fav-btn");
    });
    els.favDialog.addEventListener("click", onFavClick);
    els.saveDialog.addEventListener("click", function (event) {
      if (event.target.closest("[data-close]")) {
        els.saveDialog.close();
      }
    });
    els.saveDialog.addEventListener("submit", submitSave);
    els.navDialog.addEventListener("click", function (event) {
      if (event.target.closest("[data-close]")) {
        els.navDialog.close();
      }
    });
    [els.favDialog, els.saveDialog, els.navDialog].forEach(function (dialog) {
      dialog.addEventListener("close", restoreFocusAfterClose);
    });

    document.addEventListener("keydown", function (event) {
      if (event.key !== "Escape") {
        return;
      }
      if (!els.searchResults.hidden) {
        els.searchResults.hidden = true;
        els.searchInput.focus();
      } else if (state.panel) {
        setPanel(null, true);
      } else if (state.detailsOpen && !document.querySelector("dialog[open]")) {
        closeDetails(false);
        document.getElementById("map").focus();
      }
    });

    new ResizeObserver(function () { map.invalidateSize({ animate: false }); })
      .observe(document.querySelector(".mapcell"));
    phoneQuery.addEventListener("change", function () {
      setPanel(null, false);
      scrollChipIntoView();
    });
  }

  // ---------- Start ----------

  function startView() {
    if (state.squareId) {
      var square = squaresById[state.squareId];
      var zoom = zoomForWidthKm(REP_POINT.lat, focusKm());
      map.setView(L.latLng(REP_POINT.lat, REP_POINT.lon), zoom, { animate: false });
      keepSquareVisible(square);
    } else {
      map.fitBounds([[35.4, 6.6], [47.2, 18.6]], { animate: false });
    }
  }

  function applyQueryPanels() {
    var panel = params.get("panel");
    if (panel === "layers" || panel === "legend") {
      setPanel(panel, false);
    } else if (panel === "favorites") {
      els.favBtn.click();
    } else if (panel === "save" && selectedSquare()) {
      openSaveDialog();
    } else if (panel === "nav" && selectedSquare()) {
      openNavDialog();
    }
  }

  function start() {
    applyBackground();
    renderAll();
    map.invalidateSize({ animate: false });
    startView();
    forestLayer.setOpacity(forestOpacity());
    mode.detail = null;
    refreshMapMode();
    els.progress.hidden = !isLoading();
    bindEvents();
    if (scenario === "no_results") {
      els.searchInput.value = "Zeta";
      renderSearchResults();
    }
    if (state.squareId) {
      announceSelection();
    }
    if (scenario === "storage_unavailable") {
      saveStatus = "failed";
      renderSaveDialog(t("fav_default_name"), "green");
      openDialog(els.saveDialog, "[data-act=\"save\"]");
    }
    applyQueryPanels();
  }

  start();
}());
