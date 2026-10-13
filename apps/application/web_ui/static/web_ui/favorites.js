(() => {
  "use strict";

  const STORAGE_KEY = "micometeo.favorites";
  const VERSION = 1;
  const COLORS = ["green", "amber", "violet", "blue", "rose"];

  function storage() {
    try {
      return window.localStorage;
    } catch (error) {
      return null;
    }
  }

  function finiteCoordinate(value, minimum, maximum) {
    return typeof value === "number" && Number.isFinite(value) && value >= minimum && value <= maximum;
  }

  function text(value, maximum) {
    return typeof value === "string" && value.trim().length > 0 && value.length <= maximum;
  }

  function validateItem(value) {
    try {
      if (!value || typeof value !== "object" || Array.isArray(value)) return null;
      const fields = new Set(["id", "kind", "latitude", "longitude", "cellId", "name", "color"]);
      if (Object.keys(value).some((key) => !fields.has(key))) return null;
      if (!text(value.id, 128) || !text(value.kind, 16)) return null;
      if (!["point", "grid"].includes(value.kind)) return null;
      if (!finiteCoordinate(value.latitude, -90, 90) || !finiteCoordinate(value.longitude, -180, 180)) return null;
      if (!text(value.name, 160)) return null;
      if (value.color !== undefined && (!text(value.color, 32) || !COLORS.includes(value.color))) return null;
      if (value.kind === "grid" && !text(value.cellId, 160)) return null;
      if (value.kind === "point" && value.cellId !== undefined) return null;
      return {
        id: value.id.trim(),
        kind: value.kind,
        latitude: Number(value.latitude),
        longitude: Number(value.longitude),
        ...(value.kind === "grid" ? { cellId: value.cellId.trim() } : {}),
        name: value.name.trim(),
        ...(value.color !== undefined ? { color: value.color } : {}),
      };
    } catch (error) {
      return null;
    }
  }

  function read() {
    const localStorage = storage();
    if (!localStorage) return { status: "unavailable", items: [], invalid: [] };
    let raw;
    try {
      raw = localStorage.getItem(STORAGE_KEY);
    } catch (error) {
      return { status: "unavailable", items: [], invalid: [] };
    }
    if (raw === null) return { status: "ready", items: [], invalid: [] };
    let wrapper;
    try {
      wrapper = JSON.parse(raw);
    } catch (error) {
      console.warn("Micometeo favorites could not be read as JSON");
      return { status: "unreadable", items: [], invalid: [] };
    }
    if (!wrapper || typeof wrapper !== "object" || Array.isArray(wrapper)
      || Object.keys(wrapper).some((key) => !["version", "items"].includes(key))
      || wrapper.version !== VERSION || !Array.isArray(wrapper.items)) {
      console.warn("Micometeo favorites use an unknown storage version");
      return { status: "unknown", items: [], invalid: [] };
    }
    const items = [];
    const invalid = [];
    const parsedItems = wrapper.items.map((item) => ({ item, valid: validateItem(item) }));
    const idCounts = new Map();
    parsedItems.forEach(({ valid }) => {
      if (valid) idCounts.set(valid.id, (idCounts.get(valid.id) || 0) + 1);
    });
    parsedItems.forEach(({ item, valid }) => {
      if (valid && idCounts.get(valid.id) === 1) {
        items.push(valid);
      }
      else invalid.push(item);
    });
    if (invalid.length) console.warn("Micometeo favorites contain invalid entries");
    return { status: invalid.length ? "warning" : "ready", items, invalid };
  }

  function write(items, invalid) {
    const localStorage = storage();
    if (!localStorage) return { ok: false, reason: "unavailable" };
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: VERSION, items: [...items, ...invalid] }));
      return { ok: true };
    } catch (error) {
      const reason = error?.name === "QuotaExceededError" || error?.code === 22 ? "quota" : "write";
      return { ok: false, reason };
    }
  }

  function sameDestination(first, second) {
    if (first.kind !== second.kind) return false;
    if (first.kind === "grid") return first.cellId === second.cellId;
    return first.latitude === second.latitude && first.longitude === second.longitude;
  }

  function id() {
    try {
      if (window.crypto?.randomUUID) return window.crypto.randomUUID();
    } catch {}
    return `favorite-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }

  window.MicometeoFavorites = {
    colors: COLORS,
    key: STORAGE_KEY,
    read,
    validateItem,
    sameDestination,
    create(value) {
      try {
        return validateItem({ ...value, id: value.id || id() });
      } catch (error) {
        return null;
      }
    },
    write,
  };
})();
