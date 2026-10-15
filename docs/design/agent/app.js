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
    favMessage: null
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
  var SQUARE_BORDER = cssVar("--square-border");
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
    worldCopyJump: false
  });
  L.control.attribution({ position: "bottomleft", prefix: false })
    .addAttribution("&copy; <a href=\"https://www.openstreetmap.org/copyright\">OpenStreetMap</a> contributors")
    .addTo(map);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19 }).addTo(map);

  var canvas = L.canvas({ padding: 0.3 });
  var HATCH = hatchPattern();
  var forestLayer = L.imageOverlay(SAMPLE.national_forest.url, SAMPLE.national_forest.bounds, {
    interactive: false, opacity: 0.9
  });
  var haloLayer = L.rectangle([[0, 0], [0, 0]], {
    renderer: canvas, interactive: false, color: "#ffffff", weight: 8, fill: false
  });
  var outlineLayer = L.rectangle([[0, 0], [0, 0]], {
    renderer: canvas, interactive: false, color: cssVar("--lake"), weight: 4, fill: false
  });
  var positionMarker = null;
  var mode = { detail: null, near: null, km: 0 };

  squares.forEach(function (square) {
    square.layer = L.rectangle(square.bounds, { renderer: canvas, interactive: false, weight: 1 });
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
      stroke: true, weight: 1, color: SQUARE_BORDER, opacity: 1, dashArray: null,
      fill: true, fillColor: SCALE[0], fillOpacity: state.opacity / 100
    };
    if (data.no_estimate_reason === "missing_data") {
      return Object.assign(style, { color: GREY, dashArray: "5 3", fillColor: HATCH, fillOpacity: 0.95 });
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
      return;
    }
    haloLayer.setBounds(square.bounds);
    outlineLayer.setBounds(square.bounds);
    haloLayer.addTo(map).bringToFront();
    outlineLayer.addTo(map).bringToFront();
  }

  function forestOpacity() {
    return Math.min(1, (state.opacity / 100) * 1.5);
  }

  function refreshMapMode() {
    var km = mapWidthKm();
    var detail = km <= DETAIL_KM;
    var near = km <= LESS_FOREST_KM;
    var changed = detail !== mode.detail || near !== mode.near;
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
  }

  function applyBackground() {
    var container = map.getContainer();
    container.classList.toggle("bg-light", state.background === "light");
    container.classList.toggle("bg-contrast", state.background === "contrast");
  }

  function flyTo(latlng, km) {
    var zoom = Math.min(map.getMaxZoom(), zoomForWidthKm(latlng.lat, km));
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
    var bar = "";
    if (square) {
      if (value !== null && !waiting) {
        pct = value + "%";
        bar = "<i style=\"width:" + value + "%;background:" + SCALE[Math.min(4, Math.floor(value / 20))] + "\"></i>";
      } else {
        pct = "<span aria-hidden=\"true\">-</span><span class=\"sr-only\">" + t("estimate_unavailable") + "</span>";
      }
    }
    var date = dateAt(index);
    var today = index === 0;
    var weekday = today ? t("today") : capitalise(format(date, { weekday: "short" }).replace(".", ""));
    var dayMonth = format(date, { day: "numeric", month: "short" }).replace(".", "");
    return "<li><button type=\"button\" class=\"date-btn\" data-i=\"" + index + "\" aria-pressed=\"" +
      (index === state.dateIdx) + "\">" +
      "<span class=\"d-short\"><b>" + esc(weekday) + "</b><span>" + esc(dayMonth) + "</span></span>" +
      "<span class=\"d-long\">" + esc(longDate(index)) +
      (today ? "<span class=\"d-today\">" + t("today") + "</span>" : "") + "</span>" +
      "<span class=\"d-pct\">" + pct + "</span><span class=\"d-bar\" aria-hidden=\"true\">" + bar + "</span>" +
      "</button></li>";
  }

  function renderDates() {
    keepFocus(els.dates, function () {
      els.dates.innerHTML = SAMPLE.dates.map(function (_, index) { return dateButton(index); }).join("");
    });
    els.dateHint.hidden = !!selectedSquare();
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

  function noticeExperimental() {
    return "<p class=\"notice-experimental\"><strong>" + t("note_label") + "</strong> " + t("note_text") + "</p>";
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
      html += "<div class=\"pct-row\"><span class=\"pct\">" + pct + "%</span>" +
        sizeButton() + caption + "</div>" + noticeExperimental();
    } else if (kind === "waiting") {
      html += "<div class=\"callout callout-wait\"><span class=\"spinner\" aria-hidden=\"true\"></span><span>" +
        t("waiting") + "</span></div><div class=\"sizerow\">" + sizeButton() + "</div>";
    } else {
      var message = kind === "missing" ? t("no_estimate") : t("less_forest");
      html += "<div class=\"callout\"><strong>" + message + "</strong>" +
        (kind === "missing" ? t("no_estimate_help") : "") + "<br>" +
        "<button type=\"button\" class=\"btn btn-primary\" data-act=\"pick\">" + t("pick_another") + "</button>" +
        (kind === "missing" ? "<button type=\"button\" class=\"btn btn-secondary\" data-act=\"retry\">" +
          t("retry") + "</button>" : "") + "</div><div class=\"sizerow\">" + sizeButton() + "</div>";
    }
    return html;
  }

  function kvRow(label, value) {
    return "<div class=\"kv\"><dt>" + label + "</dt><dd>" + value + "</dd></div>";
  }

  function weatherHtml() {
    var date = format(dateAt(state.shownIdx), { day: "numeric", month: "long" });
    return "<section class=\"d-sec\"><h3>" + t("weather_heading", { date: date }) + "</h3><dl>" +
      kvRow(t("temperature"), "13°C") + kvRow(t("minimum"), "8°C") +
      kvRow(t("drying"), t("drying_low")) + kvRow(t("frost"), t("frost_none")) +
      "</dl><p class=\"muted\">" + t("hail_missing") + "</p></section>";
  }

  function rainHtml() {
    var rows = RAIN_TOTALS.map(function (pair) {
      return kvRow(t("rain_row", { n: pair[0], range: rainRange(pair[0]) }), pair[1] + " mm");
    }).join("");
    var end = assessmentDate();
    end.setUTCDate(end.getUTCDate() - 1);
    var until = toWord(end, true);
    return "<section class=\"d-sec\"><h3>" + t("rain_heading") + "</h3><dl>" + rows + "</dl><p class=\"muted\">" +
      t("rain_note", { until: until }) + "</p></section>";
  }

  function moreHtml(square, kind) {
    var data = effective(square);
    var point = pointOf(square);
    var withValues = kind === "estimate";
    var html = "<div class=\"d-actions\">" +
      "<button type=\"button\" class=\"btn btn-primary\" data-act=\"save\">" + t("save_favorite") + "</button>" +
      "<button type=\"button\" class=\"btn btn-secondary\" data-act=\"nav\">" + t("open_navigation") + "</button>" +
      "</div>";
    html += "<p class=\"notice-sample d-sample\"><strong>" + t("design_label") + "</strong> " + t("design_text") + "</p>";
    if (withValues) {
      html += "<section class=\"d-sec\"><h3>" + t("facts_heading") + "</h3><p>" +
        t("facts_text", { forest: forestText(data.forest_share) }) + "</p></section>";
      html += weatherHtml() + rainHtml();
    }
    html += "<section class=\"d-sec\"><h3>" + t("forest_heading") + "</h3><p><strong>" + data.forest_share +
      "%</strong></p><div class=\"forest-bar\" aria-hidden=\"true\"><i style=\"width:" + data.forest_share +
      "%\"></i></div></section>";
    html += "<section class=\"d-sec\"><h3>" + t("area_heading") + "</h3><p>" + t("area_text") + "</p></section>";
    html += "<section class=\"d-sec\"><h3>" + t("point_heading") + "</h3><p><strong>" +
      t("point_value", { lat: point.lat.toFixed(4), lon: point.lon.toFixed(4) }) + "</strong></p>" +
      "<p class=\"muted\">" + t("point_label") + "</p></section>";
    html += "<section class=\"d-sec sources\"><h3>" + t("sources_heading") + "</h3><ul><li>" + t("src_forest") +
      "</li><li>" + t("src_weather") + "</li><li>" + t("src_osm") + "</li></ul><p class=\"muted\">" +
      t("src_dates") + "</p></section>";
    html += "<section class=\"d-sec\"><h3>" + t("update_heading") + "</h3><dl>" +
      kvRow(t("target_day"), dayMonthYear(dateAt(state.shownIdx))) +
      kvRow(t("assessment"), dayMonthYear(assessmentDate())) +
      kvRow(t("updated"), updateText()) + "</dl></section>";
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
      els.details.innerHTML =
        "<div class=\"d-top\"><div><h2 id=\"details-heading\" tabindex=\"-1\">" + placeName(square) + "</h2>" +
        "<p class=\"d-date\">" + fullDate(state.shownIdx) + "</p></div>" +
        "<button type=\"button\" class=\"btn btn-secondary phone-only\" data-act=\"close\">" + t("back_to_map") +
        "</button><button type=\"button\" class=\"btn btn-secondary desktop-only\" data-act=\"close\">" +
        t("close_details") + "</button></div>" +
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
    els.legendBody.innerHTML =
      "<div class=\"legend-group\"><p class=\"legend-title\">" + t("legend_scale") + "</p>" + scale + "</div>" +
      "<div class=\"legend-group\"><p class=\"legend-title\">" + t("legend_other") + "</p>" +
      legendRow("sw-missing", "", t("legend_missing")) + legendRow("sw-less", "", t("legend_less_forest")) +
      legendRow("sw-selected", "", t("legend_selected")) + "</div>" +
      "<div class=\"legend-group\">" + legendRow("sw-forest", "", t("legend_forest")) + "</div>" +
      "<p class=\"legend-note\">" + t("legend_note") + "</p>";
  }

  function renderLayers() {
    els.overlayToggle.textContent = t(state.overlayOn ? "hide_overlay" : "show_overlay");
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
    flyTo(L.latLng(REP_POINT.lat, REP_POINT.lon), 6);
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
    flyTo(state.position, 6);
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

  function favItemHtml(item) {
    var editing = state.favEdit && state.favEdit.id === item.id ? state.favEdit.mode : null;
    var id = esc(item.id);
    var body = "<div class=\"fav-name\">" + esc(item.name) + "</div>" +
      "<div class=\"fav-colour\">" + colourDot(item.colour) + "<span>" + colourName(item.colour) + "</span></div>";
    var buttons = "";
    if (editing === "rename") {
      body = "<div class=\"field\"><label for=\"rename-" + id + "\">" + t("fav_name") + "</label>" +
        "<input type=\"text\" id=\"rename-" + id + "\" value=\"" + esc(item.name) + "\" data-field=\"name\"></div>";
      buttons = editButtons("apply");
    } else if (editing === "colour") {
      body += "<div class=\"field\"><label for=\"colour-" + id + "\">" + t("fav_colour") + "</label>" +
        "<select id=\"colour-" + id + "\" data-field=\"colour\">" + COLOURS.map(function (colour) {
          return "<option value=\"" + colour.id + "\"" + (colour.id === item.colour ? " selected" : "") + ">" +
            colourName(colour.id) + "</option>";
        }).join("") + "</select></div>";
      buttons = editButtons("apply");
    } else if (editing === "remove") {
      body += "<p><strong>" + t("remove_confirm", { name: esc(item.name) }) + "</strong></p>";
      buttons = "<button type=\"button\" class=\"btn btn-danger\" data-fav-act=\"confirm-remove\">" + t("remove") +
        "</button><button type=\"button\" class=\"btn btn-secondary\" data-fav-act=\"cancel\">" + t("keep") + "</button>";
    } else {
      var label = " aria-label=\"%s: " + esc(item.name) + "\"";
      buttons = [["open", "open", "btn-primary"], ["rename", "rename", "btn-secondary"],
        ["colour", "change_colour", "btn-secondary"], ["remove", "remove", "btn-secondary"]].map(function (spec) {
        return "<button type=\"button\" class=\"btn " + spec[2] + "\" data-fav-act=\"" + spec[0] + "\"" +
          label.replace("%s", t(spec[1])) + ">" + t(spec[1]) + "</button>";
      }).join("");
    }
    var place = squaresById[item.square_id] ? placeName(squaresById[item.square_id]) : "";
    return "<li class=\"fav-item\" data-fav=\"" + id + "\">" + body +
      (editing ? "" : "<div class=\"muted\">" + place + "</div>") + "<div class=\"fav-buttons\">" + buttons +
      "</div></li>";
  }

  function editButtons(act) {
    return "<button type=\"button\" class=\"btn btn-primary\" data-fav-act=\"" + act + "\">" + t("save") +
      "</button><button type=\"button\" class=\"btn btn-secondary\" data-fav-act=\"cancel\">" + t("cancel") + "</button>";
  }

  function renderFavDialog() {
    var list = readFavorites();
    var message = state.favMessage ? "<p class=\"callout" + (state.favMessage.error ? " callout-error" : "") +
      "\" role=\"status\">" + esc(state.favMessage.text) + "</p>" : "";
    els.favDialog.innerHTML = "<div class=\"modal-inner\">" + modalHead("fav-heading", t("fav_heading")) +
      "<p>" + t("fav_explain") + "</p>" + message +
      (list.length ? "<ul class=\"fav-list\">" + list.map(favItemHtml).join("") + "</ul>" :
        "<p class=\"callout fav-list\">" + t("fav_empty") + "</p>") + "</div>";
  }

  function onFavClick(event) {
    if (event.target.closest("[data-close]")) {
      els.favDialog.close();
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
    } else if (act === "rename" || act === "colour" || act === "remove") {
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
    var mode = state.favEdit.mode;
    var message;
    if (act === "confirm-remove") {
      list.splice(index, 1);
      message = t("fav_removed", { name: item.name });
    } else if (mode === "rename") {
      var name = els.favDialog.querySelector("[data-field=\"name\"]").value.trim();
      if (!name) {
        return;
      }
      item.name = name;
      message = t("fav_renamed", { name: name });
    } else {
      item.colour = els.favDialog.querySelector("[data-field=\"colour\"]").value;
      message = t("fav_recoloured", { name: item.name, colour: colourName(item.colour) });
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
      focusFavButton(id, mode === "colour" ? "colour" : "rename");
    }
  }

  function openFavorite(id) {
    var item = readFavorites().filter(function (entry) { return entry.id === id; })[0];
    var square = squaresById[item.square_id];
    els.favDialog.close();
    state.favEdit = null;
    flyTo(L.latLng(item.lat, item.lon), 6);
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
    var zoomIn = document.querySelector(".leaflet-control-zoom-in");
    var zoomOut = document.querySelector(".leaflet-control-zoom-out");
    if (zoomIn) {
      zoomIn.title = zoomIn.ariaLabel = t("zoom_in");
      zoomOut.title = zoomOut.ariaLabel = t("zoom_out");
    }
    document.title = "SporaMeteo";
  }

  function renderAll() {
    applyStaticText();
    renderDates();
    renderLegend();
    renderLayers();
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
      var zoom = zoomForWidthKm(REP_POINT.lat, 6);
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
