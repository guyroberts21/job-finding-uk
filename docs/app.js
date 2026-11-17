(() => {
  "use strict";

  const DATA_URL = "data/jobs.json";
  const REFRESH_MS = 15 * 60 * 1000;
  const VISA_LABEL = {
    offered: "Sponsorship offered",
    not_offered: "No sponsorship",
    rtw_required: "Right to work needed",
    not_stated: "Not stated",
  };
  const $ = (id) => document.getElementById(id);
  const state = { data: null, generatedAt: null, cats: new Set(), open: new Set() };

  // ---------- safe DOM helpers (all job text is third-party, so never use innerHTML) ----------
  function el(tag, props, ...children) {
    const node = document.createElement(tag);
    if (props) {
      for (const [k, v] of Object.entries(props)) {
        if (v == null || v === false) continue;
        if (k === "class") node.className = v;
        else if (k === "text") node.textContent = v;
        else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
        else node.setAttribute(k, v === true ? "" : v);
      }
    }
    for (const c of children.flat()) {
      if (c == null || c === false) continue;
      node.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return node;
  }
  const safeUrl = (u) => (typeof u === "string" && /^https?:\/\//i.test(u) ? u : null);
  const extLink = (href, cls, text, label) =>
    safeUrl(href) ? el("a", { href, class: cls, target: "_blank", rel: "noopener noreferrer", "aria-label": label }, text) : null;

  // ---------- formatting ----------
  const todayISO = () => new Date().toISOString().slice(0, 10);
  function fmtDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  }
  function daysUntil(iso) {
    if (!iso) return null;
    return Math.round((new Date(iso + "T00:00:00") - new Date(todayISO() + "T00:00:00")) / 86400000);
  }
  function fmtMinutes(lo, hi) {
    const f = (m) => (m >= 60 ? (m % 60 ? `${(m / 60).toFixed(1)} h` : `${m / 60} h`) : `${m} min`);
    return `${f(lo)} – ${f(hi)}`;
  }
  function relTime(iso) {
    if (!iso) return "never";
    const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
    if (mins < 60) return `${Math.max(mins, 1)} min ago`;
    const h = Math.round(mins / 60);
    if (h < 36) return `${h} h ago`;
    return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  }
  const catLabel = (id) => (state.data?.meta?.categories || []).find((c) => c.id === id)?.label || id;
  const locLabel = (id) => (state.data?.meta?.locations || []).find((l) => l.id === id)?.label || id;

  // ---------- data ----------
  async function load(initial) {
    try {
      const res = await fetch(`${DATA_URL}?t=${Date.now()}`, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const changed = data?.meta?.generated_at !== state.generatedAt;
      if (!initial && changed && state.generatedAt) {
        const newIds = new Set((state.data?.jobs || []).map((j) => j.id));
        const added = (data.jobs || []).filter((j) => !newIds.has(j.id)).length;
        toast(added ? `Updated: ${added} new job${added === 1 ? "" : "s"}` : "Listings refreshed");
      }
      state.data = data;
      state.generatedAt = data?.meta?.generated_at || null;
      if (initial || changed) {
        buildFilterOptions();
        render();
      } else {
        renderHeader();
      }
    } catch (err) {
      $("updated").textContent = "Couldn't load job data";
      if (initial) {
        $("rows").replaceChildren(el("tr", null, el("td", { colspan: 8, class: "empty", text: `Couldn't load jobs (${err.message}). Try refreshing the page.` })));
      }
    }
  }

  function toast(msg) {
    const t = $("toast");
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => (t.hidden = true), 4000);
  }

  // ---------- filters ----------
  function buildFilterOptions() {
    const meta = state.data?.meta || {};
    const loc = $("loc");
    const keepLoc = loc.value;
    loc.replaceChildren(el("option", { value: "" }, "All locations"), ...(meta.locations || []).map((l) => el("option", { value: l.id }, l.label)));
    loc.value = keepLoc;

    const cats = $("cats");
    cats.replaceChildren(
      ...(meta.categories || []).map((c) =>
        el("button", {
          type: "button", class: "chip", "aria-pressed": String(state.cats.has(c.id)),
          onclick: (e) => {
            state.cats.has(c.id) ? state.cats.delete(c.id) : state.cats.add(c.id);
            e.currentTarget.setAttribute("aria-pressed", String(state.cats.has(c.id)));
            render();
          },
        }, c.label)
      )
    );
  }

  function readFilters() {
    return {
      q: $("q").value.trim().toLowerCase(),
      loc: $("loc").value,
      visa: $("visa").value,
      sort: $("sort").value,
      min: Number($("min").value),
      hideSenior: $("hideSenior").checked,
      newOnly: $("newOnly").checked,
      closingSoon: $("closingSoon").checked,
    };
  }

  function filtered() {
    const f = readFilters();
    const today = state.data?.meta?.date || todayISO();
    let jobs = (state.data?.jobs || []).filter((j) => {
      if ((j.match?.score ?? 0) < f.min) return false;
      if (f.hideSenior && j.level === "senior") return false;
      if (f.loc && !(j.areas || []).includes(f.loc)) return false;
      if (f.visa && j.sponsorship !== f.visa) return false;
      if (state.cats.size && !(j.categories || []).some((c) => state.cats.has(c))) return false;
      if (f.newOnly && j.first_seen !== today) return false;
      if (f.closingSoon) {
        const d = daysUntil(j.closing);
        if (d == null || d > 7) return false;
      }
      if (f.q) {
        const hay = [j.title, j.employer, j.location, j.summary, ...(j.responsibilities || []), ...(j.flags || [])].join(" ").toLowerCase();
        if (!f.q.split(/\s+/).every((w) => hay.includes(w))) return false;
      }
      return true;
    });
    const by = {
      match: (a, b) => b.match.score - a.match.score,
      closing: (a, b) => (a.closing || "9999").localeCompare(b.closing || "9999"),
      posted: (a, b) => (b.posted || "").localeCompare(a.posted || ""),
      salary: (a, b) => (b.salary_max || b.salary_min || 0) - (a.salary_max || a.salary_min || 0),
      time: (a, b) => a.process.minutes_low - b.process.minutes_low,
    }[f.sort];
    return jobs.sort((a, b) => by(a, b) || b.match.score - a.match.score);
  }

  // ---------- rendering ----------
  function renderHeader() {
    const meta = state.data?.meta || {};
    const upd = $("updated");
    upd.replaceChildren(
      el("span", { class: "dot", "aria-hidden": "true" }),
      meta.generated_at ? `Updated ${relTime(meta.generated_at)}` : "Waiting for the first daily update"
    );
    upd.title = meta.generated_at ? new Date(meta.generated_at).toLocaleString("en-GB") : "";

    const notice = $("notice");
    if (meta.status === "needs_api_keys") {
      notice.hidden = false;
      notice.replaceChildren(
        el("strong", null, "Almost ready: "),
        "the daily job feed needs its free API keys. Add ",
        el("code", null, "REED_API_KEY"), " (and optionally ", el("code", null, "ADZUNA_APP_ID"), " / ", el("code", null, "ADZUNA_APP_KEY"),
        ") as repository secrets, then run the “Daily job update” workflow. See the README for the 5-minute steps."
      );
    } else if (meta.errors && meta.errors.length && !(state.data.jobs || []).length) {
      notice.hidden = false;
      notice.textContent = `The last update hit errors: ${meta.errors.slice(0, 2).join("; ")}`;
    } else {
      notice.hidden = true;
    }
  }

  function renderStats(all) {
    const today = state.data?.meta?.date || todayISO();
    const items = [
      [all.length, "live roles"],
      [all.filter((j) => j.first_seen === today).length, "new today"],
      [all.filter((j) => { const d = daysUntil(j.closing); return d != null && d >= 0 && d <= 7; }).length, "closing this week"],
      [all.filter((j) => j.match.score >= 70).length, "strong matches (70%+)"],
    ];
    $("stats").replaceChildren(...items.map(([n, l]) => el("div", { class: "stat" }, el("div", { class: "n" }, n), el("div", { class: "l" }, l))));
  }

  function linkCheckText(lc) {
    if (!lc) return null;
    const map = { ok: "Link checked", blocked: "Open manually", unknown: "Not verified", skipped: "Not checked" };
    return el("span", { class: `check-state ${lc.state}`, title: `${lc.note || ""}${lc.checked ? ` · ${new Date(lc.checked).toLocaleString("en-GB")}` : ""}` }, map[lc.state] || lc.state);
  }

  function mainRow(j) {
    const today = state.data?.meta?.date || todayISO();
    const open = state.open.has(j.id);
    const days = daysUntil(j.closing);
    const lvl = `lvl-${j.match.level}`;
    const toggle = () => {
      state.open.has(j.id) ? state.open.delete(j.id) : state.open.add(j.id);
      render();
    };
    const tags = el("div", { class: "tags" },
      j.first_seen === today ? el("span", { class: "tag new" }, "New") : null,
      ...(j.categories || []).slice(0, 2).map((c) => el("span", { class: "tag cat" }, catLabel(c))),
      ...(j.flags || []).filter((f) => ["Mandarin/Chinese", "Remote/home-based", "Hybrid", "Driving licence"].includes(f)).map((f) => el("span", { class: "tag" }, f))
    );
    const lcListing = j.link_check?.listing;
    const lcApply = j.link_check?.apply;
    return el("tr", { class: `main${open ? " open" : ""}` },
      el("td", null, el("div", { class: `match ${lvl}`, title: (j.match.reasons || []).join("\n") },
        el("span", { class: "pct" }, `${j.match.score}%`),
        el("div", { class: "bar", "aria-hidden": "true" }, el("i", { style: `width:${j.match.score}%` })))),
      el("td", null,
        el("button", { type: "button", class: "role-title", "aria-expanded": String(open), onclick: toggle }, j.title),
        el("div", { class: "employer" }, j.employer),
        tags),
      el("td", null, j.location || "—", el("div", { class: "small" }, (j.areas || []).map(locLabel).join(", "))),
      el("td", null, j.salary || "Not stated", j.contract ? el("div", { class: "small" }, j.contract) : null),
      el("td", null,
        el("span", { class: days != null && days <= 7 ? "closing-soon" : "" }, j.closing ? fmtDate(j.closing) : "Not stated"),
        el("div", { class: "small" }, j.posted ? `Posted ${fmtDate(j.posted)}` : "")),
      el("td", null,
        el("div", null, j.process.type),
        el("div", { class: "small" }, `≈ ${fmtMinutes(j.process.minutes_low, j.process.minutes_high)}`)),
      el("td", null, el("span", { class: `visa ${j.sponsorship}` }, VISA_LABEL[j.sponsorship] || "Not stated")),
      el("td", null, el("div", { class: "links" },
        extLink(j.listing_url, "btn ghost", "View listing ↗", `View the full listing for ${j.title} (opens in a new tab)`),
        linkCheckText(lcListing),
        j.apply_url && j.apply_url !== j.listing_url ? extLink(j.apply_url, "btn primary", "Apply ↗", `Apply for ${j.title} on the employer's site (opens in a new tab)`) : null,
        lcApply ? linkCheckText(lcApply) : null,
        el("button", { type: "button", class: "link-btn", "aria-expanded": String(open), onclick: toggle }, open ? "Hide details" : "Details")
      ))
    );
  }

  function detailRow(j) {
    const p = j.process;
    return el("tr", { class: "detail" }, el("td", { colspan: 8 }, el("div", { class: "detail-grid" },
      el("div", { class: "panel" },
        el("h3", null, "Summary"),
        el("p", null, j.summary || "No summary available — open the listing."),
        !j.full_description && j.source === "Adzuna" ? el("p", { class: "small" }, "Adzuna only shares a short preview; see the listing for the full advert.") : null),
      el("div", { class: "panel" },
        el("h3", null, "Key responsibilities"),
        (j.responsibilities || []).length
          ? el("ul", null, ...j.responsibilities.map((r) => el("li", null, r)))
          : el("p", null, "Not listed in the advert preview — see the full listing.")),
      el("div", { class: "panel" },
        el("h3", null, "How to apply"),
        el("p", null, el("span", { class: "time-est" }, `≈ ${fmtMinutes(p.minutes_low, p.minutes_high)}`), ` · ${p.type}`),
        el("ol", null, ...p.steps.map((s) => el("li", null, s))),
        ...(p.notes || []).map((n) => el("p", { class: "small" }, n)),
        el("p", { class: "small" }, `Apply via: ${j.apply_via}`)),
      el("div", { class: "panel" },
        el("h3", null, `Match ${j.match.score}%`),
        el("ul", null, ...(j.match.reasons || []).map((r) => el("li", null, r))),
        (j.flags || []).length ? el("p", { class: "small" }, `Mentions: ${j.flags.join(", ")}`) : null,
        el("p", { class: "small" }, `Source: ${j.source} · First seen ${fmtDate(j.first_seen)} · Last confirmed live ${fmtDate(j.last_seen)}`),
        j.link_check?.listing ? el("p", { class: "small" }, `Listing check: ${j.link_check.listing.note || j.link_check.listing.state}`) : null,
        j.link_check?.apply ? el("p", { class: "small" }, `Apply-link check: ${j.link_check.apply.note || j.link_check.apply.state}`) : null)
    )));
  }

  function render() {
    renderHeader();
    const all = state.data?.jobs || [];
    renderStats(all);
    $("minval").textContent = `${$("min").value}%`;
    const jobs = filtered();
    $("count").textContent = `Showing ${jobs.length} of ${all.length} roles`;
    const rows = [];
    for (const j of jobs) {
      rows.push(mainRow(j));
      if (state.open.has(j.id)) rows.push(detailRow(j));
    }
    if (!rows.length) {
      const msg = all.length ? "No roles match these filters. Try lowering the minimum match or clearing a filter." : "No roles yet — the first daily update hasn't run.";
      rows.push(el("tr", null, el("td", { colspan: 8, class: "empty" }, msg)));
    }
    $("rows").replaceChildren(...rows);
  }

  // ---------- wiring ----------
  for (const id of ["q", "loc", "visa", "sort", "min", "hideSenior", "newOnly", "closingSoon"]) {
    $(id).addEventListener(id === "q" || id === "min" ? "input" : "change", render);
  }
  $("reset").addEventListener("click", () => {
    $("q").value = ""; $("loc").value = ""; $("visa").value = ""; $("sort").value = "match"; $("min").value = 40;
    $("hideSenior").checked = true; $("newOnly").checked = false; $("closingSoon").checked = false;
    state.cats.clear(); buildFilterOptions(); render();
  });

  load(true);
  setInterval(() => load(false), REFRESH_MS);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) load(false); });
  setInterval(renderHeader, 60 * 1000);
})();
