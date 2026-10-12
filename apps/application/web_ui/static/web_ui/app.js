(() => {
  "use strict";

  const root = document.querySelector("[data-map-app]");
  const languageButtons = [...document.querySelectorAll("button[data-language]")];
  const locale = () => document.documentElement.lang === "it" ? "it-IT" : "en-GB";
  let liveMapController = null;

  function date(value) {
    return new Intl.DateTimeFormat(locale(), {
      day: "numeric",
      month: "long",
      year: "numeric",
      timeZone: "Europe/Rome",
    }).format(new Date(`${value}T12:00:00Z`));
  }

  function number(value) {
    return new Intl.NumberFormat(locale(), {
      maximumFractionDigits: 1,
      minimumFractionDigits: 1,
    }).format(value);
  }

  function measurement(value, unit) {
    return `${number(value)} ${unit}`;
  }

  function fullDate(value) {
    const display = new Intl.DateTimeFormat(locale(), {
      weekday: "long", day: "numeric", month: "long", year: "numeric",
      timeZone: "Europe/Rome",
    }).format(new Date(`${value}T12:00:00Z`));
    return display.charAt(0).toLocaleUpperCase(locale()) + display.slice(1);
  }

  function dateTime(value) {
    if (!value) return "";
    return new Intl.DateTimeFormat(locale(), {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: "Europe/Rome",
    }).format(new Date(value));
  }

  function compactDateRange(values, formatter) {
    if (!values.length) return "";
    const first = formatter(values[0]);
    const last = formatter(values[values.length - 1]);
    return first === last ? first : `${first} - ${last}`;
  }

  window.MicometeoFormatting = {
    formatDate: date,
    formatNumber: number,
    formatMeasurement: measurement,
  };

  function setLanguage(language) {
    if (!/^(it|en)$/.test(language)) return;
    document.cookie = `micometeo_language=${language};path=/;max-age=31536000;samesite=lax`;
    const next = new URL(window.location.href);
    next.searchParams.delete("lang");
    window.location.assign(next);
  }

  languageButtons.forEach((button) => button.addEventListener("click", () => setLanguage(button.dataset.language)));
  if (!root) return;
  const labels = JSON.parse(document.getElementById("ui-labels")?.textContent || "{}");

  function updateDateMetadata(features, loading = false, info = null) {
    const assessment = document.querySelector(".date-assess");
    const calculated = document.querySelector("[data-date-update]");
    const warning = document.querySelector("[data-date-warning]");
    if (!assessment || !calculated) return;
    if (loading) {
      assessment.textContent = `${labels.assessment}: ${labels.map_loading || labels.loading}`;
      calculated.hidden = true;
      calculated.textContent = "";
      if (warning) {
        warning.hidden = true;
        warning.textContent = "";
      }
      return;
    }
    const values = Array.isArray(features) ? features : [];
    const records = values
      .map((feature) => ({
        assessment: feature.properties?.assessment_date,
        calculated: feature.properties?.calculated_at,
        target: feature.properties?.target_date,
      }))
      .filter((record) => record.assessment || record.calculated);
    const assessmentDates = [...new Set(records.map((record) => record.assessment).filter(Boolean))].sort();
    assessment.textContent = assessmentDates.length
      ? `${labels.assessment}: ${compactDateRange(assessmentDates, date)}${assessmentDates.length > 1 ? ` (${labels.map_mixed_assessment})` : ""}`
      : `${labels.assessment}: -`;
    const calculatedAt = [...new Set(records.map((record) => record.calculated).filter(Boolean))].sort();
    calculated.hidden = !calculatedAt.length;
    calculated.textContent = calculatedAt.length
      ? `${labels.map_calculated_at}: ${compactDateRange(calculatedAt, dateTime)}`
      : "";
    if (warning) {
      const today = info?.today || root.dataset.assessmentDate;
      const olderRecords = records.filter((record) => today && record.assessment && record.assessment < today);
      const olderDates = [...new Set(olderRecords.map((record) => record.assessment).filter(Boolean))].sort();
      const olderCalculatedAt = [...new Set(olderRecords.map((record) => record.calculated).filter(Boolean))].sort();
      warning.hidden = !olderDates.length || !olderCalculatedAt.length;
      warning.textContent = olderDates.length && olderCalculatedAt.length
        ? (labels.map_older_warning || "").replace("{target}", olderRecords.map((record) => record.target).find(Boolean) || state.date)
          .replace("{assessment}", compactDateRange(olderDates, date))
          .replace("{calculated}", compactDateRange(olderCalculatedAt, dateTime))
        : "";
    }
  }

  const params = new URLSearchParams(window.location.search);
  const state = {
    square: params.get("square") || root.dataset.selectedSquare || "",
    date: root.dataset.targetDate || params.get("date") || "",
    resultId: params.get("result") || root.dataset.resultId || "",
    assessment: root.dataset.assessmentDate || params.get("assessment") || "",
    updateId: params.get("update") || root.dataset.updateId || "",
    center: params.get("center") || root.dataset.mapCenter || "",
    zoom: Number(params.get("zoom") || root.dataset.mapZoom || "11"),
    panel: params.get("panel") || "",
    details: params.has("details") ? params.get("details") === "true" : root.dataset.detailsOpen === "true",
    sheetHeight: params.get("sheet") || "short",
    background: params.get("background") || "light",
    overlay: params.get("overlay") !== "false",
    opacity: Number(params.get("opacity") || "60"),
    foldedLayers: params.get("foldedLayers") === "true",
    foldedLegend: params.get("foldedLegend") === "true",
    legendMore: params.get("legendMore") === "true",
  };
  if (!["short", "half", "tall"].includes(state.sheetHeight)) state.sheetHeight = "short";
  if (!["light", "contrast"].includes(state.background)) state.background = "light";
  state.opacity = Number.isFinite(state.opacity) ? Math.min(100, Math.max(0, state.opacity)) : 60;
  state.zoom = Number.isFinite(state.zoom) ? Math.min(19, Math.max(1, state.zoom)) : 11;
  if (!["layers", "legend"].includes(state.panel)) state.panel = "";

  const toastTarget = document.querySelector("[data-toast]");
  let toastTimer;
  function toast(message) {
    if (!toastTarget) return;
    toastTarget.textContent = message;
    toastTarget.classList.add("is-visible");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => toastTarget.classList.remove("is-visible"), 2600);
  }

  function persistState() {
    root.classList.toggle("has-overlay", state.details || Boolean(state.panel));
    const next = new URL(window.location.href);
    const values = {
      square: state.square,
      date: state.date,
      result: state.resultId,
      assessment: state.assessment,
      update: state.updateId,
      center: state.center,
      zoom: String(state.zoom),
      panel: state.panel,
      details: String(state.details),
      sheet: state.sheetHeight,
      background: state.background,
      overlay: String(state.overlay),
      opacity: String(state.opacity),
      foldedLayers: String(state.foldedLayers),
      foldedLegend: String(state.foldedLegend),
      legendMore: String(state.legendMore),
    };
    Object.entries(values).forEach(([key, value]) => {
      if (value) next.searchParams.set(key, value);
      else next.searchParams.delete(key);
    });
    window.history.replaceState({}, "", next);
    Object.assign(root.dataset, {
      selectedSquare: state.square,
      targetDate: state.date,
      assessmentDate: state.assessment,
      updateId: state.updateId,
      resultId: state.resultId,
      mapCenter: state.center,
      mapZoom: String(state.zoom),
      detailsOpen: String(state.details),
      panel: state.panel,
    });
  }

  function setDate(button) {
    document.querySelectorAll(".date-btn").forEach((item) => {
      const selected = item === button;
      item.classList.toggle("is-selected", selected);
      item.setAttribute("aria-pressed", String(selected));
    });
    state.date = button.dataset.date || state.date;
    const displayedDate = document.querySelector(".date-big");
    if (displayedDate) displayedDate.textContent = fullDate(state.date);
    const estimateText = button.querySelector(".d-pct")?.textContent.trim() || "";
    const percentage = document.querySelector(".pct-badge .pct");
    if (percentage) {
      if (button.dataset.estimateState === "unavailable") percentage.textContent = "-";
      else if (estimateText) percentage.textContent = estimateText.endsWith("%") ? estimateText : `${estimateText}%`;
    }
    persistState();
    liveMapController?.setDate(state.date);
  }

  document.querySelectorAll(".date-btn").forEach((button) => button.addEventListener("click", () => setDate(button)));
  document.querySelectorAll("[data-zoom]").forEach((button) => button.addEventListener("click", () => {
    state.zoom = Math.min(19, Math.max(1, state.zoom + (button.dataset.zoom === "in" ? 1 : -1)));
    persistState();
    if (liveMapController) {
      liveMapController.zoom(button.dataset.zoom === "in" ? 1 : -1);
    } else {
      toast(labels.later_map);
    }
  }));

  function closePanel(name) {
    const panel = document.querySelector(`[data-fold-card="${name}"]`);
    if (!panel) return;
    panel.classList.remove("is-open");
    const trigger = document.querySelector(`[data-open-panel="${name}"]`);
    if (trigger) trigger.setAttribute("aria-expanded", "false");
    if (state.panel === name) state.panel = "";
    root.classList.remove("panel-open");
    document.querySelector("#main")?.classList.remove("panel-open");
    persistState();
    trigger?.focus();
  }

  document.querySelectorAll("[data-open-panel]").forEach((button) => button.addEventListener("click", () => {
    const name = button.dataset.openPanel;
    const panel = document.querySelector(`[data-fold-card="${name}"]`);
    if (!panel) return;
    const open = !panel.classList.contains("is-open");
    if (state.panel && state.panel !== name) closePanel(state.panel);
    panel.classList.toggle("is-open", open);
    button.setAttribute("aria-expanded", String(open));
    state.panel = open ? name : "";
    root.classList.toggle("panel-open", open);
    document.querySelector("#main")?.classList.toggle("panel-open", open);
    persistState();
    if (open) panel.querySelector("button")?.focus();
  }));
  document.querySelectorAll("[data-close-panel]").forEach((button) => button.addEventListener("click", () => closePanel(button.dataset.closePanel)));

  document.querySelectorAll("[data-fold]").forEach((button) => button.addEventListener("click", () => {
    const body = document.getElementById(`${button.dataset.fold}-body`);
    const card = document.querySelector(`[data-fold-card="${button.dataset.fold}"]`);
    if (!body || !card) return;
    const folded = body.hidden = !body.hidden;
    card.classList.toggle("is-folded", folded);
    button.setAttribute("aria-expanded", String(!folded));
    state[button.dataset.fold === "layers" ? "foldedLayers" : "foldedLegend"] = folded;
    persistState();
  }));

  const more = document.querySelector("[data-legend-more]");
  if (more) more.addEventListener("click", () => {
    const extra = document.querySelector(".lg-extra");
    if (!extra) return;
    extra.hidden = !extra.hidden;
    state.legendMore = !extra.hidden;
    more.textContent = extra.hidden ? labels.legend_more : labels.legend_less;
    more.setAttribute("aria-expanded", String(state.legendMore));
    persistState();
  });

  const overlay = document.querySelector("[data-overlay]");
  function setOverlay(value) {
    state.overlay = value;
    root.classList.toggle("overlay-off", !value);
    if (overlay) {
      overlay.setAttribute("aria-checked", String(value));
      overlay.classList.toggle("is-on", value);
    }
    persistState();
    liveMapController?.setOverlay(value);
  }
  if (overlay) {
    overlay.addEventListener("click", () => setOverlay(!state.overlay));
  }
  const opacity = document.querySelector("[data-opacity]");
  if (opacity) opacity.addEventListener("input", () => {
    state.opacity = Number(opacity.value);
    const output = document.querySelector("[data-opacity-value]");
    if (output) output.value = `${state.opacity}%`;
    root.style.setProperty("--overlay-opacity", String(state.opacity / 100));
    persistState();
    liveMapController?.setOpacity(state.opacity);
  });
  document.querySelectorAll("input[name=background]").forEach((input) => input.addEventListener("change", () => {
    state.background = input.value;
    root.classList.toggle("bg-contrast", state.background === "contrast");
    persistState();
    liveMapController?.setBackground(state.background);
  }));

  function setDetails(open) {
    const details = document.querySelector(".details[data-details]");
    if (!details) return;
    state.details = open;
    root.classList.toggle("details-open", open);
    document.querySelector("#main")?.classList.toggle("details-open", open);
    details.hidden = !open;
    document.querySelectorAll("[data-center-select]").forEach((button) => button.removeAttribute("hidden"));
    persistState();
    liveMapController?.resize();
    if (!open) document.getElementById("map")?.focus();
  }
  document.querySelectorAll("[data-close-details]").forEach((button) => button.addEventListener("click", () => setDetails(false)));
  const heightButton = document.querySelector("button[data-sheet-height]");
  if (heightButton) heightButton.addEventListener("click", () => {
    const details = document.querySelector(".details[data-details]");
    if (!details) return;
    const sizes = ["short", "half", "tall"];
    state.sheetHeight = sizes[(sizes.indexOf(state.sheetHeight) + 1) % sizes.length];
    details.dataset.sheetHeight = state.sheetHeight;
    details.dataset.size = state.sheetHeight;
    persistState();
    liveMapController?.resize();
  });

  document.querySelectorAll("[data-center-select]").forEach((button) => button.addEventListener("click", () => {
    if (button.closest("aside[data-details]")) {
      setDetails(false);
      if (!liveMapController?.centerSelection()) toast(labels.later_map);
    } else if (liveMapController?.centerSelection()) {
      return;
    } else if (root.dataset.fixture && document.querySelector("aside[data-details]")) {
      setDetails(true);
      document.getElementById("details-heading")?.focus();
    } else toast(labels.later_map);
  }));
  document.querySelector("[data-search-form]")?.addEventListener("submit", (event) => { event.preventDefault(); toast(labels.later_search); });
  document.querySelector("[data-location]")?.addEventListener("click", () => toast(labels.later_search));
  document.querySelector("[data-favourites]")?.addEventListener("click", () => toast(labels.later_favorites));
  document.querySelector("[data-save]")?.addEventListener("click", () => toast(labels.later_favorites));
  document.querySelector("[data-navigation]")?.addEventListener("click", () => toast(labels.later_navigation));
  document.querySelectorAll("[data-try-again]").forEach((button) => button.addEventListener("click", () => window.location.reload()));

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (state.panel) closePanel(state.panel);
    else if (state.details) setDetails(false);
  });

  const selectedDate = document.querySelector(`.date-btn[data-date="${CSS.escape(state.date)}"]`);
  if (selectedDate) {
    setDate(selectedDate);
    selectedDate.scrollIntoView({ block: "nearest", inline: "center" });
  }
  document.querySelectorAll("input[name=background]").forEach((input) => { input.checked = input.value === state.background; });
  root.classList.toggle("bg-contrast", state.background === "contrast");
  setOverlay(state.overlay);
  if (opacity) { opacity.value = String(state.opacity); opacity.dispatchEvent(new Event("input")); }
  const details = document.querySelector(".details[data-details]");
  if (details) {
    details.dataset.sheetHeight = state.sheetHeight;
    details.dataset.size = state.sheetHeight;
    details.hidden = !state.details;
    root.classList.toggle("details-open", state.details);
    document.querySelector("#main")?.classList.toggle("details-open", state.details);
  }
  for (const name of ["layers", "legend"]) {
    const folded = state[name === "layers" ? "foldedLayers" : "foldedLegend"];
    const body = document.getElementById(`${name}-body`);
    if (body) body.hidden = folded;
    document.querySelector(`[data-fold-card="${name}"]`)?.classList.toggle("is-folded", folded);
    document.querySelector(`[data-fold="${name}"]`)?.setAttribute("aria-expanded", String(!folded));
  }
  const extra = document.querySelector(".lg-extra");
  if (extra) extra.hidden = !state.legendMore;
  if (more) {
    more.textContent = state.legendMore ? labels.legend_less : labels.legend_more;
    more.setAttribute("aria-expanded", String(state.legendMore));
  }
  const panel = document.querySelector(`[data-fold-card="${state.panel}"]`);
  if (panel) {
    panel.classList.add("is-open");
    root.classList.add("panel-open");
    document.querySelector("#main")?.classList.add("panel-open");
    document.querySelector(`[data-open-panel="${state.panel}"]`)?.setAttribute("aria-expanded", "true");
  }
  persistState();

  function createLiveMapController() {
    if (root.dataset.fixture) return null;
    const container = document.querySelector("[data-map-container]");
    if (!container) return null;

    const EMPTY = { type: "FeatureCollection", features: [] };
    const styles = {
      light: "https://tiles.openfreemap.org/styles/liberty",
      contrast: "https://tiles.openfreemap.org/styles/positron",
    };
    const stateData = {
      info: null,
      forest: null,
      squares: null,
      selected: null,
      request: null,
      forestRequest: null,
      forestVisible: false,
      squaresRendered: false,
      pendingSelectionId: null,
      pendingSelectionUpdateId: null,
      pendingSelectionDetails: false,
      debounce: null,
      generation: 0,
      pendingPolls: 0,
      requestCount: 0,
      renderCount: 0,
      styleLoads: 0,
      ready: false,
      lastRequest: null,
      listenerCount: 0,
      dateTimer: null,
      lastView: null,
      movementInvalidated: false,
      moveFrame: null,
      moveStarts: 0,
      moveEnds: 0,
      invalidationCount: 0,
      resizeObserver: null,
      resizeWidth: 0,
      resizeHeight: 0,
      estimateRequest: null,
      estimateGeneration: 0,
      estimateCache: new Map(),
      estimateFeature: null,
      styleRequest: null,
      styleGeneration: 0,
      styleRestoreGeneration: -1,
      styleMessageId: null,
      initialising: false,
      backgroundKey: state.background,
    };

    const squareLayers = [
      "micometeo-square-estimates",
      "micometeo-square-missing",
      "micometeo-square-noforest",
      "micometeo-noforest-line",
      "micometeo-grid-lines",
      "micometeo-missing-line",
      "micometeo-selected",
      "micometeo-weather-area",
    ];

    function listen(event, listener, layer) {
      stateData.listenerCount += 1;
      if (layer) stateData.map.on(event, layer, listener);
      else stateData.map.on(event, listener);
    }

    function listenOnce(event, listener) {
      stateData.listenerCount += 1;
      stateData.map.once(event, listener);
    }

    let messageIdentity = 0;
    function message(text, kind = "wait", retry = false, retryAction = null, source = "map") {
      const identity = String(++messageIdentity);
      const target = document.querySelector("#mapmsgs");
      if (!target) return identity;
      target.replaceChildren();
      if (!text) return identity;
      const item = document.createElement("div");
      item.className = `msg msg-${kind}`;
      item.dataset.liveState = kind;
      item.dataset.liveMessageId = identity;
      item.dataset.liveMessageSource = source;
      const copy = document.createElement("span");
      copy.textContent = text;
      item.append(copy);
      if (retry) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn btn-secondary";
        button.textContent = labels.map_retry || labels.try_again;
        if (retryAction) button.addEventListener("click", retryAction);
        item.append(button);
      }
      target.append(item);
      return identity;
    }

    function currentMessage() {
      const item = document.querySelector("#mapmsgs > [data-live-message-id]");
      if (!item) return null;
      return {
        id: item.dataset.liveMessageId,
        source: item.dataset.liveMessageSource,
      };
    }

    if (!window.maplibregl) {
      message(labels.map_library_error, "error", true, () => window.location.reload());
      return null;
    }

    function parseCenter(value) {
      const values = String(value || "").split(",").map(Number);
      if (values.length !== 2 || values.some((part) => !Number.isFinite(part))) return null;
      const [lat, lon] = values;
      if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return null;
      return [lon, lat];
    }

    function emptySource(name) {
      return stateData.map?.getSource(name)?.setData(EMPTY);
    }

    function setSquareLayersVisible(visible, record = true) {
      const map = stateData.map;
      if (!map) return;
      if (record) stateData.squaresRendered = visible;
      const value = visible && state.overlay ? "visible" : "none";
      squareLayers.forEach((id) => {
        if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", value);
      });
    }

    function setForestVisible(visible, clearSource = false) {
      const map = stateData.map;
      const wasVisible = stateData.forestVisible;
      stateData.forestVisible = visible;
      if (!map) return;
      if (map.getLayer("micometeo-forest")) {
        map.setLayoutProperty("micometeo-forest", "visibility", visible && state.overlay ? "visible" : "none");
      }
      if (clearSource && wasVisible) emptySource("forest");
    }

    function clearVisibleSelection() {
      stateData.weatherLabel?.remove();
      stateData.weatherLabel = null;
      const hadSelection = Boolean(stateData.selected);
      stateData.selected = null;
      if (hadSelection) {
        emptySource("selected-square");
        emptySource("weather-area");
      }
      document.querySelector("aside[data-live-details]")?.remove();
      if (!root.dataset.fixture) document.querySelector("aside[data-details]:not([data-live-details])")?.remove();
      document.getElementById("centre-btn")?.setAttribute("hidden", "");
      const percentage = document.querySelector(".pct-badge .pct");
      if (percentage) percentage.textContent = "-";
      const unit = document.querySelector(".pct-badge .pct-unit");
      if (unit) unit.textContent = labels.estimate_unavailable;
    }

    function clearSquares() {
      const hadSquares = Boolean(stateData.squares);
      const keepSelection = state.details && stateData.selected?.properties?.target_date === state.date;
      if (!keepSelection) {
        updateDateMetadata([], true, stateData.info);
        stateData.estimateGeneration += 1;
        stateData.estimateRequest?.abort();
        stateData.estimateRequest = null;
        stateData.estimateFeature = null;
        clearDateEstimates();
      }
      if (state.square && !keepSelection) {
        stateData.pendingSelectionId = state.square;
        stateData.pendingSelectionUpdateId = state.updateId;
        stateData.pendingSelectionDetails = state.details;
        state.square = "";
        state.updateId = "";
        state.details = false;
        root.classList.remove("details-open");
        document.querySelector("#main")?.classList.remove("details-open");
        persistState();
      }
      stateData.squares = null;
      setSquareLayersVisible(false);
      if (!keepSelection) clearVisibleSelection();
      if (hadSquares) emptySource("squares");
      stateData.renderCount += 1;
    }

    function revealSquaresWhenRendered(generation) {
      const map = stateData.map;
      if (!map) return;
      const reveal = () => {
        if (generation !== stateData.generation || !stateData.squares) return;
        setSquareLayersVisible(true);
        document.getElementById("centre-btn")?.removeAttribute("hidden");
      };
      map.once("idle", reveal);
      map.triggerRepaint();
    }

    function renderDates(targetDates) {
      const buttons = [...document.querySelectorAll(".date-btn")];
      targetDates.forEach((value, index) => {
        const button = buttons[index];
        if (!button) return;
        const current = new Date(`${value}T12:00:00Z`);
        button.dataset.date = value;
        button.querySelector(".d-wd").textContent = index === 0 ? labels.today : new Intl.DateTimeFormat(locale(), { weekday: "short", timeZone: "Europe/Rome" }).format(current);
        button.querySelector(".d-dm").textContent = new Intl.DateTimeFormat(locale(), { day: "numeric", month: "short", timeZone: "Europe/Rome" }).format(current);
        button.querySelector(".d-pct").textContent = "";
      });
      clearDateEstimates();
      buttons.slice(targetDates.length).forEach((button) => button.closest("li")?.remove());
      const selected = document.querySelector(`.date-btn[data-date="${CSS.escape(state.date)}"]`) || buttons[0];
      if (selected) setDate(selected);
    }

    function clearDateEstimates() {
      document.querySelectorAll(".date-btn").forEach((button) => {
        const estimate = button.querySelector(".d-pct");
        if (estimate) estimate.textContent = "";
        delete button.dataset.estimateState;
      });
    }

    function setDateEstimate(targetDate, value, unavailable = false) {
      const button = document.querySelector(`.date-btn[data-date="${CSS.escape(targetDate)}"]`);
      if (!button) return;
      const estimate = button.querySelector(".d-pct");
      if (!estimate) return;
      estimate.textContent = unavailable ? (labels.map_date_unavailable || "-") : `${value}%`;
      button.dataset.estimateState = unavailable ? "unavailable" : "available";
    }

    function clearDateEstimate(targetDate) {
      const button = document.querySelector(`.date-btn[data-date="${CSS.escape(targetDate)}"]`);
      if (!button) return;
      const estimate = button.querySelector(".d-pct");
      if (estimate) estimate.textContent = "";
      delete button.dataset.estimateState;
    }

    function loadSelectedEstimates(feature) {
      const properties = feature?.properties || {};
      const targetDates = stateData.info?.target_dates || [];
      const assessmentDate = properties.assessment_date;
      const updateId = properties.update_id;
      const cellId = properties.cell_id || feature?.id;
      stateData.estimateFeature = feature;
      stateData.estimateGeneration += 1;
      stateData.estimateRequest?.abort();
      stateData.estimateRequest = null;
      clearDateEstimates();
      if (!targetDates.length || !assessmentDate || !updateId || !cellId) {
        targetDates.forEach((targetDate) => setDateEstimate(targetDate, null, true));
        return;
      }
      const generation = stateData.estimateGeneration;
      const assessmentTime = new Date(`${assessmentDate}T12:00:00Z`).getTime();
      const eligibleDates = targetDates.filter((targetDate) => {
        const targetTime = new Date(`${targetDate}T12:00:00Z`).getTime();
        return targetTime >= assessmentTime && targetTime <= assessmentTime + 7 * 86400000;
      });
      targetDates.filter((targetDate) => !eligibleDates.includes(targetDate)).forEach((targetDate) => setDateEstimate(targetDate, null, true));
      const cacheKey = `${cellId}|${updateId}`;
      let cached = stateData.estimateCache.get(cacheKey);
      if (!cached) {
        cached = new Map();
        stateData.estimateCache.set(cacheKey, cached);
        while (stateData.estimateCache.size > 12) stateData.estimateCache.delete(stateData.estimateCache.keys().next().value);
      }
      const missingDates = eligibleDates.filter((targetDate) => !cached.has(targetDate));
      eligibleDates.filter((targetDate) => cached.has(targetDate)).forEach((targetDate) => {
        const result = cached.get(targetDate);
        setDateEstimate(targetDate, result.value, result.unavailable);
      });
      if (!missingDates.length) return;
      const controller = new AbortController();
      stateData.estimateRequest = controller;
      Promise.all(missingDates.map(async (targetDate) => {
        const query = new URLSearchParams({ target_date: targetDate, update_id: updateId });
        try {
          const { response, body } = await fetchJson(`/api/v1/areas/${encodeURIComponent(cellId)}?${query}`, { signal: controller.signal });
          if (!response.ok) return [targetDate, { error: true }];
          if (body?.estimate?.whole_percentage === null || body?.estimate?.whole_percentage === undefined) {
            return [targetDate, { value: null, unavailable: true }];
          }
          const value = Number(body.estimate.whole_percentage);
          return Number.isFinite(value)
            ? [targetDate, { value, unavailable: false }]
            : [targetDate, { error: true }];
        } catch (error) {
          if (error.name === "AbortError") throw error;
          return [targetDate, { error: true }];
        }
      })).then((entries) => {
        if (generation !== stateData.estimateGeneration) return;
        let failed = false;
        entries.forEach(([targetDate, result]) => {
          if (result.error) {
            failed = true;
            clearDateEstimate(targetDate);
            return;
          }
          cached.set(targetDate, result);
          setDateEstimate(targetDate, result.value, result.unavailable);
        });
        if (failed) {
          message(labels.map_request_error, "error", true, () => loadSelectedEstimates(feature));
        }
      }).catch((error) => {
        if (error.name !== "AbortError" && generation === stateData.estimateGeneration) {
          missingDates.forEach((targetDate) => clearDateEstimate(targetDate));
          message(labels.map_request_error, "error", true, () => loadSelectedEstimates(feature));
        }
      }).finally(() => {
        if (generation === stateData.estimateGeneration) stateData.estimateRequest = null;
      });
    }

    function applyBasePalette() {
      const map = stateData.map;
      if (!map) return;
      const contrast = state.background === "contrast";
      const background = contrast ? "#e0e0de" : "#f5f0e6";
      const layers = map.getStyle()?.layers || [];
      layers.forEach((layer) => {
        if (layer.id.startsWith("micometeo-")) return;
        if (layer.type === "background") {
          map.setPaintProperty(layer.id, "background-color", background);
        }
        if (layer.type !== "fill") return;
        const id = layer.id.toLowerCase();
        let fillColor = contrast ? "#d0d0ce" : "#ebe5d9";
        if (/water|river|lake|ocean|sea/.test(id)) {
          fillColor = contrast ? "#c3c7c7" : "#dbe4e1";
        } else if (/building|built/.test(id)) {
          fillColor = contrast ? "#d9d9d7" : "#eeeae2";
        }
        if (/land|park|wood|forest|grass|water|river|lake|ocean|sea|building|built/.test(id)) {
          map.setPaintProperty(layer.id, "fill-color", fillColor);
          map.setPaintProperty(layer.id, "fill-opacity", contrast ? 0.92 : 1);
        }
      });
    }

    function addMissingPattern() {
      const map = stateData.map;
      if (!map || map.hasImage("micometeo-missing")) return;
      const canvas = document.createElement("canvas");
      canvas.width = 12;
      canvas.height = 12;
      const context = canvas.getContext("2d");
      if (!context) return;
      context.fillStyle = "#d8d8d4";
      context.fillRect(0, 0, 12, 12);
      context.strokeStyle = "#888984";
      context.lineWidth = 2;
      context.beginPath();
      context.moveTo(-2, 10);
      context.lineTo(10, -2);
      context.moveTo(2, 14);
      context.lineTo(14, 2);
      context.stroke();
      map.addImage("micometeo-missing", context.getImageData(0, 0, 12, 12), { pixelRatio: 1 });
    }

    function addSourcesAndLayers() {
      const map = stateData.map;
      if (!map) return;
      stateData.styleLoads += 1;
      applyBasePalette();
      addMissingPattern();
      if (!map.getSource("forest")) map.addSource("forest", { type: "geojson", data: EMPTY });
      if (!map.getSource("squares")) map.addSource("squares", { type: "geojson", data: EMPTY, promoteId: "cell_id" });
      if (!map.getSource("selected-square")) map.addSource("selected-square", { type: "geojson", data: EMPTY });
      if (!map.getSource("weather-area")) map.addSource("weather-area", { type: "geojson", data: EMPTY });
      if (!map.getLayer("micometeo-forest")) {
        map.addLayer({
          id: "micometeo-forest",
          type: "fill",
          source: "forest",
          paint: {
            "fill-color": ["interpolate", ["linear"], ["coalesce", ["get", "forest_share"], 0], 0, "rgba(60,110,89,0)", 0.1, "rgba(60,110,89,0.1)", 1, "rgba(60,110,89,0.58)"],
            "fill-opacity": 0.72,
          },
        });
      }
      if (!map.getLayer("micometeo-square-estimates")) {
        map.addLayer({
          id: "micometeo-square-estimates",
          type: "fill",
          source: "squares",
          filter: ["==", ["get", "state"], "available"],
          paint: {
            "fill-color": ["interpolate", ["linear"], ["coalesce", ["get", "percentage"], 0], 0, "#fff9f0", 20, "#f3e6d0", 40, "#ebd6b5", 60, "#dcbc91", 80, "#c99e6b", 100, "#c99e6b"],
            "fill-opacity": 0.6,
            "fill-antialias": false,
          },
        });
      }
      if (!map.getLayer("micometeo-square-missing")) {
        map.addLayer({
          id: "micometeo-square-missing",
          type: "fill",
          source: "squares",
          filter: ["in", ["get", "state"], ["literal", ["unavailable", "noresultyet", "expired"]]],
          paint: { "fill-color": "#d8d8d4", "fill-pattern": "micometeo-missing", "fill-opacity": 0.72 },
        });
      }
      if (!map.getLayer("micometeo-square-noforest")) {
        map.addLayer({
          id: "micometeo-square-noforest",
          type: "fill",
          source: "squares",
          filter: ["==", ["get", "state"], "noforest"],
          paint: { "fill-color": "rgba(0,0,0,0)", "fill-opacity": 0 },
        });
      }
      if (!map.getLayer("micometeo-noforest-line")) {
        map.addLayer({
          id: "micometeo-noforest-line",
          type: "line",
          source: "squares",
          filter: ["==", ["get", "state"], "noforest"],
          paint: { "line-color": "#777872", "line-width": 1.25, "line-dasharray": [1, 2], "line-opacity": 0.9 },
        });
      }
      if (!map.getLayer("micometeo-grid-lines")) {
        map.addLayer({
          id: "micometeo-grid-lines",
          type: "line",
          source: "squares",
          minzoom: 12,
          filter: ["==", ["get", "state"], "available"],
          paint: { "line-color": "rgba(17,34,27,0.25)", "line-width": 0.5, "line-opacity": 0.7 },
        });
      }
      if (!map.getLayer("micometeo-missing-line")) {
        map.addLayer({
          id: "micometeo-missing-line",
          type: "line",
          source: "squares",
          filter: ["in", ["get", "state"], ["literal", ["unavailable", "noresultyet", "expired"]]],
          paint: { "line-color": "#777872", "line-width": 1, "line-dasharray": [2, 2], "line-opacity": 0.9 },
        });
      }
      if (!map.getLayer("micometeo-weather-area")) {
        map.addLayer({
          id: "micometeo-weather-area",
          type: "line",
          source: "weather-area",
          paint: { "line-color": "#2e5645", "line-width": 2, "line-dasharray": [2, 2], "line-opacity": 0.85 },
        });
      }
      if (!map.getLayer("micometeo-selected")) {
        map.addLayer({
          id: "micometeo-selected",
          type: "line",
          source: "selected-square",
          paint: { "line-color": "#2e5645", "line-width": 3, "line-gap-width": 2 },
        });
      }
      if (stateData.forest && stateData.forestVisible) map.getSource("forest")?.setData(stateData.forest);
      if (stateData.squares) map.getSource("squares")?.setData(stateData.squares);
      if (stateData.selected) drawSelection(stateData.selected);
      setForestVisible(stateData.forestVisible);
      setSquareLayersVisible(false);
      if (stateData.squares) revealSquaresWhenRendered(stateData.generation);
      applyOverlay(state.overlay);
      applyOpacity(state.opacity);
    }

    function restoreCustomLayers() {
      const map = stateData.map;
      if (!map || !map.isStyleLoaded?.()) return;
      if (map.getSource("squares") && map.getLayer("micometeo-square-estimates")) return;
      if (stateData.styleRestoreGeneration === stateData.styleGeneration) return;
      stateData.styleRestoreGeneration = stateData.styleGeneration;
      addSourcesAndLayers();
    }

    function applyOverlay(enabled) {
      const map = stateData.map;
      if (!map) return;
      setSquareLayersVisible(stateData.squaresRendered, false);
      if (map.getLayer("micometeo-forest")) {
        map.setLayoutProperty("micometeo-forest", "visibility", enabled && stateData.forestVisible ? "visible" : "none");
      }
    }

    function applyOpacity(value) {
      const map = stateData.map;
      if (!map) return;
      const opacity = Math.max(0, Math.min(1, Number(value) / 100));
      if (map.getLayer("micometeo-square-estimates")) map.setPaintProperty("micometeo-square-estimates", "fill-opacity", opacity);
      if (map.getLayer("micometeo-square-missing")) map.setPaintProperty("micometeo-square-missing", "fill-opacity", opacity);
      if (map.getLayer("micometeo-square-noforest")) map.setPaintProperty("micometeo-square-noforest", "fill-opacity", 0);
      if (map.getLayer("micometeo-noforest-line")) map.setPaintProperty("micometeo-noforest-line", "line-opacity", opacity);
      if (map.getLayer("micometeo-missing-line")) map.setPaintProperty("micometeo-missing-line", "line-opacity", opacity);
    }

    function featureCenter(feature) {
      const coordinates = feature.geometry?.coordinates?.[0] || [];
      const points = coordinates.flatMap((ring) => Array.isArray(ring?.[0]) ? ring : [ring]);
      const valid = points.filter((point) => Array.isArray(point) && point.length >= 2);
      if (!valid.length) return null;
      const longitudes = valid.map((point) => point[0]);
      const latitudes = valid.map((point) => point[1]);
      return [
        (Math.min(...longitudes) + Math.max(...longitudes)) / 2,
        (Math.min(...latitudes) + Math.max(...latitudes)) / 2,
      ];
    }

    function areaFeature(feature) {
      const properties = feature.properties || {};
      const cell = properties.weather_cell;
      if (!cell || properties.state === "noforest" || properties.reason === "forest_missing" || properties.unavailable_reason === "forest_missing") return EMPTY;
      const lat = Number(cell.latitude);
      const lon = Number(cell.longitude);
      if (!Number.isFinite(lat) || !Number.isFinite(lon) || lat < -90 || lat > 90 || lon < -180 || lon > 180) return EMPTY;
      const lngHalf = 0.05;
      const latHalf = 0.05;
      return {
        type: "FeatureCollection",
        features: [{ type: "Feature", geometry: { type: "Polygon", coordinates: [[[lon - lngHalf, lat - latHalf], [lon + lngHalf, lat - latHalf], [lon + lngHalf, lat + latHalf], [lon - lngHalf, lat + latHalf], [lon - lngHalf, lat - latHalf]]] }, properties: {} }],
      };
    }

    function plainFeature(feature) {
      if (!feature) return null;
      try {
        return JSON.parse(JSON.stringify({
          type: "Feature",
          id: feature.id,
          geometry: feature.geometry,
          properties: feature.properties ?? {},
        }));
      } catch (error) {
        return null;
      }
    }

    function drawSelection(feature) {
      const map = stateData.map;
      if (!map) return;
      const selection = { type: "FeatureCollection", features: [feature] };
      map.getSource("selected-square")?.setData(selection);
      const weatherArea = areaFeature(feature);
      map.getSource("weather-area")?.setData(weatherArea);
      stateData.weatherLabel?.remove();
      stateData.weatherLabel = null;
      const weatherCell = feature.properties?.weather_cell;
      if (weatherArea.features.length) {
        const label = document.createElement("span");
        label.className = "live-weather-label";
        label.textContent = `${labels.weather_area}: ~11 × 8 km`;
        stateData.weatherLabel = new window.maplibregl.Marker({ element: label, anchor: "bottom-left" })
          .setLngLat([Number(weatherCell.longitude) - 0.05, Number(weatherCell.latitude) + 0.05])
          .addTo(map);
      }
    }

    function createLiveDetails() {
      let details = document.querySelector("aside[data-live-details]");
      if (details) return details;
      const wrapper = document.querySelector("#sheetwrap");
      if (!wrapper) return null;
      details = document.createElement("aside");
      details.className = "details live-details";
      details.dataset.liveDetails = "true";
      details.dataset.details = "true";
      details.dataset.sheetHeight = state.sheetHeight;
      details.dataset.size = state.sheetHeight;
      details.setAttribute("aria-label", labels.details_label);
      wrapper.append(details);
      return details;
    }

    function showDetails(feature) {
      const properties = feature.properties || {};
      const details = createLiveDetails();
      if (!details) return;
      details.replaceChildren();
      const top = document.createElement("div");
      top.className = "d-top";
      const heading = document.createElement("h2");
      heading.textContent = properties.cell_id || feature.id || labels.map_selected;
      const coordinate = document.createElement("p");
      coordinate.className = "d-coord";
      const centre = featureCenter(feature);
      coordinate.textContent = centre ? `${centre[1].toFixed(4)}° N, ${centre[0].toFixed(4)}° E` : "";
      const titleGroup = document.createElement("div");
      titleGroup.className = "live-details-title";
      titleGroup.append(heading, coordinate);
      top.append(titleGroup);
      const close = document.createElement("button");
      close.type = "button";
      close.className = "btn btn-secondary live-details-close";
      close.textContent = "×";
      close.setAttribute("aria-label", labels.close_details);
      close.addEventListener("click", () => clearSelection());
      top.append(close);
      details.append(top);
      const status = document.createElement("div");
      status.className = "live-summary";
      const stateName = properties.state || "unavailable";
      const percent = properties.percentage === null || properties.percentage === undefined ? labels.estimate_unavailable : `${properties.percentage}%`;
      const title = document.createElement("strong");
      title.textContent = stateName === "available" ? percent : stateName === "noforest" ? labels.map_no_forest : stateName === "expired" ? labels.map_expired : stateName === "noresultyet" ? labels.map_pending : labels.map_missing;
      status.append(title);
      const rows = [
        [labels.map_target, properties.target_date ? date(properties.target_date) : ""],
        [labels.map_assessment, properties.assessment_date ? date(properties.assessment_date) : ""],
        [labels.map_calculated_at, properties.calculated_at ? dateTime(properties.calculated_at) : ""],
        [labels.map_update, properties.update_id || ""],
      ];
      rows.forEach(([label, value]) => {
        const row = document.createElement("p");
        row.textContent = `${label}: ${value || "-"}`;
        status.append(row);
      });
      details.append(status);
      if (stateName === "available") {
        const notice = document.createElement("div");
        notice.className = "notice-experimental";
        const noticeText = document.createElement("p");
        const noticeTitle = document.createElement("strong");
        noticeTitle.textContent = labels.experimental_label;
        noticeText.append(noticeTitle, ` ${labels.experimental_body}`);
        notice.append(noticeText);
        details.append(notice);
      }
      const closeButton = document.createElement("button");
      closeButton.type = "button";
      closeButton.className = "btn btn-quiet";
      closeButton.textContent = labels.back_to_map;
      closeButton.addEventListener("click", () => clearSelection());
      details.append(closeButton);
      state.details = true;
      state.square = properties.cell_id || feature.id || "";
      state.updateId = properties.update_id || "";
      state.assessment = properties.assessment_date || state.assessment;
      root.classList.add("details-open");
      document.querySelector("#main")?.classList.add("details-open");
      document.getElementById("centre-btn")?.removeAttribute("hidden");
      persistState();
      liveMapController?.resize();
    }

    function clearSelection() {
      stateData.weatherLabel?.remove();
      stateData.weatherLabel = null;
      stateData.selected = null;
      stateData.estimateGeneration += 1;
      stateData.estimateRequest?.abort();
      stateData.estimateRequest = null;
      stateData.estimateFeature = null;
      clearDateEstimates();
      stateData.pendingSelectionId = null;
      stateData.pendingSelectionUpdateId = null;
      stateData.pendingSelectionDetails = false;
      emptySource("selected-square");
      emptySource("weather-area");
      const details = document.querySelector("aside[data-live-details]");
      details?.remove();
      state.details = false;
      state.square = "";
      state.updateId = "";
      root.classList.remove("details-open");
      document.querySelector("#main")?.classList.remove("details-open");
      persistState();
      liveMapController?.resize();
    }

    function selectFeature(feature) {
      const selection = plainFeature(feature);
      if (!selection?.geometry) return;
      stateData.selected = selection;
      drawSelection(selection);
      showDetails(selection);
      loadSelectedEstimates(selection);
    }

    function visibleSizeKm() {
      const bounds = stateData.map.getBounds();
      const centre = stateData.map.getCenter();
      const width = Math.abs(bounds.getEast() - bounds.getWest()) * 111.32 * Math.max(0.2, Math.cos(centre.lat * Math.PI / 180));
      const height = Math.abs(bounds.getNorth() - bounds.getSouth()) * 111.32;
      return { width, height };
    }

    function outsideCoverage() {
      const coverage = stateData.info?.coverage;
      if (!coverage) return false;
      const values = Array.isArray(coverage)
        ? { west: coverage[0], south: coverage[1], east: coverage[2], north: coverage[3] }
        : coverage;
      const bounds = stateData.map.getBounds();
      return bounds.getEast() <= Number(values.west)
        || bounds.getWest() >= Number(values.east)
        || bounds.getNorth() <= Number(values.south)
        || bounds.getSouth() >= Number(values.north);
    }

    function syncMapState() {
      const centre = stateData.map?.getCenter();
      if (!centre) return;
      const zoom = Number(stateData.map.getZoom().toFixed(2));
      const view = { lat: centre.lat, lng: centre.lng, zoom };
      const changed = !stateData.lastView
        || Math.abs(stateData.lastView.lat - view.lat) > 0.000001
        || Math.abs(stateData.lastView.lng - view.lng) > 0.000001
        || Math.abs(stateData.lastView.zoom - view.zoom) > 0.001;
      stateData.lastView = view;
      state.center = `${centre.lat.toFixed(5)},${centre.lng.toFixed(5)}`;
      state.zoom = zoom;
      persistState();
      return changed;
    }

    async function fetchJson(url, options = {}) {
      const response = await fetch(url, options);
      const body = await response.json().catch(() => null);
      return { response, body };
    }

    async function fetchStyle(name, signal) {
      const { response, body } = await fetchJson(styles[name], { signal, headers: { Accept: "application/json" } });
      if (!response.ok || !body || body.version !== 8 || !Array.isArray(body.layers) || !body.sources) throw new Error("style");
      return { ...body, metadata: { ...(body.metadata || {}), micometeoStyle: name } };
    }

    async function fetchForest(generation) {
      if (!stateData.map || generation !== stateData.generation) return false;
      if (stateData.forest) {
        setForestVisible(true);
        return true;
      }
      if (!stateData.forestRequest) {
        message(labels.map_loading, "wait");
        stateData.forestRequest = (async () => {
          try {
            const { response, body } = await fetchJson("/api/v1/forest-layer", { headers: { Accept: "application/geo+json" } });
            if (!response.ok || !body?.features) throw new Error("forest-layer");
            return body;
          } catch (error) {
            return null;
          } finally {
            stateData.forestRequest = null;
          }
        })();
      }
      const body = await stateData.forestRequest;
      if (generation !== stateData.generation) return false;
      if (!body) {
        message(labels.map_layer_error, "error", true, () => scheduleFetch(0));
        return false;
      }
      stateData.forest = body;
      stateData.map.getSource("forest")?.setData(body);
      setForestVisible(true);
      return true;
    }

    function dataForDate(data, targetDate) {
      const features = data.features.filter((feature) => feature.properties?.target_date === targetDate);
      return { ...data, features };
    }

    function handleSelectionAfterData(data) {
      const selectedId = state.square || stateData.pendingSelectionId;
      if (!selectedId) return "";
      const selectedUpdateId = state.updateId || stateData.pendingSelectionUpdateId;
      const feature = data.features.find((item) => item.id === selectedId || item.properties?.cell_id === selectedId);
      if (!feature) {
        // A selected area remains selected when it leaves the viewport.
        if (stateData.selected?.properties?.target_date === state.date && state.details) return "";
        stateData.pendingSelectionId = null;
        stateData.pendingSelectionUpdateId = null;
        stateData.pendingSelectionDetails = false;
        clearSelection();
        return "";
      }
      if (feature.properties?.state === "expired" || (selectedUpdateId && feature.properties?.update_id && feature.properties.update_id !== selectedUpdateId)) {
        clearSelection();
        return labels.map_expired;
      }
      stateData.pendingSelectionId = null;
      stateData.pendingSelectionUpdateId = null;
      state.square = selectedId;
      state.updateId = feature.properties?.update_id || selectedUpdateId || "";
      state.details = state.details || stateData.pendingSelectionDetails;
      stateData.pendingSelectionDetails = false;
      persistState();
      stateData.selected = feature;
      drawSelection(feature);
      loadSelectedEstimates(feature);
      if (state.details) showDetails(feature);
      return "";
    }

    function providerReasonMessage(features) {
      const reasons = features
        .map((feature) => feature.properties?.reason || feature.properties?.unavailable_reason)
        .filter(Boolean);
      for (const reason of ["visitor_limit", "quota_exhausted", "provider_refused", "provider_unavailable"]) {
        const text = providerReasonText(reason);
        if (reasons.includes(reason)) return text;
      }
      return "";
    }

    function providerReasonText(reason) {
      return {
        visitor_limit: labels.map_visitor_limit,
        quota_exhausted: labels.map_quota_exhausted,
        provider_refused: labels.map_provider_refused,
        provider_unavailable: labels.map_provider_unavailable,
      }[reason] || "";
    }

    async function fetchSquares(generation, preserveData = false) {
      if (!stateData.info || !stateData.map || generation !== stateData.generation) return;
      if (stateData.request) stateData.request.abort();
      const size = visibleSizeKm();
      if (size.width > Number(stateData.info.max_width_km) || size.height > Number(stateData.info.max_height_km)) {
        stateData.request = null;
        if (!preserveData) clearSquares();
        const loaded = await fetchForest(generation);
        if (generation !== stateData.generation) return;
        if (loaded) message(labels.map_zoom_in, "wait");
        return;
      }
      setForestVisible(false);
      if (outsideCoverage()) {
        clearSquares();
        message(labels.map_outside_coverage, "error");
        return;
      }
      const bounds = stateData.map.getBounds();
      const bbox = [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()].map((value) => value.toFixed(6)).join(",");
      const query = new URLSearchParams({ bbox, target_date: state.date });
      const controller = new AbortController();
      stateData.request = controller;
      stateData.requestCount += 1;
      const requestGeneration = generation;
      if (!preserveData) clearSquares();
      message((labels.map_loading_estimates || labels.loading).replace("{date}", fullDate(state.date)), "wait");
      try {
        const { response, body } = await fetchJson(`/api/v1/squares?${query}`, { signal: controller.signal });
        if (requestGeneration !== stateData.generation || controller.signal.aborted) return;
        if (!response.ok) {
          const code = body?.code;
          if (code === "view_too_large" || code === "square_limit_exceeded") message(labels.map_zoom_in, "wait");
          else if (code === "outside_coverage") message(labels.map_outside_coverage, "error");
          else if (providerReasonText(code)) message(providerReasonText(code), "error", true, () => scheduleFetch(0));
          else message(labels.map_request_error, "error", true, () => scheduleFetch(0));
          return;
        }
        if (!body || !Array.isArray(body.features)) throw new Error("squares");
        stateData.request = null;
        stateData.lastRequest = { targetDate: state.date, bbox, generation: requestGeneration };
        stateData.squares = dataForDate(body, state.date);
        stateData.map.getSource("squares")?.setData(stateData.squares);
        updateDateMetadata(stateData.squares.features, false, stateData.info);
        stateData.renderCount += 1;
        const selectionMessage = handleSelectionAfterData(stateData.squares);
        revealSquaresWhenRendered(requestGeneration);
        const pending = stateData.squares.features.some((feature) => feature.properties?.state === "noresultyet" && feature.properties?.reason === "pending");
        const providerMessage = providerReasonMessage(stateData.squares.features);
        if (selectionMessage) {
          message(selectionMessage, "older");
        } else if (providerMessage) {
          message(providerMessage, "error", true, () => scheduleFetch(0));
        } else if (pending && stateData.pendingPolls < 2) {
          stateData.pendingPolls += 1;
          message(labels.map_pending, "wait");
          window.setTimeout(() => fetchSquares(requestGeneration, true), 2500);
        } else if (pending) {
          message(labels.map_pending, "error", true, () => scheduleFetch(0));
        } else if (!stateData.squares.features.length) {
          message(labels.map_no_results, "wait");
        } else {
          message("");
        }
      } catch (error) {
        if (error.name === "AbortError") return;
        if (requestGeneration !== stateData.generation) return;
        message(labels.map_request_error, "error", true, () => scheduleFetch(0));
      }
    }

    function scheduleFetch(delay = 280, alreadyCleared = false) {
      window.clearTimeout(stateData.debounce);
      stateData.generation += 1;
      stateData.pendingPolls = 0;
      if (stateData.request) stateData.request.abort();
      if (!alreadyCleared) clearSquares();
      const generation = stateData.generation;
      stateData.debounce = window.setTimeout(() => fetchSquares(generation, true), delay);
    }

    function bindMapEvents() {
      const map = stateData.map;
      const invalidateMovement = () => {
        if (stateData.movementInvalidated) return;
        stateData.invalidationCount += 1;
        stateData.movementInvalidated = true;
        stateData.generation += 1;
        stateData.pendingPolls = 0;
        stateData.request?.abort();
        setForestVisible(false);
        // Keep the panel width stable until the drag has finished.
        setSquareLayersVisible(false);
      };
      listen("movestart", () => {
        stateData.moveStarts += 1;
        window.cancelAnimationFrame(stateData.moveFrame);
        stateData.movementInvalidated = false;
        stateData.moveFrame = window.requestAnimationFrame(() => {
          const centre = map.getCenter();
          const zoom = Number(map.getZoom().toFixed(2));
          const view = stateData.lastView;
          const changed = !view
            || Math.abs(view.lat - centre.lat) > 0.000001
            || Math.abs(view.lng - centre.lng) > 0.000001
            || Math.abs(view.zoom - zoom) > 0.001;
          if (changed) invalidateMovement();
        });
      });
      listen("moveend", () => {
        window.cancelAnimationFrame(stateData.moveFrame);
        stateData.moveEnds += 1;
        const changed = syncMapState();
        if (changed && !stateData.movementInvalidated) invalidateMovement();
        if (changed || stateData.movementInvalidated) scheduleFetch(280);
        stateData.movementInvalidated = false;
      });
      listen("click", (event) => {
        const features = map.queryRenderedFeatures(event.point, { layers: ["micometeo-square-estimates", "micometeo-square-missing", "micometeo-square-noforest", "micometeo-noforest-line", "micometeo-missing-line"] });
        if (features[0]) selectFeature(features[0]);
      });
      listen("mouseenter", () => { map.getCanvas().style.cursor = "pointer"; }, "micometeo-square-estimates");
      listen("mouseleave", () => { map.getCanvas().style.cursor = ""; }, "micometeo-square-estimates");
    }

    async function initialise() {
      if (stateData.initialising || stateData.map) return;
      stateData.initialising = true;
      message(labels.map_loading, "wait");
      let styleFailed = false;
      try {
        const { response, body } = await fetchJson("/api/v1/info");
        if (!response.ok || !body?.target_dates?.length) throw new Error("info");
        stateData.info = body;
        window.clearTimeout(stateData.dateTimer);
        stateData.dateTimer = window.setTimeout(async function refreshDates() {
          try {
            const { response, body: latest } = await fetchJson("/api/v1/info");
            if (!response.ok) throw new Error("info-refresh");
            if (latest?.today && latest.today !== stateData.info.today) {
              window.location.reload();
              return;
            }
          } catch (error) {
            message(labels.map_info_error, "error", true, () => window.location.reload());
          } finally {
            stateData.dateTimer = window.setTimeout(refreshDates, 900_000);
          }
        }, 900_000);
        state.assessment = body.today;
        if (!body.target_dates.includes(state.date)) state.date = body.target_dates[0];
        renderDates(body.target_dates);
        styleFailed = true;
        const initialStyle = await fetchStyle(state.background);
        styleFailed = false;
        const mapCenter = parseCenter(state.center) || [11.0, 43.7];
        const options = {
          container,
          style: initialStyle,
          center: mapCenter,
          zoom: state.zoom,
          attributionControl: false,
          // The container observer below handles size changes without a delayed second resize.
          trackResize: false,
          maxZoom: 18,
        };
        stateData.map = new window.maplibregl.Map(options);
        stateData.backgroundKey = state.background;
        if (window.ResizeObserver) {
          const resizeTarget = container.closest(".mapcell") || container;
          stateData.resizeObserver = new ResizeObserver((entries) => {
            const rectangle = entries[0]?.contentRect;
            if (!rectangle) return;
            const width = Math.round(rectangle.width);
            const height = Math.round(rectangle.height);
            if (width === stateData.resizeWidth && height === stateData.resizeHeight) return;
            stateData.resizeWidth = width;
            stateData.resizeHeight = height;
            controller.resize();
          });
          stateData.resizeObserver.observe(resizeTarget);
        }
        stateData.map.addControl(new window.maplibregl.AttributionControl({ compact: true, customAttribution: "OpenStreetMap contributors · OpenFreeMap" }), "bottom-right");
        listen("style.load", restoreCustomLayers);
        listen("styledata", restoreCustomLayers);
        listenOnce("load", () => {
          restoreCustomLayers();
          bindMapEvents();
          stateData.ready = true;
          syncMapState();
          scheduleFetch(0);
        });
        const attribution = document.querySelector("[data-map-attribution]");
        if (attribution) {
          attribution.replaceChildren();
          const mapCredits = document.createElement("span");
          mapCredits.className = "attribution-map";
          const credits = [
            ["OpenStreetMap", "https://www.openstreetmap.org/copyright"],
            ["OpenMapTiles", "https://openmaptiles.org"],
            ["OpenFreeMap", "https://openfreemap.org"],
          ];
          credits.forEach(([text, url], index) => {
            if (index) mapCredits.append(" · ");
            if (typeof url === "string" && /^https?:\/\//.test(url)) {
              const link = document.createElement("a");
              link.href = url;
              link.rel = "noreferrer";
              link.textContent = text;
              mapCredits.append(link);
            } else {
              mapCredits.append(document.createTextNode(text));
            }
          });
          attribution.append(mapCredits);

          const apiCredits = Array.isArray(body.attributions) ? body.attributions : [];
          if (apiCredits.length) {
            attribution.append(document.createTextNode(" · "));
            const details = document.createElement("details");
            details.className = "attribution-details";
            const summary = document.createElement("summary");
            summary.textContent = labels.map_api_credit;
            details.append(summary);
            const detailsBody = document.createElement("div");
            detailsBody.className = "attribution-details-body";
            apiCredits.forEach((item) => {
              const source = document.createElement("div");
              source.className = "attribution-source";
              if (item.name) {
                const name = document.createElement("strong");
                name.textContent = item.name;
                source.append(name);
              }
              [item.credit, item.licence].forEach((text) => {
                if (!text) return;
                const line = document.createElement("div");
                if (typeof item.url === "string" && /^https?:\/\//.test(item.url)) {
                  const link = document.createElement("a");
                  link.href = item.url;
                  link.rel = "noreferrer";
                  link.textContent = text;
                  line.append(link);
                } else {
                  line.append(document.createTextNode(text));
                }
                source.append(line);
              });
              detailsBody.append(source);
            });
            details.append(detailsBody);
            attribution.append(details);
          }
        }
      } catch (error) {
        message(
          styleFailed ? labels.map_style_error : labels.map_info_error,
          "error",
          true,
          () => initialise(),
        );
      } finally {
        stateData.initialising = false;
      }
    }

    const controller = {
      zoom(delta) {
        if (!stateData.map) return;
        stateData.map.easeTo({ zoom: Math.max(1, Math.min(18, stateData.map.getZoom() + delta)) });
      },
      setDate() {
        if (stateData.ready) scheduleFetch();
      },
      setOverlay(value) { applyOverlay(value); },
      setOpacity(value) { applyOpacity(value); },
      centerSelection() {
        const map = stateData.map;
        if (!map || !stateData.squaresRendered) return false;
        const point = map.project(map.getCenter());
        const features = map.queryRenderedFeatures(point, {
          layers: ["micometeo-square-estimates", "micometeo-square-missing", "micometeo-square-noforest", "micometeo-noforest-line", "micometeo-missing-line"],
        });
        if (!features[0]) return false;
        selectFeature(features[0]);
        return true;
      },
      resize() {
        const width = container.clientWidth;
        const height = container.clientHeight;
        if (width === stateData.appliedResizeWidth && height === stateData.appliedResizeHeight) return;
        stateData.appliedResizeWidth = width;
        stateData.appliedResizeHeight = height;
        stateData.map?.resize();
      },
      async setBackground(value, previousValue = stateData.backgroundKey) {
        if (!stateData.map || !styles[value]) return;
        const generation = ++stateData.styleGeneration;
        stateData.styleRequest?.abort();
        if (value === stateData.backgroundKey) {
          stateData.styleRequest = null;
          return;
        }
        const request = new AbortController();
        stateData.styleRequest = request;
        try {
          const style = await fetchStyle(value, request.signal);
          if (generation !== stateData.styleGeneration || request.signal.aborted) return;
          stateData.map.setStyle(style, { diff: false });
          stateData.map.once("idle", restoreCustomLayers);
          stateData.backgroundKey = value;
          state.background = value;
          root.classList.toggle("bg-contrast", state.background === "contrast");
          document.querySelectorAll("input[name=background]").forEach((input) => { input.checked = input.value === state.background; });
          persistState();
          const styleMessageId = stateData.styleMessageId;
          stateData.styleMessageId = null;
          const current = currentMessage();
          if (
            styleMessageId
            && current?.id === styleMessageId
            && current.source === "style"
          ) {
            message("");
          }
        } catch (error) {
          if (error.name === "AbortError" || generation !== stateData.styleGeneration) return;
          state.background = previousValue;
          root.classList.toggle("bg-contrast", state.background === "contrast");
          document.querySelectorAll("input[name=background]").forEach((input) => { input.checked = input.value === state.background; });
          persistState();
          const failedStyle = value;
          stateData.styleMessageId = message(
            labels.map_style_error,
            "error",
            true,
            () => controller.setBackground(failedStyle, stateData.backgroundKey),
            "style",
          );
        } finally {
          if (generation === stateData.styleGeneration) stateData.styleRequest = null;
        }
      },
      getDiagnostics() {
        return {
          mapInstances: stateData.map ? 1 : 0,
          mapInstanceCount: stateData.map ? 1 : 0,
          listenerCount: stateData.listenerCount,
          requestCount: stateData.requestCount,
          renderCount: stateData.renderCount,
          styleLoads: stateData.styleLoads,
          generation: stateData.generation,
          moveStarts: stateData.moveStarts,
          moveEnds: stateData.moveEnds,
          invalidationCount: stateData.invalidationCount,
          ready: stateData.ready,
          targetDate: state.date,
          background: state.background,
          overlay: state.overlay,
          opacity: state.opacity,
          lastTargetDate: stateData.lastRequest?.targetDate || null,
        };
      },
    };
    Object.defineProperty(controller, "map", { get: () => stateData.map });
    Object.defineProperty(controller, "lastRequest", { get: () => stateData.lastRequest });
    window.MicometeoMap = controller;
    initialise();
    return controller;
  }

  liveMapController = createLiveMapController();
})();
