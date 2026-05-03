// MapLibre dashboard for Coverage Gap Index.
// Loads MS county polygons + per-county aggregates + per-CAH summaries, renders
// a choropleth + CAH point overlay, wires click handlers to the side panel.

const SEVERITY_COLORS = {
  none: "#d0d0d0",
  low: "#27ae60",
  moderate: "#f1c40f",
  high: "#e67e22",
  critical: "#c0392b",
};

const MS_BBOX = [-91.66, 30.17, -88.10, 35.00];

(async function init() {
  const [counties, countyData, cahData] = await Promise.all([
    fetch("data/ms_counties.geojson").then(r => r.json()),
    fetch("data/county_aggregates.json").then(r => r.json()),
    fetch("data/cahs_summary.json").then(r => r.json()),
  ]);

  const countyByFips = Object.fromEntries(countyData.map(c => [c.fips, c]));
  const cahById = Object.fromEntries(cahData.map(c => [c.id, c]));

  // Stamp the per-county color onto each feature so MapLibre's data-driven
  // styling can read it without a join expression.
  for (const f of counties.features) {
    const fips = f.properties.fips;
    const c = countyByFips[fips];
    f.properties.bucket = c ? c.bucket : "none";
    f.properties.color = c ? c.color : SEVERITY_COLORS.none;
    f.properties.cah_count = c ? c.cah_count : 0;
    f.properties.max_gaps = c ? (c.max_gaps !== null ? c.max_gaps : -1) : -1;
  }

  const cahFeatures = cahData
    .filter(c => c.lat !== null && c.lon !== null)
    .map(c => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [c.lon, c.lat] },
      properties: {
        id: c.id,
        name: c.name,
        gap_count: c.gap_count,
        bucket: c.bucket,
        color: c.color,
        coord_source: c.coord_source,
      },
    }));

  const map = new maplibregl.Map({
    container: "map",
    style: "https://tiles.openfreemap.org/styles/positron",
    bounds: MS_BBOX,
    fitBoundsOptions: { padding: 30 },
    attributionControl: { compact: true },
  });

  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

  map.on("load", () => {
    map.addSource("counties", { type: "geojson", data: counties });

    map.addLayer({
      id: "counties-fill",
      type: "fill",
      source: "counties",
      paint: {
        "fill-color": ["get", "color"],
        "fill-opacity": 0.62,
      },
    });
    map.addLayer({
      id: "counties-line",
      type: "line",
      source: "counties",
      paint: {
        "line-color": "#888",
        "line-width": 0.5,
      },
    });
    map.addLayer({
      id: "counties-hover",
      type: "line",
      source: "counties",
      paint: {
        "line-color": "#1a1a1a",
        "line-width": 2,
      },
      filter: ["==", ["get", "fips"], ""],
    });

    // County name labels at moderate zoom so the YC partner can scan the map
    // without having to hover. OpenFreeMap Positron exposes "Noto Sans" glyphs.
    map.addLayer({
      id: "county-labels",
      type: "symbol",
      source: "counties",
      minzoom: 6.5,
      layout: {
        "text-field": ["get", "name"],
        "text-font": ["Noto Sans Regular"],
        "text-size": [
          "interpolate", ["linear"], ["zoom"],
          6.5, 9,
          8, 11,
          10, 13,
        ],
        "text-allow-overlap": false,
        "text-ignore-placement": false,
        "text-padding": 3,
        "text-letter-spacing": 0.04,
        "text-transform": "uppercase",
      },
      paint: {
        "text-color": "#3a3a3a",
        "text-halo-color": "rgba(255,255,255,0.92)",
        "text-halo-width": 1.4,
        "text-halo-blur": 0.4,
      },
    });

    map.addSource("cahs", {
      type: "geojson",
      data: { type: "FeatureCollection", features: cahFeatures },
    });

    // Invisible hit-area circle for accurate touch targets (44px). The visible
    // circle layer renders on top so it stays small visually while the tap
    // surface stays large.
    map.addLayer({
      id: "cahs-hit",
      type: "circle",
      source: "cahs",
      paint: {
        "circle-radius": 22,
        "circle-color": "#000",
        "circle-opacity": 0.001,
      },
    });

    map.addLayer({
      id: "cahs-circle",
      type: "circle",
      source: "cahs",
      paint: {
        "circle-radius": [
          "interpolate", ["linear"], ["zoom"],
          5, 5,
          8, 9,
          10, 13,
        ],
        "circle-color": ["get", "color"],
        "circle-stroke-color": [
          "case",
          ["==", ["get", "coord_source"], "zip_centroid"], "#ffffff",
          "#1a1a1a",
        ],
        "circle-stroke-width": [
          "case",
          ["==", ["get", "coord_source"], "zip_centroid"], 2.6,
          1.4,
        ],
        "circle-stroke-opacity": 0.95,
      },
    });

    map.on("click", "counties-fill", (e) => {
      if (!e.features || !e.features.length) return;
      const fips = e.features[0].properties.fips;
      openCounty(fips);
      window.location.hash = "county/" + fips;
    });
    map.on("click", "cahs-hit", (e) => {
      if (!e.features || !e.features.length) return;
      e.originalEvent.stopPropagation();
      const id = e.features[0].properties.id;
      openCah(id);
      window.location.hash = "cah/" + id;
    });

    map.on("mousemove", "counties-fill", (e) => {
      if (!e.features || !e.features.length) return;
      map.getCanvas().style.cursor = "pointer";
      map.setFilter("counties-hover", ["==", ["get", "fips"], e.features[0].properties.fips]);
    });
    map.on("mouseleave", "counties-fill", () => {
      map.getCanvas().style.cursor = "";
      map.setFilter("counties-hover", ["==", ["get", "fips"], ""]);
    });
    map.on("mouseenter", "cahs-hit", () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", "cahs-hit", () => {
      map.getCanvas().style.cursor = "";
    });

    handleHash();
  });

  function openCounty(fips) {
    const c = countyByFips[fips];
    if (!c) return;
    const cahsHere = c.cahs.map(id => cahById[id]).filter(Boolean);
    const subtitle = c.cah_count === 0
      ? "No federally designated Critical Access Hospital in this county."
      : `${c.cah_count} Critical Access Hospital${c.cah_count === 1 ? "" : "s"} in this county.`;
    const summary = c.max_gaps !== null
      ? `<p class="panel-summary">Worst hospital here has <strong>${c.max_gaps} of 15 specialties</strong> with HIGH or CRITICAL gaps within 30 miles.</p>`
      : "";
    const missing = c.top_missing.length
      ? `<h3>Most missing across CAHs</h3><ul>${c.top_missing.map(s => `<li>${escapeHtml(s)}</li>`).join("")}</ul>`
      : "";
    const cahLinks = cahsHere.length
      ? `<h3>Hospitals in county</h3><ul class="cah-list">${cahsHere.map(h => `<li><button class="link-btn" data-cah="${h.id}">${escapeHtml(h.name)}</button> &middot; ${h.gap_count} gap${h.gap_count === 1 ? "" : "s"}</li>`).join("")}</ul>`
      : "";
    setPanel(`
      <div class="panel-tag" style="background: ${c.color}">${labelForBucket(c.bucket)}</div>
      <h2>${escapeHtml(c.full_name || c.name + " County")}</h2>
      <p class="panel-meta">${subtitle}</p>
      ${summary}
      ${missing}
      ${cahLinks}
    `);
    document.querySelectorAll(".link-btn[data-cah]").forEach(btn => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-cah");
        openCah(id);
        window.location.hash = "cah/" + id;
      });
    });
  }

  function openCah(id) {
    const c = cahById[id];
    if (!c) return;

    // Group specialties: gaps (CRITICAL + HIGH) at top, COVERED + MODERATE in disclosure.
    const gaps = c.specialties.filter(s => s.level === "CRITICAL" || s.level === "HIGH");
    const others = c.specialties.filter(s => s.level === "MODERATE" || s.level === "COVERED");

    const summary = c.gap_count > 0
      ? `<p class="panel-summary"><strong>${c.gap_count} of 15 core specialties</strong> have HIGH or CRITICAL gaps within 30 miles.</p>`
      : `<p class="panel-summary">All 15 core specialties have at least 3 physicians within 30 miles.</p>`;

    const gapsHtml = gaps.length
      ? `<h3>Specialty gaps within 30 miles</h3>
         <ul class="gap-list">
           ${gaps.map(s => `
             <li>
               <span class="spec-name">${escapeHtml(s.label)}</span>
               <span class="spec-distance">
                 ${s.nearest_mi !== null ? "nearest " + s.nearest_mi + " mi" : "none in dataset"}
                 <span class="level-tag level-${s.level.toLowerCase()}">${s.level}</span>
               </span>
             </li>`).join("")}
         </ul>`
      : "";

    const othersHtml = others.length
      ? `<details class="spec-disclosure">
           <summary>Show ${others.length} covered specialt${others.length === 1 ? "y" : "ies"}</summary>
           <table class="spec-table">
             <thead><tr><th>Specialty</th><th>Status</th><th class="num">Physicians within 30mi</th><th class="num">Nearest</th></tr></thead>
             <tbody>${others.map(s => `
               <tr class="row-${s.level.toLowerCase()}">
                 <td>${escapeHtml(s.label)}</td>
                 <td><span class="badge badge-${s.level.toLowerCase()}">${s.level}</span></td>
                 <td class="num">${s.physician_count}</td>
                 <td class="num">${s.nearest_mi !== null ? s.nearest_mi + " mi" : "&mdash;"}</td>
               </tr>`).join("")}
             </tbody>
           </table>
         </details>`
      : "";

    setPanel(`
      <div class="panel-tag" style="background: ${c.color}">${labelForBucket(c.bucket)}</div>
      <h2>${escapeHtml(c.name)}</h2>
      <p class="panel-meta">${escapeHtml(c.city || "")}${c.county_name ? ", " + escapeHtml(c.county_name) + " County" : ""} &middot; Medicare provider ${c.id}</p>
      ${summary}
      ${gapsHtml}
      ${othersHtml}
    `);
  }

  function setPanel(html) {
    const panel = document.getElementById("side-panel");
    document.getElementById("side-content").innerHTML = html;
    panel.setAttribute("aria-hidden", "false");
    panel.classList.add("open");
    panel.scrollTop = 0;
  }

  function closePanel() {
    const panel = document.getElementById("side-panel");
    panel.classList.remove("open");
    panel.setAttribute("aria-hidden", "true");
    if (window.location.hash) history.replaceState(null, "", window.location.pathname);
  }

  function handleHash() {
    const h = window.location.hash.replace(/^#/, "");
    if (!h) return;
    const [kind, id] = h.split("/");
    if (kind === "county") openCounty(id);
    else if (kind === "cah") openCah(id);
  }

  function labelForBucket(b) {
    return ({
      none: "No CAH",
      low: "0-2 gaps",
      moderate: "3-5 gaps",
      high: "6-9 gaps",
      critical: "10+ gaps",
    })[b] || b;
  }

  function escapeHtml(s) {
    if (s === null || s === undefined) return "";
    return String(s).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
  }

  document.getElementById("side-close").addEventListener("click", closePanel);
  window.addEventListener("hashchange", handleHash);

  // Close on Escape for keyboard users.
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closePanel();
  });
})();
