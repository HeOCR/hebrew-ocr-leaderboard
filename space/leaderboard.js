"use strict";

const categories = {
  C1: "Modern unpointed print",
  C2: "Historical unpointed print",
  C3: "Modern pointed print",
  C4: "Historical pointed print",
  C5: "Modern handwriting",
  C6: "Historical handwriting",
};
const strata = {
  pooled: "Pooled page CER",
  archive: "Archive",
  "issuer-render": "Issuer render",
  "issuer-scan": "Issuer scan",
  scanner: "Office scanner",
  "phone-a": "Phone A",
  "phone-b": "Phone B",
};
const view = document.querySelector("#view");
const scope = document.querySelector("#scope");
const table = document.querySelector("#results");
const buttons = [];
let data;

function cell(tag, value, className = "") {
  const node = document.createElement(tag);
  node.textContent = value;
  if (className) node.className = className;
  return node;
}

function showCategory(id) {
  document.querySelector("#category-title").textContent = categories[id];
  document.querySelector("#scores").hidden = id !== "C1";
  document.querySelector("#coming").hidden = id === "C1";
  for (const button of buttons) button.setAttribute("aria-pressed", String(button.value === id));
}

function render() {
  const rows = data.rows.filter(row => !row.diagnostic).sort((a, b) => {
    const ma = a.views[view.value].pooled;
    const mb = b.views[view.value].pooled;
    return ma.edits / ma.chars - mb.edits / mb.chars || a.reader.localeCompare(b.reader) || a.id.localeCompare(b.id);
  });
  const body = document.createDocumentFragment();
  for (const row of rows) {
    const tr = document.createElement("tr");
    const heading = cell("th", row.reader);
    heading.scope = "row";
    tr.append(heading);
    for (const field of ["version", "type", "licence"]) tr.append(cell("td", row[field]));
    for (const key of Object.keys(strata)) {
      const metric = row.views[view.value][key];
      tr.append(cell("td", metric.chars ? `${(100 * metric.edits / metric.chars).toFixed(2)}%` : "—", "metric"));
    }
    tr.append(cell("td", row.date), cell("td", row.scorer_version, "scorer"), cell("td", row.verified ? "Verified" : "Self-submitted, unverified"));
    body.append(tr);
  }
  table.tBodies[0].replaceChildren(body);
  table.hidden = false;
  renderDiagnostics();
}

function renderDiagnostics() {
  const output = document.querySelector("#diagnostics");
  output.replaceChildren();
  for (const row of data.rows.filter(row => row.diagnostic)) {
    const details = row.diagnostic;
    const section = document.createElement("section");
    section.className = "diagnostic";
    const notice = cell("p", details.notice, "notice");
    const wrapper = document.createElement("div");
    wrapper.className = "table-wrap";
    const scores = document.createElement("table");
    const header = scores.createTHead().insertRow();
    for (const label of ["Scope", "Carriers", "Filtered page CER", "All page CER"]) {
      const heading = cell("th", label);
      heading.scope = "col";
      header.append(heading);
    }
    const body = scores.createTBody();
    for (const [label, count, views] of [
      ["Matched originals", details.paired_carriers, row.views],
      ["Artwork-masked carriers", details.masked_carriers, details.masked_views],
    ]) {
      const cells = body.insertRow();
      const heading = cell("th", label);
      heading.scope = "row";
      cells.append(heading, cell("td", count));
      for (const key of ["filtered", "all"]) {
        const { edits, chars } = views[key].pooled;
        cells.append(cell("td", `${(100 * edits / chars).toFixed(2)}%`, "metric"));
      }
    }
    wrapper.append(scores);
    section.append(cell("h2", `${row.reader} · ${row.version} · ${row.type}`), notice, wrapper);
    output.append(section);
  }
}

const efficiencyPlatform = document.querySelector("#efficiency-platform");
const executionLabels = {
  "native-tesseract": { measured: "Native Tesseract · measured" },
  "onnx-cpu": { "measured-cpu-variant": "ONNX CPU · measured variant" },
  "vertex-global-https": { "list-price-only": "Vertex global · list prices only" },
};

function renderEfficiency() {
  const panel = data?.efficiency;
  if (!panel?.rows.length) return;
  const readers = new Map(data.rows.map(row => [row.id, row.reader]));
  const rows = document.createDocumentFragment();
  const measure = (value, decimals) => value == null ? "—" : value.toFixed(decimals);

  for (const entry of panel.rows.filter(row => row.platform === efficiencyPlatform.value)) {
    const reader = readers.get(entry.reader_id);
    const execution = executionLabels[entry.execution]?.[entry.status];
    if (!reader || !execution) continue;
    const tr = document.createElement("tr");
    const readerLabel = entry.execution === "onnx-cpu" ? reader.replace(/ \(CUDA\)$/, "") : reader;
    const heading = cell("th", readerLabel);
    heading.scope = "row";
    const counts = entry.pages === null ? "—" : `${entry.pages} / ${entry.repetitions}`;
    const rates = entry.api_input_usd_per_million === null ? "—"
      : `${measure(entry.api_input_usd_per_million, 2)} / ${measure(entry.api_output_usd_per_million, 2)}`;
    tr.append(heading, cell("td", execution), cell("td", counts, "metric"));
    for (const value of [
      measure(entry.pages_per_minute, 2), measure(entry.peak_rss_mib, 2),
      measure(entry.marginal_usd_per_1000, 2), measure(entry.runner_hours_per_1000, 3),
      measure(entry.runner_usd_per_1000, 5), rates,
    ]) {
      tr.append(cell("td", value, "metric"));
    }
    rows.append(tr);
  }
  document.querySelector("#efficiency-rows").replaceChildren(rows);
  if (/^[a-f0-9]{40}$/.test(panel.source_commit)) {
    document.querySelector("#efficiency-source").href =
      `https://github.com/HeOCR/heocr-bench/tree/${panel.source_commit}/efficiency`;
  }
  document.querySelector("#efficiency").hidden = false;
}

efficiencyPlatform.addEventListener("change", renderEfficiency);

for (const [id, title] of Object.entries(categories)) {
  const button = cell("button", title);
  button.type = "button";
  button.value = id;
  button.setAttribute("aria-controls", "category");
  button.addEventListener("click", () => showCategory(id));
  document.querySelector("#categories").append(button);
  buttons.push(button);
}
showCategory("C1");
const columns = ["Reader", "Version", "Type", "Licence", ...Object.values(strata), "Date", "Scorer version", "Status"];
const header = table.tHead.insertRow();
for (const field of columns) {
  const th = cell("th", field);
  th.scope = "col";
  header.append(th);
}
view.addEventListener("change", render);

async function load() {
  try {
    const response = await fetch("results.json", { cache: "no-cache" });
    if (!response.ok) throw new Error("Results unavailable");
    data = await response.json();
    if (data.schema !== "heocr.leaderboard.results.v1") throw new Error("Unsupported results");
    render();
    renderEfficiency();
    scope.textContent = `${data.benchmark.pages} pages · ${data.benchmark.carriers} carriers · ${data.rows.filter(row => !row.diagnostic).length} ranked readers`;
    view.disabled = false;
  } catch {
    scope.textContent = "Results are temporarily unavailable.";
  }
}
load();
