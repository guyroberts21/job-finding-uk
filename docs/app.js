(() => {
  "use strict";

  const DATA_URL = "data/jobs.json";
  const REFRESH_MS = 15 * 60 * 1000;
  const I = window.I18N;
  const t = (k, v) => I.t(k, v);
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
  // Job text stays in its original language; mark it so screen readers pronounce it correctly in Chinese mode.
  const en = (tag, props, ...kids) => el(tag, { ...(props || {}), lang: "en" }, ...kids);

  // ---------- formatting ----------
  const todayISO = () => new Date().toISOString().slice(0, 10);
  function fmtDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString(I.locale(), { day: "numeric", month: "short" });
  }
  function daysUntil(iso) {
    if (!iso) return null;
    return Math.round((new Date(iso + "T00:00:00") - new Date(todayISO() + "T00:00:00")) / 86400000);
  }
  function fmtMinutes(lo, hi) {
    const f = (m) => (m >= 60 ? t("hours", { n: m % 60 ? (m / 60).toFixed(1) : m / 60 }) : t("minutes", { n: m }));
    return `${f(lo)} – ${f(hi)}`;
  }
  function relTime(iso) {
    if (!iso) return "";
    const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
    if (mins < 60) return t("minAgo", { n: Math.max(mins, 1) });
    const h = Math.round(mins / 60);
    if (h < 36) return t("hAgo", { n: h });
    return new Date(iso).toLocaleDateString(I.locale(), { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  }
  const catLabel = (id) => I.category(id, (state.data?.meta?.categories || []).find((c) => c.id === id)?.label || id);
  const locLabel = (id) => I.place(id, (state.data?.meta?.locations || []).find((l) => l.id === id)?.label || id);
  const visaLabel = (s) => t(`visa.${s}`) || t("visa.not_stated");

  // ---------- data ----------
  async function load(initial) {
    try {
      const res = await fetch(`${DATA_URL}?t=${Date.now()}`, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const changed = data?.meta?.generated_at !== state.generatedAt;
      if (!initial && changed && state.generatedAt) {
        const oldIds = new Set((state.data?.jobs || []).map((j) => j.id));
        const added = (data.jobs || []).filter((j) => !oldIds.has(j.id)).length;
        toast(added ? t(added === 1 ? "toastNew" : "toastNewPlural", { n: added }) : t("toastRefreshed"));
      }
      state.data = data;
      state.generatedAt = data?.meta?.generated_at || null;
      if (initial || changed) {
        buildFilterOptions();
        renderFooter();
        render();
      } else {
        renderHeader();
      }
    } catch (err) {
      $("updated").textContent = t("loadFailed");
      if (initial) {
        $("rows").replaceChildren(el("tr", null, el("td", { colspan: 8, class: "empty", text: t("loadFailedRow", { err: err.message }) })));
      }
    }
  }

  function toast(msg) {
    const box = $("toast");
    box.textContent = msg;
    box.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => (box.hidden = true), 4000);
  }

  // ---------- filters ----------
  function buildFilterOptions() {
    const meta = state.data?.meta || {};
    const loc = $("loc");
    const keepLoc = loc.value;
    loc.replaceChildren(el("option", { value: "" }, t("allLocations")), ...(meta.locations || []).map((l) => el("option", { value: l.id }, locLabel(l.id))));
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
        }, catLabel(c.id))
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
    const jobs = (state.data?.jobs || []).filter((j) => {
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
        const hay = [j.title, j.employer, j.location, j.summary, ...(j.responsibilities || []), ...(j.flags || []),
          ...(j.flags || []).map(I.tx)].join(" ").toLowerCase();
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
      meta.generated_at ? t("updatedAgo", { when: relTime(meta.generated_at) }) : t("waitingFirst")
    );
    upd.title = meta.generated_at ? new Date(meta.generated_at).toLocaleString(I.locale()) : "";

    const notice = $("notice");
    if (meta.status === "needs_api_keys") {
      notice.hidden = false;
      notice.replaceChildren(
        el("strong", null, t("noticeKeysLead")),
        t("noticeKeys1"),
        el("code", null, "REED_API_KEY"), t("noticeKeys2"), el("code", null, "ADZUNA_APP_ID"), " / ", el("code", null, "ADZUNA_APP_KEY"),
        t("noticeKeys3")
      );
    } else if (meta.errors && meta.errors.length && !(state.data.jobs || []).length) {
      notice.hidden = false;
      notice.textContent = t("noticeErrors", { errors: meta.errors.slice(0, 2).join("; ") });
    } else {
      notice.hidden = true;
    }
  }

  function renderStats(all) {
    const today = state.data?.meta?.date || todayISO();
    const items = [
      [all.length, t("stat.live")],
      [all.filter((j) => j.first_seen === today).length, t("stat.new")],
      [all.filter((j) => { const d = daysUntil(j.closing); return d != null && d >= 0 && d <= 7; }).length, t("stat.closing")],
      [all.filter((j) => j.match.score >= 70).length, t("stat.strong")],
    ];
    $("stats").replaceChildren(...items.map(([n, l]) => el("div", { class: "stat" }, el("div", { class: "n" }, n), el("div", { class: "l" }, l))));
  }

  function linkCheckText(lc) {
    if (!lc) return null;
    const label = ["ok", "blocked", "unknown", "skipped", "closed", "broken"].includes(lc.state) ? t(`check.${lc.state}`) : lc.state;
    const when = lc.checked ? ` · ${new Date(lc.checked).toLocaleString(I.locale())}` : "";
    return el("span", { class: `check-state ${lc.state}`, title: `${I.tx(lc.note || "")}${when}` }, label);
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
      j.first_seen === today ? el("span", { class: "tag new" }, t("tagNew")) : null,
      ...(j.categories || []).slice(0, 2).map((c) => el("span", { class: "tag cat" }, catLabel(c))),
      ...(j.flags || []).filter((f) => ["Mandarin/Chinese", "Remote/home-based", "Hybrid", "Driving licence"].includes(f)).map((f) => el("span", { class: "tag" }, I.tx(f)))
    );
    const lcListing = j.link_check?.listing;
    const lcApply = j.link_check?.apply;
    return el("tr", { class: `main${open ? " open" : ""}` },
      el("td", null, el("div", { class: `match ${lvl}`, title: (j.match.reasons || []).map(I.reason).join("\n") },
        el("span", { class: "pct" }, `${j.match.score}%`),
        el("div", { class: "bar", "aria-hidden": "true" }, el("i", { style: `width:${j.match.score}%` })))),
      el("td", null,
        en("button", { type: "button", class: "role-title", "aria-expanded": String(open), onclick: toggle }, j.title),
        en("div", { class: "employer" }, j.employer),
        tags),
      el("td", null, en("span", null, j.location || "—"), el("div", { class: "small" }, (j.areas || []).map(locLabel).join(t("listSep")))),
      el("td", { class: "col-salary" }, I.salary(j.salary || "Not stated"), j.contract ? el("div", { class: "small" }, I.contract(j.contract)) : null),
      el("td", { class: "col-closes" },
        el("span", { class: days != null && days <= 7 ? "closing-soon" : "" }, j.closing ? fmtDate(j.closing) : t("notStated")),
        el("div", { class: "small" }, j.posted ? t("posted", { date: fmtDate(j.posted) }) : "")),
      el("td", { class: "col-app" },
        el("div", null, I.tx(j.process.type)),
        el("div", { class: "small" }, `≈ ${fmtMinutes(j.process.minutes_low, j.process.minutes_high)}`)),
      el("td", null, el("span", { class: `visa ${j.sponsorship}` }, visaLabel(j.sponsorship))),
      el("td", null, el("div", { class: "links" },
        extLink(j.listing_url, "btn ghost", t("viewListing"), t("viewListingAria", { title: j.title })),
        linkCheckText(lcListing),
        j.apply_url && j.apply_url !== j.listing_url ? extLink(j.apply_url, "btn primary", t("apply"), t("applyAria", { title: j.title })) : null,
        lcApply ? linkCheckText(lcApply) : null,
        el("button", { type: "button", class: "link-btn", "aria-expanded": String(open), onclick: toggle }, open ? t("hideDetails") : t("details"))
      ))
    );
  }

  function detailRow(j) {
    const p = j.process;
    return el("tr", { class: "detail" }, el("td", { colspan: 8 }, el("div", { class: "detail-grid" },
      el("div", { class: "panel" },
        el("h3", null, t("panel.summary")),
        j.summary ? en("p", null, j.summary) : el("p", null, t("noSummary")),
        !j.full_description && j.source !== "Reed" ? el("p", { class: "small" }, t("shortPreview", { source: j.source })) : null),
      el("div", { class: "panel" },
        el("h3", null, t("panel.resp")),
        (j.responsibilities || []).length
          ? en("ul", null, ...j.responsibilities.map((r) => el("li", null, r)))
          : el("p", null, t("noResp"))),
      el("div", { class: "panel" },
        el("h3", null, t("panel.apply")),
        el("p", null, el("span", { class: "time-est" }, `≈ ${fmtMinutes(p.minutes_low, p.minutes_high)}`), ` · ${I.tx(p.type)}`),
        el("ol", null, ...p.steps.map((s) => el("li", null, I.tx(s)))),
        ...(p.notes || []).map((n) => el("p", { class: "small" }, I.tx(n))),
        el("p", { class: "small" }, t("applyVia", { via: I.tx(j.apply_via) }))),
      el("div", { class: "panel" },
        el("h3", null, t("panel.match", { score: j.match.score })),
        el("ul", null, ...(j.match.reasons || []).map((r) => el("li", null, I.reason(r)))),
        (j.flags || []).length ? el("p", { class: "small" }, t("mentions", { list: j.flags.map(I.tx).join(t("listSep")) })) : null,
        el("p", { class: "small" }, t("sourceLine", { source: j.source, first: fmtDate(j.first_seen), last: fmtDate(j.last_seen) })),
        j.link_check?.listing ? el("p", { class: "small" }, t("listingCheck", { note: I.tx(j.link_check.listing.note) || j.link_check.listing.state })) : null,
        j.link_check?.apply ? el("p", { class: "small" }, t("applyCheck", { note: I.tx(j.link_check.apply.note) || j.link_check.apply.state })) : null)
    )));
  }

  const SOURCE_LINKS = {
    Reed: ["https://www.reed.co.uk", "reedJobs"],
    Adzuna: ["https://www.adzuna.co.uk", "adzunaJobs"],
    Jooble: ["https://uk.jooble.org", "joobleJobs"],
  };

  function renderFooter() {
    const a = (href, text) => el("a", { href, target: "_blank", rel: "noopener noreferrer" }, text);
    const used = (state.data?.meta?.sources || ["Reed", "Adzuna"]).filter((s) => SOURCE_LINKS[s]);
    const parts = [];
    used.forEach((s, i) => {
      if (i) parts.push(i === used.length - 1 ? t("footer1b") : t("listSep"));
      parts.push(a(SOURCE_LINKS[s][0], t(SOURCE_LINKS[s][1])));
    });
    $("footer").replaceChildren(
      el("p", null, t("footer1a"), ...parts, t("footer1c")),
      el("p", null, t("footer2"))
    );
  }

  function render() {
    renderHeader();
    const all = state.data?.jobs || [];
    renderStats(all);
    $("minval").textContent = `${$("min").value}%`;
    const jobs = filtered();
    $("count").textContent = t("count", { shown: jobs.length, total: all.length });
    const rows = [];
    for (const j of jobs) {
      rows.push(mainRow(j));
      if (state.open.has(j.id)) rows.push(detailRow(j));
    }
    if (!rows.length) {
      rows.push(el("tr", null, el("td", { colspan: 8, class: "empty" }, all.length ? t("emptyFiltered") : t("emptyNone"))));
    }
    $("rows").replaceChildren(...rows);
  }

  function switchLang(next) {
    I.setLang(next);
    renderFooter();
    if (state.data) {
      buildFilterOptions();
      render();
    } else {
      $("updated").textContent = t("loading");
    }
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
  document.querySelectorAll(".lang-btn").forEach((b) => b.addEventListener("click", () => switchLang(b.dataset.lang)));

  I.applyStatic();
  renderFooter();
  $("updated").textContent = t("loading");
  load(true);
  setInterval(() => load(false), REFRESH_MS);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) load(false); });
  setInterval(renderHeader, 60 * 1000);
})();
