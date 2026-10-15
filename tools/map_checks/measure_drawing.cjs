const fs = require("fs");
const http = require("http");
const path = require("path");

const VIEW_NAMES = ["northern_apennines", "alps", "calabria"];
const DEFAULT_DATA_DIR = path.resolve("data/processed/map_checks");
const DEFAULT_OUTPUT = path.resolve(
  "data/processed/map_checks/sporameteo-map-drawing-measurements.json",
);
const DEFAULT_PROFILE_DIR = path.resolve("data/processed/map_checks/browser-profile");

function printHelp() {
  console.log(`Usage: node tools/map_checks/measure_drawing.cjs [options]

Options:
  --data-dir PATH             Saved GeoJSON directory.
  --output PATH               JSON report path.
  --profile-dir PATH          Persistent browser profile directory.
  --browser-executable PATH   Optional visible browser executable.
  --help                      Show this help.`);
}

function parseArguments(argv) {
  const values = {
    dataDir: DEFAULT_DATA_DIR,
    output: DEFAULT_OUTPUT,
    profileDir: DEFAULT_PROFILE_DIR,
    browserExecutable: null,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    const next = argv[index + 1];
    if (
      argument === "--data-dir" ||
      argument === "--output" ||
      argument === "--profile-dir" ||
      argument === "--browser-executable"
    ) {
      if (!next || next.startsWith("--")) {
        throw new Error(`${argument} needs a value.`);
      }
      if (argument === "--data-dir") values.dataDir = path.resolve(next);
      if (argument === "--output") values.output = path.resolve(next);
      if (argument === "--profile-dir") values.profileDir = path.resolve(next);
      if (argument === "--browser-executable") values.browserExecutable = next;
      index += 1;
      continue;
    }
    throw new Error(`Unknown argument: ${argument}`);
  }
  return values;
}

function contentType(filePath) {
  if (filePath.endsWith(".html")) return "text/html; charset=utf-8";
  if (filePath.endsWith(".js") || filePath.endsWith(".mjs")) return "application/javascript; charset=utf-8";
  if (filePath.endsWith(".css")) return "text/css; charset=utf-8";
  return "application/octet-stream";
}

function createServer({ dataDir }) {
  const pagePath = path.join(__dirname, "sporameteo-map-drawing.html");
  const maplibreDir = path.dirname(require.resolve("maplibre-gl/dist/maplibre-gl.mjs"));
  const assets = new Map([
    ["/sporameteo-map-drawing.html", pagePath],
    ["/maplibre-gl.css", path.join(maplibreDir, "maplibre-gl.css")],
  ]);
  for (const asset of ["maplibre-gl.mjs", "maplibre-gl-shared.mjs", "maplibre-gl-worker.mjs"]) {
    assets.set(`/${asset}`, path.join(maplibreDir, asset));
  }
  for (const name of VIEW_NAMES) {
    assets.set(`/sporameteo-map-${name}.geojson`, path.join(dataDir, `sporameteo-map-${name}.geojson`));
  }
  const server = http.createServer((request, response) => {
    const filePath = assets.get(request.url);
    if (!filePath || request.method !== "GET") {
      response.writeHead(404);
      response.end();
      return;
    }
    fs.createReadStream(filePath)
      .on("error", () => {
        response.writeHead(404);
        response.end();
      })
      .on("open", () => {
        response.writeHead(200, {"Content-Type": contentType(filePath), "Cache-Control": "no-store"});
      })
      .pipe(response);
  });
  return server;
}

function listen(server) {
  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      server.removeListener("error", reject);
      resolve(server.address().port);
    });
  });
}

async function main() {
  if (process.argv.slice(2).includes("--help")) {
    printHelp();
    return;
  }
  const args = parseArguments(process.argv.slice(2));
  const { chromium } = require("playwright");
  for (const name of VIEW_NAMES) {
    const filePath = path.join(args.dataDir, `sporameteo-map-${name}.geojson`);
    if (!fs.existsSync(filePath)) throw new Error(`Missing map response: ${filePath}`);
  }
  fs.mkdirSync(path.dirname(args.output), {recursive: true});
  fs.mkdirSync(args.profileDir, {recursive: true});
  const server = createServer({dataDir: args.dataDir});
  const port = await listen(server);
  let context = null;
  try {
    const launchOptions = {
      headless: false,
      viewport: {width: 1440, height: 900},
      deviceScaleFactor: 2,
    };
    if (args.browserExecutable) launchOptions.executablePath = args.browserExecutable;
    context = await chromium.launchPersistentContext(args.profileDir, launchOptions);
    const page = context.pages()[0] || await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${port}/sporameteo-map-drawing.html`);
    await page.waitForFunction(() => typeof window.runMeasurement === "function" && window.maplibregl);
    const results = [];
    for (const name of VIEW_NAMES) {
      for (let repeat = 0; repeat < 3; repeat += 1) {
        results.push(await page.evaluate(viewName => window.runMeasurement(viewName), name));
      }
    }
    if (errors.length) throw new Error(errors.join("\n"));
    const report = {
      browser: context.browser().version(),
      maplibre_version: results[0].maplibre_version,
      maplibre_package: {name: "maplibre-gl", version: results[0].maplibre_version},
      viewport: {width: 1440, height: 900, device_pixel_ratio: 2},
      headed: true,
      physical_phone: false,
      results,
    };
    fs.writeFileSync(args.output, `${JSON.stringify(report, null, 2)}\n`);
    console.log(JSON.stringify(report, null, 2));
    console.log(`Saved drawing measurement report to ${args.output}`);
  } finally {
    if (context) await context.close();
    await new Promise(resolve => server.close(resolve));
  }
}

main().catch(error => {
  console.error(error.message);
  process.exitCode = 1;
});
