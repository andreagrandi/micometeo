// Landing page behaviour: language switch, date chips, legend and the Abetone preview map.

var COPY = {
  it: {
    tagline: "Gratuito, senza account",
    openMap: "Apri la mappa",
    sampleLabel: "Esempio di design:",
    sampleText: "tutti i valori mostrati sono illustrativi e non provengono da una previsione in tempo reale.",
    noteLabel: "Stima sperimentale:",
    noteText: "questa percentuale non è stata validata. Non indica la tua probabilità personale di trovare porcini.",
    heroTitle: "Scegli un bosco da esplorare per cercare porcini",
    heroText: "Micometeo stima la probabilità che crescano porcini in un quadrato di bosco di 500 m, in tutta Italia, Sicilia e Sardegna comprese. Puoi leggere la stima per oggi e per ognuno dei sette giorni successivi. Il servizio è gratuito, non richiede un account e non mostra pubblicità.",
    mapLabel: "Mappa di esempio con i quadrati di bosco intorno ad Abetone, in Toscana",
    mapCaption: "I quadrati sono colorati secondo la stima di oggi. Il contorno blu indica il quadrato scelto.",
    samplePlace: "Abetone, Toscana",
    sampleToday: "Oggi, 12 ottobre 2026",
    sampleLater: "Giovedì 15 ottobre",
    meaningTitle: "Che cosa significa la percentuale, e che cosa no",
    meaningLead: "La percentuale indica la probabilità che i porcini stiano crescendo da qualche parte dentro il quadrato, nel giorno scelto.",
    meaningMissing: "Se mancano dei dati, per quel quadrato non c'è nessuna stima. La mappa lo dice a parole e non mostra mai 0%.",
    meansTitle: "Che cosa significa",
    means1: "La probabilità che crescano porcini da qualche parte dentro il quadrato di 500 m, nel giorno scelto.",
    means2: "Una stima sperimentale, non ancora validata.",
    notTitle: "Che cosa non significa",
    not1: "La tua probabilità personale di trovare porcini.",
    not2: "La promessa di un fungo in un punto preciso del quadrato.",
    not3: "Una precisione misurata. Le percentuali non sono state validate.",
    methodTitle: "Come si calcola la stima",
    methodIntro: "Ogni stima usa tre tipi di dati.",
    methodRainTitle: "Pioggia.",
    methodRain: "Quella caduta negli ultimi 7, 14 e 21 giorni completati.",
    methodWeatherTitle: "Meteo del giorno.",
    methodWeather: "Il meteo modellato per il giorno scelto, come la temperatura. È un calcolo su un'area, non una misura nel tuo punto.",
    methodForestTitle: "Bosco.",
    methodForest: "Quanta parte del quadrato è bosco, secondo la carta forestale di Copernicus.",
    methodGrid: "Il meteo arriva in aree di circa 11 per 8 km. Ogni quadrato sulla mappa misura 500 m. Molti quadrati condividono lo stesso meteo, quindi la loro piccola dimensione non dimostra che la stima sia precisa a quel livello di dettaglio.",
    methodShared: "Le stime di un'area si calcolano la prima volta che qualcuno la richiede in un giorno, poi vengono condivise con tutti i visitatori successivi. Chi apre l'area per primo può dover aspettare un momento.",
    diagramLabel: "Disegno: un'area meteo di circa 11 per 8 km contiene molti quadrati da 500 m, uno dei quali è scelto.",
    diagramArea: "Un'area meteo, circa 11 per 8 km",
    diagramSquare: "Un quadrato della mappa, 500 m",
    featuresTitle: "Che cosa puoi fare sulla mappa",
    feature1: "Scegliere tra otto date: oggi e i sette giorni successivi.",
    feature2: "Cercare un luogo, oppure usare la tua posizione se vuoi. La posizione è facoltativa.",
    feature3: "Usare due sfondi leggibili e regolare l'opacità dei quadrati colorati.",
    feature4: "Salvare i preferiti nel tuo browser, con un nome e un colore.",
    feature5: "Aprire il punto scelto nella tua app di navigazione.",
    feature6: "Usare la mappa in italiano o in inglese.",
    fragmentDates: "Seleziona data",
    fragmentLegend: "Legenda",
    fragmentLayers: "Sfondo e sovrapposizione",
    layerLight: "Chiaro",
    layerContrast: "Alto contrasto",
    layerOpacity: "Opacità della sovrapposizione",
    legendMissing: "Nessuna stima, dati mancanti",
    legendLessForest: "Meno del 10% di foresta",
    today: "Oggi",
    privateTitle: "Gratuito e privato",
    privateLead: "Nessun account, nessuna pubblicità, nessun abbonamento. Puoi usare tutta la mappa senza registrarti.",
    favoritesTitle: "I preferiti restano nel tuo browser",
    favoritesText: "Non si sincronizzano tra dispositivi e si perdono se cancelli i dati del browser.",
    sourcesTitle: "Fonti",
    source1Name: "Carta forestale di Copernicus.",
    source1Use: "Dice quanta parte di ogni quadrato è bosco.",
    source2Name: "Meteo modellato di Open-Meteo.",
    source2Use: "Dà la pioggia degli ultimi giorni e il meteo del giorno scelto.",
    source3Name: "Dati cartografici di OpenStreetMap.",
    source3Use: "Disegnano gli sfondi della mappa.",
    rulesTitle: "Prima di partire",
    rulesText: "Le regole per la raccolta dei funghi e i permessi dipendono dalla regione. Controllale prima di andare.",
    closingTitle: "Pronto a scegliere un bosco?"
  },
  en: {
    tagline: "Free, no account",
    openMap: "Open the map",
    sampleLabel: "Design example:",
    sampleText: "all values shown here are illustrative and are not from a live forecast.",
    noteLabel: "Experimental estimate:",
    noteText: "this percentage is unvalidated. It does not mean your personal chance of finding porcini.",
    heroTitle: "Choose a forest to explore for porcini",
    heroText: "Micometeo estimates the chance that porcini are growing in a 500 m forest square anywhere in Italy, including Sicily and Sardinia. You can read the estimate for today and for each of the next seven days. It is free, needs no account and shows no advertising.",
    mapLabel: "Example map of forest squares around Abetone, Tuscany",
    mapCaption: "Squares are coloured by today's estimate. The blue outline marks the selected square.",
    samplePlace: "Abetone, Tuscany",
    sampleToday: "Today, 12 October 2026",
    sampleLater: "Thursday 15 October",
    meaningTitle: "What the percentage means, and what it does not",
    meaningLead: "The percentage is the chance that porcini are growing somewhere inside the square on the day you pick.",
    meaningMissing: "If data is missing, that square has no estimate. The map says so in words and never shows 0%.",
    meansTitle: "What it means",
    means1: "The chance that porcini are growing somewhere inside the 500 m square, on the day you pick.",
    means2: "An experimental estimate that has not been validated.",
    notTitle: "What it does not mean",
    not1: "Your personal chance of finding porcini.",
    not2: "A promise of a mushroom at one point in the square.",
    not3: "A measured accuracy. The percentages have not been validated.",
    methodTitle: "How the estimate is made",
    methodIntro: "Each estimate uses three kinds of data.",
    methodRainTitle: "Rain.",
    methodRain: "The rain that fell in the last 7, 14 and 21 completed days.",
    methodWeatherTitle: "Weather of the day.",
    methodWeather: "Modelled weather for the day you choose, such as temperature. It is a calculation for an area, not a measurement at your point.",
    methodForestTitle: "Forest.",
    methodForest: "How much of the square is forest, from the Copernicus forest map.",
    methodGrid: "The weather comes in areas of about 11 by 8 km. Each square on the map is 500 m. Many squares share the same weather, so their small size does not prove that the estimate is accurate at that level of detail.",
    methodShared: "The estimates for an area are calculated the first time someone asks for it each day, then shared with every later visitor. The first visitor to open an area may wait a moment.",
    diagramLabel: "Drawing: one weather area of about 11 by 8 km holds many 500 m squares, and one of them is selected.",
    diagramArea: "One weather area, about 11 by 8 km",
    diagramSquare: "One map square, 500 m",
    featuresTitle: "What you can do on the map",
    feature1: "Choose from eight dates: today and the next seven days.",
    feature2: "Search for a place, or use your location if you want. Location is optional.",
    feature3: "Use two readable map backgrounds and change the opacity of the coloured squares.",
    feature4: "Save favorites in your browser, with a name and a colour.",
    feature5: "Open the selected point in your navigation app.",
    feature6: "Use the map in Italian or English.",
    fragmentDates: "Select date",
    fragmentLegend: "Legend",
    fragmentLayers: "Background and overlay",
    layerLight: "Light",
    layerContrast: "High contrast",
    layerOpacity: "Overlay opacity",
    legendMissing: "No estimate, data missing",
    legendLessForest: "Less than 10% forest",
    today: "Today",
    privateTitle: "Free and private",
    privateLead: "No account, no advertising, no subscription. You can use the whole map without signing up.",
    favoritesTitle: "Favorites stay in your browser",
    favoritesText: "They do not sync between devices, and they are lost if you clear your browser data.",
    sourcesTitle: "Sources",
    source1Name: "Copernicus forest map.",
    source1Use: "Says how much of each square is forest.",
    source2Name: "Open-Meteo modelled weather.",
    source2Use: "Gives the rain of recent days and the weather of the chosen day.",
    source3Name: "OpenStreetMap map data.",
    source3Use: "Draws the map backgrounds.",
    rulesTitle: "Before you go",
    rulesText: "Rules for picking mushrooms and permits depend on the region. Check them before you go.",
    closingTitle: "Ready to choose a forest?"
  }
};

var SCALE = [
  { fill: "#FFF8EC", it: "da 0 a 19%", en: "0 to 19%" },
  { fill: "#F6E3C3", it: "da 20 a 39%", en: "20 to 39%" },
  { fill: "#E9C99A", it: "da 40 a 59%", en: "40 to 59%" },
  { fill: "#D9AE76", it: "da 60 a 79%", en: "60 to 79%" },
  { fill: "#C8955A", it: "da 80 a 100%", en: "80 to 100%" }
];

var LAT = 44.1318;
var LNG = 10.6625;
var currentLang = "it";

function readLang() {
  var value = new URLSearchParams(window.location.search).get("lang");
  return value === "en" || value === "it" ? value : "it";
}

function fillText() {
  var copy = COPY[currentLang];
  document.querySelectorAll("[data-i18n]").forEach(function (node) {
    node.textContent = copy[node.getAttribute("data-i18n")];
  });
  document.querySelectorAll("[data-i18n-label]").forEach(function (node) {
    node.setAttribute("aria-label", copy[node.getAttribute("data-i18n-label")]);
  });
}

function renderChips() {
  var weekday = new Intl.DateTimeFormat(currentLang, { weekday: "short", timeZone: "UTC" });
  var day = new Intl.DateTimeFormat(currentLang, { day: "numeric", month: "short", timeZone: "UTC" });
  var row = document.getElementById("chip-row");
  row.textContent = "";
  for (var i = 0; i < 8; i++) {
    var date = new Date(Date.UTC(2026, 9, 12 + i));
    var item = document.createElement("li");
    item.className = i === 3 ? "chip chip-selected" : "chip";
    var top = document.createElement("span");
    top.textContent = i === 0 ? COPY[currentLang].today : weekday.format(date);
    var bottom = document.createElement("span");
    bottom.textContent = day.format(date);
    item.appendChild(top);
    item.appendChild(bottom);
    row.appendChild(item);
  }
}

function renderLegend() {
  var list = document.getElementById("legend");
  var copy = COPY[currentLang];
  list.textContent = "";
  var entries = SCALE.map(function (step) {
    return { cls: "", fill: step.fill, label: step[currentLang] };
  });
  entries.push({ cls: "legend-hatch", fill: "", label: copy.legendMissing });
  entries.push({ cls: "legend-dotted", fill: "", label: copy.legendLessForest });
  entries.forEach(function (entry) {
    var item = document.createElement("li");
    var swatch = document.createElement("span");
    swatch.className = "legend-swatch " + entry.cls;
    if (entry.fill) {
      swatch.style.background = entry.fill;
    }
    var label = document.createElement("span");
    label.textContent = entry.label;
    item.appendChild(swatch);
    item.appendChild(label);
    list.appendChild(item);
  });
}

function updateLinks() {
  document.querySelectorAll("[data-app-link]").forEach(function (link) {
    link.setAttribute("href", "app.html?lang=" + currentLang);
  });
  document.querySelectorAll("[data-lang-link]").forEach(function (link) {
    link.setAttribute("href", "landing.html?lang=" + currentLang);
  });
}

function setLang(lang, updateUrl) {
  currentLang = lang;
  document.documentElement.lang = lang;
  document.title = lang === "it" ? "Micometeo: scegli un bosco per i porcini" : "Micometeo: choose a forest for porcini";
  fillText();
  renderChips();
  renderLegend();
  updateLinks();
  document.querySelectorAll(".lang-button").forEach(function (button) {
    button.setAttribute("aria-pressed", String(button.getAttribute("data-lang") === lang));
  });
  if (updateUrl) {
    history.replaceState(null, "", "?lang=" + lang);
  }
}

function scaleFill(percent) {
  return SCALE[Math.min(4, Math.floor(percent / 20))].fill;
}

function addHatchPattern(map) {
  var svg = map.getContainer().querySelector("svg");
  if (!svg) {
    return;
  }
  var ns = "http://www.w3.org/2000/svg";
  var defs = document.createElementNS(ns, "defs");
  defs.innerHTML = "<pattern id=\"hatch\" width=\"6\" height=\"6\" patternUnits=\"userSpaceOnUse\" patternTransform=\"rotate(45)\">" +
    "<rect width=\"6\" height=\"6\" fill=\"#FFFFFF\" fill-opacity=\"0.5\"></rect>" +
    "<line x1=\"0\" y1=\"0\" x2=\"0\" y2=\"6\" stroke=\"#6B7373\" stroke-width=\"1.5\"></line></pattern>";
  svg.insertBefore(defs, svg.firstChild);
}

function buildPreviewMap() {
  var sample = window.MICOMETEO_SAMPLE;
  var mapNode = document.getElementById("preview-map");
  if (!window.L || !sample || !sample.squares || !sample.squares.length) {
    return;
  }
  mapNode.hidden = false;
  document.getElementById("preview-caption").hidden = false;

  var halfWidth = 4000 / (111320 * Math.cos(LAT * Math.PI / 180));
  var halfHeight = 3000 / 111320;
  var map = L.map(mapNode, {
    zoomControl: false,
    dragging: false,
    touchZoom: false,
    doubleClickZoom: false,
    scrollWheelZoom: false,
    boxZoom: false,
    keyboard: false,
    zoomSnap: 0.1
  });
  map.fitBounds([[LAT - halfHeight, LNG - halfWidth], [LAT + halfHeight, LNG + halfWidth]]);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; <a href=\"https://www.openstreetmap.org/copyright\">OpenStreetMap</a>"
  }).addTo(map);

  var selected = null;
  var squares = L.layerGroup().addTo(map);
  sample.squares.forEach(function (square) {
    var style = { weight: 1, color: "rgba(28, 35, 38, 0.25)", fillOpacity: 0.6, interactive: false };
    if (square.no_estimate_reason === "missing_data") {
      style.fillColor = "url(#hatch)";
      style.fillOpacity = 1;
      style.dashArray = "4 3";
      style.color = "#6B7373";
    } else if (square.no_estimate_reason === "less_forest") {
      style.fill = false;
      style.dashArray = "1 4";
      style.color = "#6B7373";
    } else if (square.estimates) {
      style.fillColor = scaleFill(square.estimates[0]);
    } else {
      return;
    }
    L.rectangle(square.bounds, style).addTo(squares);
    if (square.id === sample.selected_square_id) {
      selected = square;
    }
  });
  addHatchPattern(map);

  if (selected && selected.estimates) {
    L.rectangle(selected.bounds, { weight: 7, color: "#FFFFFF", fill: false, interactive: false }).addTo(map);
    L.rectangle(selected.bounds, {
      weight: 3,
      color: "#1F4E79",
      fillColor: scaleFill(selected.estimates[0]),
      fillOpacity: 0.6,
      interactive: false
    }).addTo(map);
  }
}

document.querySelectorAll(".lang-button").forEach(function (button) {
  button.addEventListener("click", function () {
    setLang(button.getAttribute("data-lang"), true);
  });
});

setLang(readLang(), false);
buildPreviewMap();
