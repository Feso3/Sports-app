/* NHL Player Cards - Frontend */

let allPlayers = [];
let currentCard = null;
let selectedSeason = null;

// ── Bootstrap ───────────────────────────────────────────────────────────────

async function init() {
  const [players, seasons] = await Promise.all([
    fetch("/api/players").then(r => r.json()),
    fetch("/api/seasons").then(r => r.json()),
  ]);

  allPlayers = players;

  const sel = document.getElementById("season-select");
  seasons.forEach(s => {
    const opt = document.createElement("option");
    const label = String(s);
    opt.value = s;
    opt.textContent = label.slice(0, 4) + "-" + label.slice(4);
    sel.appendChild(opt);
  });
  selectedSeason = seasons[0] || null;

  sel.addEventListener("change", () => {
    selectedSeason = parseInt(sel.value);
    if (currentCard) loadCard(currentCard.player_id);
  });

  setupSearch();
  setupTabs();
  setupShotMap();
}

// ── Search ──────────────────────────────────────────────────────────────────

function setupSearch() {
  const input = document.getElementById("search");
  const results = document.getElementById("search-results");

  input.addEventListener("input", () => {
    const q = input.value.trim().toLowerCase();
    if (q.length < 2) { results.hidden = true; return; }

    const matches = allPlayers
      .filter(p => p.full_name.toLowerCase().includes(q))
      .slice(0, 15);

    if (matches.length === 0) { results.hidden = true; return; }

    results.innerHTML = matches.map(p => `
      <div class="result-item" data-id="${p.player_id}">
        <span>${p.full_name}</span>
        <span class="result-meta">${p.position || ""} · ${p.current_team_abbrev || ""}</span>
      </div>
    `).join("");

    results.hidden = false;

    results.querySelectorAll(".result-item").forEach(el => {
      el.addEventListener("click", () => {
        const id = parseInt(el.dataset.id);
        input.value = el.querySelector("span").textContent;
        results.hidden = true;
        loadCard(id);
      });
    });
  });

  // Close results on outside click
  document.addEventListener("click", e => {
    if (!e.target.closest(".search-bar")) results.hidden = true;
  });
}

// ── Load Card ───────────────────────────────────────────────────────────────

async function loadCard(playerId) {
  const cardEl = document.getElementById("card");
  const emptyEl = document.getElementById("empty-state");
  const loadingEl = document.getElementById("loading");

  emptyEl.hidden = true;
  cardEl.hidden = true;
  loadingEl.hidden = false;

  let url = `/api/card/${playerId}`;
  if (selectedSeason) url += `?season=${selectedSeason}`;

  try {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error((await resp.json()).error || "Failed");
    currentCard = await resp.json();
    renderCard(currentCard);
    cardEl.hidden = false;
  } catch (e) {
    emptyEl.querySelector("p").textContent = "Error: " + e.message;
    emptyEl.hidden = false;
  } finally {
    loadingEl.hidden = true;
  }
}

// ── Render Card ─────────────────────────────────────────────────────────────

function renderCard(card) {
  // Identity
  document.getElementById("card-name").textContent = card.name;
  document.getElementById("card-position").textContent = card.position;
  document.getElementById("card-team").textContent = card.team;
  document.getElementById("card-number").textContent =
    card.number ? `#${card.number}` : "";
  document.getElementById("card-shoots").textContent =
    card.shoots ? `Shoots ${card.shoots}` : "";

  const ht = card.height_inches;
  const wt = card.weight_lbs;
  document.getElementById("card-size").textContent =
    ht ? `${Math.floor(ht/12)}'${ht%12}" ${wt || ""}lb` : "";

  // Score
  const scoreEl = document.getElementById("card-score");
  scoreEl.textContent = card.score_label;
  scoreEl.className = "score-value " +
    (card.player_score > 0 ? "positive" : card.player_score < 0 ? "negative" : "neutral");
  document.getElementById("card-score-label").textContent = "vs league avg";

  // Season stats
  renderSeasonStats(card);

  // Performance range
  renderPerformanceRange(card);

  // Splits (render the active tab)
  renderActiveSplit(card);

  // Reset shot map
  document.getElementById("shot-map-container").hidden = true;
  document.getElementById("shot-map-toggle").textContent = "Show Shot Map";
}

function renderSeasonStats(card) {
  const grid = document.getElementById("season-stats");

  if (card.is_goalie && card.goalie_stats) {
    const s = card.goalie_stats;
    grid.innerHTML = statCells([
      ["GP", s.games], ["W", s.wins], ["L", s.losses], ["OTL", s.otl],
      ["SV%", (s.save_pct * 100).toFixed(1)], ["GAA", s.gaa.toFixed(2)],
      ["SO", s.shutouts], ["SA", s.shots_against],
      ["TOI/G", s.avg_toi_minutes.toFixed(0) + "m"],
    ]);
  } else if (card.skater_stats) {
    const s = card.skater_stats;
    grid.innerHTML = statCells([
      ["GP", s.games], ["G", s.goals], ["A", s.assists], ["P", s.points],
      ["+/-", s.plus_minus], ["SH%", s.shooting_pct.toFixed(1)],
      ["SOG", s.shots], ["TOI/G", s.avg_toi_minutes.toFixed(0) + "m"],
      ["P/60", s.points_per_60.toFixed(2)], ["PPG", s.power_play_goals],
      ["GWG", s.game_winning_goals], ["HIT", s.hits],
    ]);
  }
}

function statCells(pairs) {
  return pairs.map(([label, val]) =>
    `<div class="stat-cell"><span class="stat-value">${val}</span><span class="stat-label">${label}</span></div>`
  ).join("");
}

// ── Performance Range ────────────────────────────────────────────────────────

function renderPerformanceRange(card) {
  const section = document.getElementById("performance-range-section");
  const container = document.getElementById("performance-range");

  if (!card.best_game || !card.worst_game) {
    section.hidden = true;
    return;
  }
  section.hidden = false;

  const best = card.best_game;
  const worst = card.worst_game;

  function fmtDate(dateStr) {
    if (!dateStr) return "—";
    const d = new Date(dateStr + "T12:00:00");
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  }

  function fmtContext(g) {
    const loc = g.is_home ? "vs" : "@";
    const opp = g.opponent || "?";
    return `${fmtDate(g.game_date)} · ${loc} ${opp}`;
  }

  const cells = card.is_goalie ? goalieRangeCells : skaterRangeCells;

  container.innerHTML = `
    <div class="range-grid">
      <div class="range-col">
        <div class="range-label range-label-best">Best Game</div>
        <div class="range-context">${fmtContext(best)}</div>
        <div class="stats-grid">${cells(best)}</div>
      </div>
      <div class="range-divider"></div>
      <div class="range-col">
        <div class="range-label range-label-worst">Worst Game</div>
        <div class="range-context">${fmtContext(worst)}</div>
        <div class="stats-grid">${cells(worst)}</div>
      </div>
    </div>
  `;
}

function skaterRangeCells(g) {
  const pm = g.plus_minus >= 0 ? `+${g.plus_minus}` : `${g.plus_minus}`;
  return statCells([
    ["G", g.goals],
    ["A", g.assists],
    ["P", g.points],
    ["+/-", pm],
    ["SOG", g.shots],
    ["TOI", Math.round(g.toi_minutes) + "m"],
  ]);
}

function goalieRangeCells(g) {
  const svPct = (g.save_pct * 100).toFixed(1) + "%";
  return statCells([
    ["SV%", svPct],
    ["SV", g.saves],
    ["SA", g.shots_against],
    ["GA", g.goals_against],
    ["Result", g.result || "—"],
  ]);
}

// ── Splits ──────────────────────────────────────────────────────────────────

function setupTabs() {
  document.querySelectorAll(".split-tab").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".split-tab").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      if (currentCard) renderActiveSplit(currentCard);
    });
  });
}

function renderActiveSplit(card) {
  const tab = document.querySelector(".split-tab.active").dataset.tab;
  const container = document.getElementById("split-content");

  if (tab === "period") renderPeriodSplit(card, container);
  else if (tab === "phase") renderPhaseSplit(card, container);
  else if (tab === "strength") renderStrengthSplit(card, container);
}

function renderPeriodSplit(card, el) {
  const splits = card.period_splits || [];
  if (splits.length === 0) { el.innerHTML = "<p>No shot data for this season.</p>"; return; }

  if (card.is_goalie) {
    const avg = card.league_goalie_avg;
    const leagueSvPct = avg ? (avg.save_pct * 100) : null;
    el.innerHTML = makeTable(
      ["Period", "SA", "GA", "SV", "SV%"],
      splits.map(s => {
        const pLabel = s.period <= 3 ? `P${s.period}` : `OT`;
        const svPct = s.save_pct;
        return [
          pLabel, s.shots_against, s.goals_against, s.saves,
          colorVal(svPct, leagueSvPct, true) + "%"
        ];
      })
    );
  } else {
    el.innerHTML = makeTable(
      ["Period", "Shots", "Goals", "SH%"],
      splits.map(s => {
        const pLabel = s.period <= 3 ? `P${s.period}` : `OT`;
        return [pLabel, s.shots, s.goals, s.shooting_pct.toFixed(1) + "%"];
      })
    );
  }
}

function renderPhaseSplit(card, el) {
  const splits = card.season_phase_splits || [];
  if (splits.length === 0) { el.innerHTML = "<p>No data.</p>"; return; }

  const order = ["early", "mid", "late", "playoffs"];
  const labels = { early: "Oct-Nov", mid: "Dec-Jan", late: "Feb-Apr", playoffs: "Playoffs" };
  const sorted = [...splits].sort((a, b) => order.indexOf(a.phase) - order.indexOf(b.phase));

  if (card.is_goalie) {
    el.innerHTML = makeTable(
      ["Phase", "GP", "W", "L", "SV%", "GAA"],
      sorted.map(s => [
        labels[s.phase] || s.phase, s.games, s.wins, s.losses,
        (s.save_pct * 100).toFixed(1) + "%", s.gaa.toFixed(2)
      ])
    );
  } else {
    el.innerHTML = makeTable(
      ["Phase", "GP", "G", "A", "P", "SH%", "P/60"],
      sorted.map(s => [
        labels[s.phase] || s.phase, s.games, s.goals, s.assists, s.points,
        s.shooting_pct.toFixed(1) + "%", s.points_per_60.toFixed(2)
      ])
    );
  }
}

function renderStrengthSplit(card, el) {
  const splits = card.strength_splits || [];
  if (splits.length === 0) { el.innerHTML = "<p>No shot data for this season.</p>"; return; }

  const labels = { even: "Even Strength", pp: "Power Play", sh: "Shorthanded" };

  if (card.is_goalie) {
    el.innerHTML = makeTable(
      ["Strength", "SA", "GA", "SV", "SV%"],
      splits.map(s => [
        labels[s.strength] || s.strength, s.shots_against, s.goals_against, s.saves,
        s.save_pct.toFixed(1) + "%"
      ])
    );
  } else {
    el.innerHTML = makeTable(
      ["Strength", "Shots", "Goals", "SH%"],
      splits.map(s => [
        labels[s.strength] || s.strength, s.shots, s.goals,
        s.shooting_pct.toFixed(1) + "%"
      ])
    );
  }
}

function makeTable(headers, rows) {
  return `<table class="split-table">
    <thead><tr>${headers.map(h => `<th>${h}</th>`).join("")}</tr></thead>
    <tbody>${rows.map(r => `<tr>${r.map(c => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody>
  </table>`;
}

function colorVal(val, baseline, higher_is_better) {
  if (baseline == null) return val.toFixed(1);
  const cls = (higher_is_better ? val > baseline : val < baseline)
    ? "highlight-good"
    : (higher_is_better ? val < baseline : val > baseline) ? "highlight-bad" : "";
  return `<span class="${cls}">${val.toFixed(1)}</span>`;
}

// ── Shot Map ────────────────────────────────────────────────────────────────

function setupShotMap() {
  document.getElementById("shot-map-toggle").addEventListener("click", () => {
    const container = document.getElementById("shot-map-container");
    const btn = document.getElementById("shot-map-toggle");
    if (container.hidden) {
      container.hidden = false;
      btn.textContent = "Hide Shot Map";
      if (currentCard) drawShotMap(currentCard);
    } else {
      container.hidden = true;
      btn.textContent = "Show Shot Map";
    }
  });
}

function drawShotMap(card) {
  const canvas = document.getElementById("rink-canvas");
  const ctx = canvas.getContext("2d");
  const W = canvas.width;
  const H = canvas.height;

  // NHL coords: x in [-100, 100], y in [-42.5, 42.5]
  // Map to canvas
  const scaleX = W / 200;
  const scaleY = H / 85;
  const toCanvasX = x => (x + 100) * scaleX;
  const toCanvasY = y => (42.5 - y) * scaleY;  // flip y

  ctx.clearRect(0, 0, W, H);

  // Draw rink
  drawRink(ctx, W, H, scaleX, scaleY, toCanvasX, toCanvasY);

  // Draw shots
  const shots = card.shots || [];
  if (shots.length === 0) {
    ctx.fillStyle = "#5a6a7a";
    ctx.font = "14px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("No shot data available", W / 2, H / 2);
    return;
  }

  // Draw non-goals first, then goals on top
  const nonGoals = shots.filter(s => !s.is_goal);
  const goals = shots.filter(s => s.is_goal);

  nonGoals.forEach(s => {
    ctx.beginPath();
    ctx.arc(toCanvasX(s.x), toCanvasY(s.y), 3, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(59, 130, 246, 0.35)";
    ctx.fill();
  });

  goals.forEach(s => {
    ctx.beginPath();
    ctx.arc(toCanvasX(s.x), toCanvasY(s.y), 4.5, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(52, 211, 153, 0.85)";
    ctx.fill();
  });
}

function drawRink(ctx, W, H, sx, sy, tx, ty) {
  // Background
  ctx.fillStyle = "#0f1822";
  ctx.fillRect(0, 0, W, H);

  ctx.strokeStyle = "#1e2a3a";
  ctx.lineWidth = 1;

  // Rink outline
  const r = 28 * sx;  // corner radius
  ctx.beginPath();
  ctx.moveTo(r, 0);
  ctx.lineTo(W - r, 0);
  ctx.arcTo(W, 0, W, r, r);
  ctx.lineTo(W, H - r);
  ctx.arcTo(W, H, W - r, H, r);
  ctx.lineTo(r, H);
  ctx.arcTo(0, H, 0, H - r, r);
  ctx.lineTo(0, r);
  ctx.arcTo(0, 0, r, 0, r);
  ctx.closePath();
  ctx.stroke();

  // Center line
  ctx.strokeStyle = "#2a1a1a";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(tx(0), 0);
  ctx.lineTo(tx(0), H);
  ctx.stroke();

  // Blue lines
  ctx.strokeStyle = "#1a2a4a";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(tx(25), 0);
  ctx.lineTo(tx(25), H);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(tx(-25), 0);
  ctx.lineTo(tx(-25), H);
  ctx.stroke();

  // Goal lines
  ctx.strokeStyle = "#2a1a1a";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(tx(89), 0);
  ctx.lineTo(tx(89), H);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(tx(-89), 0);
  ctx.lineTo(tx(-89), H);
  ctx.stroke();

  // Goal creases (simplified)
  ctx.strokeStyle = "#1a2a4a";
  ctx.lineWidth = 1;
  [89, -89].forEach(gx => {
    ctx.beginPath();
    ctx.arc(tx(gx), ty(0), 6 * sx, 0, Math.PI * 2);
    ctx.stroke();
  });

  // Center circle
  ctx.beginPath();
  ctx.arc(tx(0), ty(0), 15 * sx, 0, Math.PI * 2);
  ctx.strokeStyle = "#1e2a3a";
  ctx.stroke();
}

// ── Init ────────────────────────────────────────────────────────────────────

init();
