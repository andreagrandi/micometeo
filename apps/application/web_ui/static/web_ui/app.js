(() => {
  "use strict";

  const root = document.querySelector("[data-map-app]");
  const languageButtons = [...document.querySelectorAll("button[data-language]")];
  const locale = () => document.documentElement.lang === "it" ? "it-IT" : "en-GB";

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
    const estimate = button.querySelector(".d-pct")?.textContent.trim().replace("%", "");
    const percentage = document.querySelector(".pct-badge .pct");
    if (percentage && estimate) percentage.textContent = `${estimate}%`;
    persistState();
  }

  document.querySelectorAll(".date-btn").forEach((button) => button.addEventListener("click", () => setDate(button)));
  document.querySelectorAll("[data-zoom]").forEach((button) => button.addEventListener("click", () => {
    state.zoom = Math.min(19, Math.max(1, state.zoom + (button.dataset.zoom === "in" ? 1 : -1)));
    persistState();
    toast(labels.later_map);
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
  });
  document.querySelectorAll("input[name=background]").forEach((input) => input.addEventListener("change", () => {
    state.background = input.value;
    root.classList.toggle("bg-contrast", state.background === "contrast");
    persistState();
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
  });

  document.querySelectorAll("[data-center-select]").forEach((button) => button.addEventListener("click", () => {
    if (button.closest("aside[data-details]")) {
      setDetails(false);
      toast(labels.later_map);
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
})();
