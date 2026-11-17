#!/usr/bin/env python3
"""Daily job fetcher.

Pulls live vacancies from the official Reed and Adzuna APIs, enriches each one
(summary, responsibilities, application process, time estimate, visa flag,
match %), checks that the links still work, merges with yesterday's data and
writes docs/data/jobs.json for the web page.

Standard library only, so the GitHub Action needs no installs.

Environment variables:
  REED_API_KEY                         - https://www.reed.co.uk/developers/jobseeker
  ADZUNA_APP_ID, ADZUNA_APP_KEY        - https://developer.adzuna.com
  JOBFINDER_FIXTURES=<dir>             - (tests only) read API responses from files
  JOBFINDER_SKIP_LINK_CHECK=1          - (tests only) skip live link checks
"""
from __future__ import annotations

import base64
import concurrent.futures as cf
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Optional local .env file (KEY=value lines) for running on your own machine. It's git-ignored.
_env_path = os.path.join(ROOT, ".env")
if os.path.exists(_env_path):
    for _line in open(_env_path, encoding="utf-8"):
        _k, _, _v = _line.strip().partition("=")
        if _k and not _k.startswith("#") and _v:
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))
SEARCHES = json.load(open(os.path.join(ROOT, "config", "searches.json"), encoding="utf-8"))
PROFILE = json.load(open(os.path.join(ROOT, "config", "profile.json"), encoding="utf-8"))
OUT_PATH = os.path.join(ROOT, "docs", "data", "jobs.json")
CACHE_PATH = os.path.join(ROOT, "data", "reed_details_cache.json")  # not published; saves API calls

FIXTURES = os.environ.get("JOBFINDER_FIXTURES")
SKIP_LINKS = os.environ.get("JOBFINDER_SKIP_LINK_CHECK") == "1"
TODAY = dt.date.fromisoformat(os.environ["JOBFINDER_TODAY"]) if os.environ.get("JOBFINDER_TODAY") else dt.date.today()
NOW_ISO = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()

API_UA = "job-finder-uk/1.0 (GitHub Action; personal job search)"
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def log(*args):
    print(*args, file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- HTTP

def http_json(url: str, headers: dict | None = None, retries: int = 2):
    req = urllib.request.Request(url, headers={"User-Agent": API_UA, "Accept": "application/json", **(headers or {})})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(3 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < retries:
                time.sleep(3 * (attempt + 1))
                continue
            raise


def fixture(name: str):
    path = os.path.join(FIXTURES, name)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------- text helpers

class _TextAndLists(HTMLParser):
    """Turns job-description HTML into plain text plus (heading, [list items]) groups."""
    BLOCK = {"p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self.buf: list[str] = []
        self.groups: list[tuple[str, list[str]]] = []
        self.last_heading = ""
        self.in_li = False
        self.li_buf: list[str] = []
        self.in_strong = False
        self.strong_buf: list[str] = []

    def _flush(self):
        text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        if text:
            self.lines.append(text)
            if len(text) < 90 and (text.endswith(":") or self._looks_heading(text)):
                self.last_heading = text
        self.buf = []

    @staticmethod
    def _looks_heading(text: str) -> bool:
        return bool(re.match(r"^(key |main |your |the )?(responsibilit|duties|role|what you|about you|requirements|skills|experience|benefits|you will|we are looking|person spec)", text, re.I))

    def handle_starttag(self, tag, attrs):
        if tag in ("ul", "ol"):
            self._flush()
            self.groups.append((self.last_heading, []))
        elif tag == "li":
            self._flush()
            self.in_li = True
            self.li_buf = []
        elif tag in ("strong", "b"):
            self.in_strong = True
            self.strong_buf = []
        elif tag in self.BLOCK:
            self._flush()

    def handle_endtag(self, tag):
        if tag == "li" and self.in_li:
            item = re.sub(r"\s+", " ", "".join(self.li_buf)).strip(" •-–•")
            if item:
                if not self.groups:
                    self.groups.append((self.last_heading, []))
                self.groups[-1][1].append(item)
                self.lines.append("• " + item)
            self.in_li = False
        elif tag in ("strong", "b"):
            self.in_strong = False
            s = re.sub(r"\s+", " ", "".join(self.strong_buf)).strip()
            if s and len(s) < 90:
                self.last_heading = s
        elif tag in self.BLOCK:
            self._flush()

    def handle_data(self, data):
        if self.in_li:
            self.li_buf.append(data)
        else:
            self.buf.append(data)
        if self.in_strong:
            self.strong_buf.append(data)

    def close(self):
        super().close()
        self._flush()


def parse_description(raw: str):
    raw = raw or ""
    if "<" not in raw:
        # Plain text (e.g. Adzuna). Treat bullet-ish lines as one list.
        text = html.unescape(raw)
        lines = [l.strip() for l in re.split(r"[\r\n]+", text) if l.strip()]
        items = [re.sub(r"^[•\-\*–]\s*", "", l) for l in lines if re.match(r"^[•\-\*–]\s+", l)]
        return " ".join(lines), ([("", items)] if items else [])
    p = _TextAndLists()
    try:
        p.feed(raw)
        p.close()
    except Exception:  # malformed HTML: fall back to tag stripping
        text = re.sub(r"<[^>]+>", " ", raw)
        return re.sub(r"\s+", " ", html.unescape(text)).strip(), []
    return " ".join(p.lines), [(h, items) for h, items in p.groups if items]


RESP_HEAD = re.compile(r"responsib|duties|the role|role will|you will|you'll|day[- ]to[- ]day|key tasks|what you('|’)ll (be )?do|main purpose|job purpose|what the job involves", re.I)
REQ_HEAD = re.compile(r"requir|skills|experience|about you|you will have|you'll (need|have|bring)|qualif|benefit|perks|we offer|what we offer|person spec|essential|desirable|criteria|package", re.I)
DUTY_VERB = re.compile(r"\b(support|supporting|manage|managing|coordinat|assist|deliver|create|creating|maintain|respond|process|organis|organiz|plan|planning|produce|write|writing|develop|answer|handle|provide|work with|liaise|update|monitor|run|help)\w*", re.I)


def extract_responsibilities(groups, text: str, limit: int = 6) -> list[str]:
    def clean(items):
        out = []
        for it in items:
            it = re.sub(r"\s+", " ", it).strip()
            if 12 <= len(it) <= 400:
                out.append(it if len(it) <= 180 else it[:177].rsplit(" ", 1)[0] + "…")
        return out

    for heading, items in groups:
        if RESP_HEAD.search(heading or "") and not REQ_HEAD.search(heading or ""):
            got = clean(items)
            if got:
                return got[:limit]
    for heading, items in groups:
        if not REQ_HEAD.search(heading or ""):
            got = [i for i in clean(items) if DUTY_VERB.search(i)]
            if len(got) >= 2:
                return got[:limit]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    picks = [s.strip() for s in sentences if 40 <= len(s) <= 220 and DUTY_VERB.search(s)
             and not re.search(r"\b(salary|apply|benefit|pension|holiday|we offer)\b", s, re.I)]
    return [p if len(p) <= 180 else p[:177].rsplit(" ", 1)[0] + "…" for p in picks[:4]]


BOILER = re.compile(r"^(job (title|type|reference)|salary|location|hours|contract|closing date|reference|ref)\b", re.I)


def make_summary(text: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.replace("• ", ""))
    out = []
    for s in sentences:
        s = s.strip()
        if len(s) < 40 or BOILER.match(s) or re.search(r"https?://|@\w", s):
            continue
        out.append(s)
        if len(" ".join(out)) > 220 or len(out) == 2:
            break
    summary = " ".join(out) or text[:300]
    return summary if len(summary) <= 340 else summary[:337].rsplit(" ", 1)[0] + "…"


# --------------------------------------------------------------------------- flags, process, score

def sponsorship_status(text: str) -> str:
    t = text.lower()
    if re.search(r"(unable|not able) to (offer|provide|consider)[^.]{0,30}sponsor|"
                 r"(cannot|can't|can not|do not|don't|will not|won't|does not|doesn't) (offer|provide|support)[^.]{0,30}sponsor|"
                 r"sponsorship (is )?(not|un)(available|offered|provided)|no (visa )?sponsorship|"
                 r"not (in a position|able) to sponsor|not (be )?open to sponsorship|without (visa )?sponsorship|"
                 r"(unable|not able) to accept applica\w+ (with|on|who (hold|require))[^.]{0,30}visa", t):
        return "not_offered"
    if re.search(r"(visa )?sponsorship (is |will be )?(available|offered|provided|considered)|"
                 r"(we|will|can) (offer|provide|consider) (visa )?sponsorship|skilled worker (visa )?sponsor|"
                 r"sponsorship[^.]{0,20}(benefit|available)", t):
        return "offered"
    if re.search(r"(must|will need to|need to) (already )?have (the |a )?(full |existing )?right to work|"
                 r"right to work in the uk (is )?(required|essential)", t):
        return "rtw_required"
    return "not_stated"


FLAG_RULES = [
    ("Driving licence", r"driving licen[cs]e|access to (a|your own|own) (car|vehicle)"),
    ("DBS check", r"\bdbs\b|disclosure and barring"),
    ("Mandarin/Chinese", r"\b(mandarin|cantonese|chinese)\b"),
    ("Portfolio requested", r"\bportfolio\b"),
    ("Cover letter", r"cover(ing)? letter"),
    # ("Person specification" alone is just a section heading, so it isn't counted.)
    ("Supporting statement", r"supporting statement|personal statement|statement (of|in) support"),
    ("No CVs accepted", r"(cvs?|curriculum vitae) (will not|won't|are not|is not) (be )?(accepted|considered)|we do not accept cvs|no cvs"),
    ("Assessment/test", r"\b(assessment|test|task|presentation) (will|may) (be|form)|online test|skills test|written exercise"),
    ("Weekend/evening work", r"\b(weekends?|evenings?) (work|working|may be required|as required)|work (some )?(weekends|evenings)"),
    ("Hybrid", r"\bhybrid\b"),
    ("Remote/home-based", r"\b(fully remote|remote working|home[- ]based|work from home|wfh)\b"),
]


def flags_for(text: str) -> list[str]:
    t = text.lower()
    return [label for label, pat in FLAG_RULES if re.search(pat, t)]


PORTALS = {
    "webitrent.com": "council / public-sector portal (iTrent)",
    "jobs.ac.uk": "jobs.ac.uk university portal",
    "trac.jobs": "NHS (Trac) application form",
    "jobs.nhs.uk": "NHS Jobs application form",
    "successfactors": "SuccessFactors portal",
    "myworkdayjobs.com": "Workday portal",
    "taleo.net": "Taleo portal",
    "tribepad": "Tribepad portal",
    "eploy": "Eploy portal",
    "networxrecruitment": "Networx portal",
    "engageats": "online application form",
    "jobtrain": "Jobtrain portal",
    "oleeo": "Oleeo portal",
    "civilservicejobs": "Civil Service Jobs form",
    "greenhouse.io": "Greenhouse form",
    "lever.co": "Lever form",
    "workable.com": "Workable form",
    "smartrecruiters.com": "SmartRecruiters form",
    "jotform.com": "online form",
    "teamtailor.com": "Teamtailor form",
    "applytojob.com": "JazzHR form",
    "bamboohr.com": "BambooHR form",
}
HEAVY_PORTALS = {"webitrent.com", "jobs.ac.uk", "trac.jobs", "jobs.nhs.uk", "civilservicejobs", "jobtrain", "oleeo", "engageats", "networxrecruitment"}


def domain_of(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def estimate_process(text: str, apply_url: str, source: str, external: bool, flags: list[str]) -> dict:
    t = text.lower()
    dom = domain_of(apply_url)
    portal_key = next((k for k in PORTALS if k in dom), None)
    # Only count an application form when the advert tells you to fill one in, not when it's one of the duties.
    app_form = re.search(r"(complete|completing|fill in|fill out|submit|download|request|questions on|apply (using|via|on|with)) "
                         r"(the |an |our |your )?(online )?application (form|pack)|"
                         r"application (form|pack)s? (is|are|can be|must|should|will|available)", t) is not None
    reed_internal = source == "Reed" and not external
    form_heavy = ("Supporting statement" in flags or "No CVs accepted" in flags
                  or (app_form and not reed_internal)
                  or (portal_key in HEAVY_PORTALS))
    steps: list[str] = []
    notes: list[str] = []

    if form_heavy:
        kind = "Application form + supporting statement"
        low, high = 120, 180
        if portal_key:
            steps.append(f"Create an account on the {PORTALS[portal_key]}")
        elif re.search(r"application pack", t):
            steps.append("Request or download the application pack")
        steps += ["Fill in personal details, education and employment history",
                  "Write a supporting statement against the person specification (STAR examples)",
                  "Complete the equality monitoring form and submit"]
    elif (source != "Reed" or external) and re.search(r"(email|send) (your|a) (cv|c\.v\.)|cvs? (should be )?(emailed|sent) to", t):
        # (On Reed, "send your CV" means Reed's Apply button: Reed strips email addresses from adverts.)
        kind = "Email CV + covering letter"
        low, high = 40, 70
        steps += ["Tailor the CV to the advert", "Write a short covering email or letter", "Email both to the address in the advert"]
    elif external and portal_key:
        kind = f"Online portal ({PORTALS[portal_key]})"
        low, high = 45, 90
        steps += ["Create an account on the employer's portal", "Upload a tailored CV and fill in the form",
                  "Answer any screening questions, then submit"]
    elif external:
        kind = "Apply on employer / agency website"
        low, high = 30, 75
        steps += ["Open the apply link (employer or agency site)", "Upload a tailored CV and complete the form",
                  "Answer any screening questions, then submit"]
    elif source == "Reed":
        kind = "Quick apply on Reed (CV)"
        low, high = 15, 30
        steps += ["Sign in to Reed", "Upload the tailored CV", "Add a short cover note, then submit"]
    else:
        kind = "Via Adzuna to the employer / agency site"
        low, high = 30, 75
        steps += ["Open the listing (Adzuna forwards you to the advertiser)", "Follow the advertiser's apply steps",
                  "Upload a tailored CV and submit"]

    if app_form and reed_internal and not form_heavy:
        # On Reed an "application form" means the screening questions after you press Apply.
        steps.insert(max(len(steps) - 1, 0), "Answer the application questions in full")
        low, high = low + 15, high + 30
    if "Cover letter" in flags and "covering" not in " ".join(steps).lower():
        steps.insert(max(len(steps) - 1, 0), "Write a tailored cover letter")
        low, high = low + 30, high + 45
    if "Portfolio requested" in flags:
        steps.insert(max(len(steps) - 1, 0), "Add a portfolio link")
        low, high = low + 10, high + 20
    if "Assessment/test" in flags:
        notes.append("The advert mentions an assessment, test or task")
    if re.search(r"\bcv\b[^.]{0,25}\b(word document|word format|in word|\.docx?)\b", t):
        notes.append("The advert asks for the CV as a Word document")
    if "DBS check" in flags:
        notes.append("A DBS check is mentioned (usually after an offer)")
    notes.append("Times include tailoring the CV/statement; first-time portal sign-ups take longer")
    return {"type": kind, "steps": steps, "minutes_low": low, "minutes_high": high, "notes": notes}


def _term_regex(term: str) -> re.Pattern:
    return re.compile(r"(?<![a-z])" + re.escape(term.lower()) + r"(?![a-z])")


SKILL_RX = [(g["label"], g["weight"], [_term_regex(t) for t in g["terms"]]) for g in PROFILE["skill_groups"]]


def match_score(title: str, text: str, category_ids: list[str]) -> dict:
    blob = f"{title} {text}".lower()
    tl = title.lower()
    matched, weight = [], 0
    for label, w, rxs in SKILL_RX:
        if any(rx.search(blob) for rx in rxs):
            matched.append(label)
            weight += w
    base = min(70.0, weight / PROFILE["score_target_weight"] * 70.0)
    reasons = [f"Skills overlap: {', '.join(matched[:6])}"] if matched else ["Little overlap with the CV skills"]
    score = base
    for b in PROFILE["bonuses"]:
        if re.search(b["pattern"], blob):
            score += b["points"]
            reasons.append(f"+ {b['label']}")
    if any(re.search(r"\b" + re.escape(t) + r"\b", tl) for t in PROFILE["title_boost_terms"]):
        score += PROFILE["title_boost_points"]
        reasons.append("+ Junior-friendly job title")
    for p in PROFILE["penalties"]:
        target = tl if p.get("field") == "title" else blob
        if re.search(p["pattern"], target):
            score -= p["points"]
            reasons.append(f"− {p['label']}")
    score = int(max(3, min(97, round(score))))
    level = "strong" if score >= 70 else "good" if score >= 50 else "stretch" if score >= 35 else "weak"
    return {"score": score, "level": level, "reasons": reasons}


def seniority(title: str) -> str:
    t = title.lower()
    if re.search(r"\b(senior|head of|director|principal|lead|manager)\b", t):
        return "senior"
    if re.search(r"\b(assistant|junior|trainee|graduate|apprentice|intern|entry)\b", t):
        return "entry"
    return "mid"


# --------------------------------------------------------------------------- sources

def parse_uk_date(s: str | None) -> str | None:
    if not s:
        return None
    s = s.strip()
    for candidate, fmt in ((s, "%d/%m/%Y"), (s[:19], "%Y-%m-%dT%H:%M:%S"), (s[:10], "%Y-%m-%d")):
        try:
            return dt.datetime.strptime(candidate, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def money(v) -> int | None:
    try:
        return int(float(v)) if v not in (None, "", 0) else None
    except (TypeError, ValueError):
        return None


def salary_text(lo, hi, predicted=False) -> str:
    lo, hi = money(lo), money(hi)
    if not lo and not hi:
        return "Not stated"
    fmt = lambda n: f"£{n:,}"
    s = fmt(lo) if lo and (not hi or lo == hi) else f"{fmt(lo)}–{fmt(hi)}" if lo and hi else f"up to {fmt(hi)}"
    return s + (" (est.)" if predicted else "")


REMOTE_RX = re.compile(r"\b(remote|home[- ]based|work from home|working from home|wfh)\b", re.I)


def reed_auth(key: str) -> dict:
    return {"Authorization": "Basic " + base64.b64encode(f"{key}:".encode()).decode()}


def reed_search(key, keywords, loc) -> list[dict]:
    if FIXTURES:
        return (fixture(f"reed_search_{loc['id']}.json") or {}).get("results", [])
    params = {"keywords": keywords + (" remote" if loc.get("remote") else ""),
              "resultsToTake": SEARCHES["reed_results_per_search"]}
    if loc.get("reed"):
        params["locationName"] = loc["reed"]
        params["distanceFromLocation"] = loc["distance"]
    url = "https://www.reed.co.uk/api/1.0/search?" + urllib.parse.urlencode(params)
    return http_json(url, reed_auth(key)).get("results", []) or []


def reed_details(key, job_id) -> dict:
    if FIXTURES:
        return fixture(f"reed_details_{job_id}.json") or {}
    return http_json(f"https://www.reed.co.uk/api/1.0/jobs/{job_id}", reed_auth(key)) or {}


def adzuna_search(app_id, app_key, phrase, loc) -> list[dict]:
    if FIXTURES:
        return (fixture(f"adzuna_search_{loc['id']}.json") or {}).get("results", [])
    params = {"app_id": app_id, "app_key": app_key, "what_phrase": phrase,
              "results_per_page": SEARCHES["adzuna_results_per_search"],
              "max_days_old": SEARCHES["max_days_old"], "content-type": "application/json"}
    if loc.get("remote"):
        params["what_or"] = "remote home-based homeworking"
    else:
        params["where"] = loc["adzuna"]
        params["distance"] = loc["distance"]
    url = "https://api.adzuna.com/v1/api/jobs/gb/search/1?" + urllib.parse.urlencode(params)
    return http_json(url).get("results", []) or []


def excluded_title(title: str) -> bool:
    t = title.lower()
    return any(term in t for term in SEARCHES["exclude_title_terms"])


def norm_key(title: str, employer: str) -> str:
    f = lambda s: re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()
    return f"{f(title)}|{f(employer)}"


def collect_reed(key: str, errors: list) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for cat in SEARCHES["categories"]:
        for kw in cat["keywords"]:
            for loc in SEARCHES["locations"]:
                try:
                    results = reed_search(key, kw, loc)
                except Exception as e:  # keep going on one bad search
                    errors.append(f"Reed '{kw}' / {loc['label']}: {e}")
                    continue
                for r in results:
                    title = (r.get("jobTitle") or "").strip()
                    if not title or excluded_title(title):
                        continue
                    snippet = html.unescape(r.get("jobDescription") or "")
                    if loc.get("remote") and not REMOTE_RX.search(f"{title} {snippet} {r.get('locationName','')}"):
                        continue
                    jid = f"reed-{r.get('jobId')}"
                    item = found.setdefault(jid, {"raw": r, "categories": set(), "areas": set()})
                    item["categories"].add(cat["id"])
                    item["areas"].add(loc["id"])
                if not FIXTURES:
                    time.sleep(0.25)
    return found


def collect_adzuna(app_id: str, app_key: str, errors: list) -> dict[str, dict]:
    found: dict[str, dict] = {}
    calls_left = SEARCHES.get("adzuna_max_calls_per_run", 20)  # free/test keys have small daily limits
    for cat in SEARCHES["categories"]:
        for kw in cat.get("adzuna_keywords", cat["keywords"][:1]):
            for loc in SEARCHES["locations"]:
                if calls_left <= 0:
                    return found
                calls_left -= 1
                try:
                    results = adzuna_search(app_id, app_key, kw, loc)
                except Exception as e:
                    errors.append(f"Adzuna '{kw}' / {loc['label']}: {e}")
                    continue
                for r in results:
                    title = html.unescape(r.get("title") or "").strip()
                    if not title or excluded_title(title):
                        continue
                    if loc.get("remote") and not REMOTE_RX.search(f"{title} {r.get('description','')}"):
                        continue
                    jid = f"adzuna-{r.get('id')}"
                    item = found.setdefault(jid, {"raw": r, "categories": set(), "areas": set()})
                    item["categories"].add(cat["id"])
                    item["areas"].add(loc["id"])
                if not FIXTURES:
                    time.sleep(0.4)
    return found


def build_job(jid: str, source: str, raw: dict, details: dict | None, categories, areas, prev: dict | None) -> dict | None:
    if source == "Reed":
        d = details or {}
        title = html.unescape((d.get("jobTitle") or raw.get("jobTitle") or "").strip())
        employer = html.unescape(d.get("employerName") or raw.get("employerName") or "")
        location = d.get("locationName") or raw.get("locationName") or ""
        desc_html = d.get("jobDescription") or raw.get("jobDescription") or ""
        listing_url = d.get("jobUrl") or raw.get("jobUrl") or f"https://www.reed.co.uk/jobs/{raw.get('jobId')}"
        external = (d.get("externalUrl") or "").strip()
        # Reed's API fills externalUrl with the Reed listing itself when there's no employer link,
        # so only treat it as external when it points somewhere other than reed.co.uk.
        if not external.startswith("http") or domain_of(external).endswith("reed.co.uk"):
            external = ""
        apply_url = external or listing_url
        posted = parse_uk_date(d.get("datePosted") or raw.get("date"))
        closing = parse_uk_date(d.get("expirationDate") or raw.get("expirationDate"))
        lo = d.get("yearlyMinimumSalary") or d.get("minimumSalary") or raw.get("minimumSalary")
        hi = d.get("yearlyMaximumSalary") or d.get("maximumSalary") or raw.get("maximumSalary")
        sal = d.get("salary") if isinstance(d.get("salary"), str) and d.get("salary") else salary_text(lo, hi)
        contract = ", ".join(x for x in [d.get("contractType"), "Part-time" if d.get("partTime") else ("Full-time" if d.get("fullTime") else None)] if x)
        apply_via = f"Employer site ({domain_of(external)})" if external else "Reed (quick apply)"
        detail_ok = bool(details)
    else:
        title = html.unescape(raw.get("title") or "").strip()
        employer = html.unescape((raw.get("company") or {}).get("display_name") or "")
        location = (raw.get("location") or {}).get("display_name") or ""
        desc_html = raw.get("description") or ""
        listing_url = raw.get("redirect_url") or ""
        apply_url = listing_url
        external = listing_url
        posted = parse_uk_date(raw.get("created"))
        closing = None
        lo, hi = raw.get("salary_min"), raw.get("salary_max")
        sal = salary_text(lo, hi, str(raw.get("salary_is_predicted")) == "1")
        contract = ", ".join(x.replace("_", "-").title() for x in [raw.get("contract_type"), raw.get("contract_time")] if x)
        apply_via = "Adzuna → advertiser"
        detail_ok = False

    if not title or not listing_url.startswith("http"):
        return None
    text, groups = parse_description(desc_html)
    flags = flags_for(text)
    match = match_score(title, text, sorted(categories))
    process = estimate_process(text, apply_url, source, bool(external) and source == "Reed", flags)
    job = {
        "id": jid,
        "source": source,
        "title": title,
        "employer": employer or "Not stated",
        "location": location,
        "areas": sorted(areas),
        "categories": sorted(categories),
        "salary": sal,
        "salary_min": money(lo),
        "salary_max": money(hi),
        "contract": contract,
        "posted": posted,
        "closing": closing,
        "listing_url": listing_url,
        "apply_url": apply_url,
        "apply_via": apply_via,
        "summary": make_summary(text),
        "responsibilities": extract_responsibilities(groups, text),
        "full_description": detail_ok,
        "process": process,
        "sponsorship": sponsorship_status(text),
        "flags": flags,
        "level": seniority(title),
        "match": match,
        "first_seen": (prev or {}).get("first_seen") or TODAY.isoformat(),
        "last_seen": TODAY.isoformat(),
        "link_check": (prev or {}).get("link_check") or {},
    }
    return job


# --------------------------------------------------------------------------- link checks

CLOSED_RX = re.compile(r"this (job|vacancy|position) (has )?(now )?(expired|closed)|no longer (accepting applications|available|advertised)|"
                       r"vacancy (has )?(now )?closed|position has been filled|job (is )?no longer available|this listing has expired", re.I)


def check_url(url: str, retries: int = 2) -> dict:
    result = {"checked": NOW_ISO, "status": None, "state": "unknown", "note": ""}
    if not url.startswith("http"):
        result.update(state="broken", note="Not a web link")
        return result
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA, "Accept": "text/html,application/xhtml+xml",
                                               "Accept-Language": "en-GB,en;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            result["status"] = resp.status
            body = resp.read(250_000).decode("utf-8", "ignore")
            if CLOSED_RX.search(body):
                result.update(state="closed", note="Page says the vacancy has closed")
            else:
                result.update(state="ok", note="Page loaded")
    except urllib.error.HTTPError as e:
        result["status"] = e.code
        if e.code == 429 and retries > 0:  # rate-limited: back off and try again
            try:
                wait = min(int(e.headers.get("Retry-After") or 0), 30)
            except ValueError:
                wait = 0
            time.sleep(wait or 10)
            return check_url(url, retries - 1)
        if e.code in (404, 410):
            result.update(state="broken", note=f"Page not found ({e.code})")
        elif e.code in (401, 403, 429, 999):
            result.update(state="blocked", note=f"Site blocks automated checks ({e.code}); open it manually")
        else:
            result.update(state="unknown", note=f"HTTP {e.code}")
    except Exception as e:
        result.update(state="unknown", note=f"Could not reach page: {type(e).__name__}")
    return result


def run_link_checks(jobs: list[dict]):
    if SKIP_LINKS:
        for j in jobs:
            j["link_check"] = {"listing": {"checked": NOW_ISO, "status": None, "state": "skipped", "note": "Test run"}}
        return
    # Group by site and check each site's links one at a time with a pause, so busy sites like
    # reed.co.uk don't rate-limit us. Different sites are still checked in parallel.
    by_host: dict[str, list] = {}
    for j in jobs:
        j["link_check"] = {}
        by_host.setdefault(domain_of(j["listing_url"]), []).append((j, "listing", j["listing_url"]))
        if j["apply_url"] != j["listing_url"]:
            by_host.setdefault(domain_of(j["apply_url"]), []).append((j, "apply", j["apply_url"]))

    def check_host(host, items):
        pause = 1.0 if "reed.co.uk" in host or "adzuna" in host else 0.5
        for i, (j, kind, url) in enumerate(items):
            if i:
                time.sleep(pause)
            j["link_check"][kind] = check_url(url)

    with cf.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda kv: check_host(*kv), by_host.items()))


# --------------------------------------------------------------------------- main

def load_previous() -> tuple[dict, dict]:
    try:
        with open(OUT_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return {j["id"]: j for j in data.get("jobs", [])}, data.get("meta", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}, {}


def write_output(jobs: list[dict], meta: dict):
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    payload = {"meta": meta, "jobs": jobs}
    tmp = OUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    os.replace(tmp, OUT_PATH)


def main() -> int:
    reed_key = os.environ.get("REED_API_KEY", "").strip()
    az_id = os.environ.get("ADZUNA_APP_ID", "").strip()
    az_key = os.environ.get("ADZUNA_APP_KEY", "").strip()
    if FIXTURES:
        reed_key = reed_key or "fixture"
        az_id, az_key = az_id or "fixture", az_key or "fixture"

    previous, prev_meta = load_previous()
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        cache = {}
    errors: list[str] = []
    sources_used = []

    if not reed_key and not (az_id and az_key):
        log("No API keys set - keeping existing data.")
        meta = {**prev_meta, "status": "needs_api_keys", "last_attempt": NOW_ISO,
                "message": "Add the REED_API_KEY (and optionally ADZUNA_APP_ID / ADZUNA_APP_KEY) repository secrets, then re-run the workflow."}
        meta.setdefault("generated_at", None)
        meta["categories"] = [{"id": c["id"], "label": c["label"]} for c in SEARCHES["categories"]]
        meta["locations"] = [{"id": l["id"], "label": l["label"]} for l in SEARCHES["locations"]]
        write_output(list(previous.values()), meta)
        return 0

    raw: dict[str, tuple[str, dict]] = {}
    if reed_key:
        sources_used.append("Reed")
        for jid, item in collect_reed(reed_key, errors).items():
            raw[jid] = ("Reed", item)
    if az_id and az_key:
        sources_used.append("Adzuna")
        for jid, item in collect_adzuna(az_id, az_key, errors).items():
            raw[jid] = ("Adzuna", item)
    log(f"Collected {len(raw)} raw listings; {len(errors)} search errors")

    # Rank Reed listings by snippet score so detail lookups go to the best ones first.
    def snippet_score(entry):
        src, item = entry[1]
        r = item["raw"]
        title = r.get("jobTitle") or r.get("title") or ""
        return match_score(title, html.unescape(r.get("jobDescription") or r.get("description") or ""), [])["score"]

    ordered = sorted(raw.items(), key=snippet_score, reverse=True)
    detail_budget = SEARCHES["max_detail_lookups_per_run"]
    jobs: dict[str, dict] = {}
    dedupe: dict[str, str] = {}
    max_age = TODAY - dt.timedelta(days=SEARCHES["max_days_old"])

    for jid, (source, item) in ordered:
        prev = previous.get(jid)
        details = None
        if source == "Reed":
            if jid in cache:
                details = cache[jid]
            elif detail_budget > 0:
                try:
                    details = reed_details(reed_key, item["raw"].get("jobId"))
                    detail_budget -= 1
                    if not FIXTURES:
                        time.sleep(0.2)
                except Exception as e:
                    errors.append(f"Reed details {item['raw'].get('jobId')}: {e}")
        job = build_job(jid, source, item["raw"], details, item["categories"], item["areas"], prev)
        if not job:
            continue
        if job["closing"] and job["closing"] < TODAY.isoformat():
            continue
        if job["posted"] and job["posted"] < max_age.isoformat():
            continue
        if job["match"]["score"] < SEARCHES["min_score_to_keep"]:
            continue
        key = norm_key(job["title"], job["employer"])
        if key in dedupe:  # same job on both sources: keep Reed (it has closing dates + full text)
            existing = jobs[dedupe[key]]
            existing["areas"] = sorted(set(existing["areas"]) | set(job["areas"]))
            existing["categories"] = sorted(set(existing["categories"]) | set(job["categories"]))
            if existing["source"] == "Reed" or job["source"] != "Reed":
                continue
            del jobs[dedupe[key]]
        dedupe[key] = jid
        if source == "Reed" and details:
            cache[jid] = {k: details.get(k) for k in (
                "jobTitle", "employerName", "locationName", "jobDescription", "jobUrl", "externalUrl", "datePosted",
                "expirationDate", "yearlyMinimumSalary", "yearlyMaximumSalary", "minimumSalary", "maximumSalary",
                "salary", "contractType", "partTime", "fullTime")}
        jobs[jid] = job

    # Keep recently-seen jobs that dropped out of today's search results (API pages shift day to day).
    keep_after = (TODAY - dt.timedelta(days=SEARCHES["keep_unseen_days"])).isoformat()
    for jid, prev in previous.items():
        if jid in jobs or excluded_title(prev.get("title", "")):
            continue
        if prev.get("source") == "Reed" and jid in cache:
            # Rebuild from the cached advert so carried-over jobs pick up any rule or config changes.
            rebuilt = build_job(jid, "Reed", {"jobId": jid.removeprefix("reed-"), "jobTitle": prev.get("title")},
                                cache[jid], prev.get("categories") or [], prev.get("areas") or [], prev)
            if rebuilt:
                rebuilt["last_seen"] = prev.get("last_seen") or rebuilt["last_seen"]
                prev = rebuilt
        if (prev.get("match") or {}).get("score", 0) < SEARCHES["min_score_to_keep"]:
            continue
        if prev.get("last_seen", "") >= keep_after and not (prev.get("closing") and prev["closing"] < TODAY.isoformat()):
            jobs[jid] = prev

    job_list = list(jobs.values())
    run_link_checks(job_list)
    # Drop listings whose own page is gone or says it has closed.
    job_list = [j for j in job_list if j.get("link_check", {}).get("listing", {}).get("state") not in ("broken", "closed")]
    job_list.sort(key=lambda j: (-j["match"]["score"], j.get("closing") or "9999"))

    new_today = sum(1 for j in job_list if j["first_seen"] == TODAY.isoformat())
    meta = {
        "status": "ok" if job_list or not errors else "error",
        "generated_at": NOW_ISO,
        "last_attempt": NOW_ISO,
        "date": TODAY.isoformat(),
        "sources": sources_used,
        "total": len(job_list),
        "new_today": new_today,
        "errors": errors[:20],
        "categories": [{"id": c["id"], "label": c["label"]} for c in SEARCHES["categories"]],
        "locations": [{"id": l["id"], "label": l["label"]} for l in SEARCHES["locations"]],
    }
    write_output(job_list, meta)
    live_ids = {j["id"] for j in job_list}
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in cache.items() if k in live_ids}, f, ensure_ascii=False)
    log(f"Wrote {len(job_list)} jobs ({new_today} new). Errors: {len(errors)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
