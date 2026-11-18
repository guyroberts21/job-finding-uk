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
import xml.etree.ElementTree as ET
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

def http_json(url: str, headers: dict | None = None, retries: int = 2, body: dict | None = None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    hdrs = {"User-Agent": API_UA, "Accept": "application/json", **({"Content-Type": "application/json"} if data else {}), **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST" if data else "GET")
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
                 r"(does not|doesn't|will not|won't) attract (visa )?sponsorship|not eligible for (visa )?sponsorship|"
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


# --------------------------------------------------------------------------- required qualifications
# Pulls out degrees and qualifications the advert asks for, so the site can warn before you click through.
# Each one is tagged essential / desirable / training (offered on the job) / stated (no wording either way).

REQ_SPLIT = re.compile(r"\s*(?:[•·▪●◦*]+|(?<=[.!?;])\s+(?=[A-Z0-9])|\s[-–]\s(?=[A-Z]))\s*")
REQ_SKIP = re.compile(r"equal opportunit|regardless of|all (suitably )?qualified|qualified (candidates|applicants|individuals|advisors)|"
                      r"depending on (experience|qualifications)|no (degree|qualifications?) (is )?(required|needed|necessary)|"
                      r"(degree|qualifications?) (is |are )?not (required|necessary|needed)|without a degree|don'?t need (a degree|qualifications)", re.I)
DEGREE_WORD = re.compile(r"\bdegrees?\b(?!\s+of\b)|\bundergraduate\b|\bbachelor|\bmaster'?s (degree|level)|\bpostgraduate (degree|qualification)|"
                         r"\b(educated to|degree[- ])level\b", re.I)
DEGREE_ABBR = re.compile(r"\b(BA|BSc|LLB|MSc|MA|BEng|MEng|PhD|MBA)\b(?= (\(Hons\) )?in\b| degree| or equivalent)")
DEGREE_360 = re.compile(r"\b\d+\s*degrees?\b", re.I)
DEGREE_SUBJ = re.compile(r"\b(?:degrees?|BA|BSc|MSc|MA|LLB|qualification|educated|equivalent|studies)\b(?:(?!\b(?:and|with|plus|fluen\w*|experience|skills|knowledge|working)\b)[^.;:]){0,30}?\bin\s+"
                         r"(?!order\b|line\b|addition\b|which\b|this\b|our\b|your\b|their\b|place\b|time\b|hand\b|the uk\b)(.{3,100})", re.I)
DEGREE_PREFIX = re.compile(r"\b((?:[A-Z][a-z]+ ){0,2}[A-Z][a-z]+) (?:[Dd]egree|BA|BSc)\b")
PREFIX_NOISE = {"A", "An", "The", "Your", "Our", "University", "Undergraduate", "Honours", "Hons", "Bachelor", "Bachelors", "Master", "Masters",
                "Relevant", "Related", "First", "Good", "Completed", "Recognised", "Recent", "Degree", "Level", "Any", "Essential",
                "Desirable", "Ideally", "Strong", "Similar", "Appropriate", "Suitable", "Equivalent", "Postgraduate", "Foundation",
                "Full", "Minimum", "Educated", "Have", "Hold", "Holding", "With", "Or", "And", "Uk", "Higher", "Graduate"}
GENERIC_SUBJ = re.compile(r"^(?:(?:a|an|any|the|relevant|related|suitable|appropriate|similar|comparable|associated|closely|"
                          r"subject|subjects|discipline|disciplines|field|fields|area|areas|degree)\b[\s,/]*)+$", re.I)
SUBJ_STOP = re.compile(r"\s*(?:\(|\)|,?\s+(?:or|and/or)\s+(?:an?\s+|other\s+|another\s+)?(?:equivalent|related|relevant|similar|other|another|"
                       r"closely|comparable|suitable|appropriate|associated)\b|\s+(?:would|is|are|was|with|from|plus|preferred|desirable|"
                       r"essential|ideally|required|as well|and (?:a|an|experience|some|demonstrable|at|the|have|be|strong|good|proven)|"
                       r"or (?:equivalent|experience|relevant|a|an)|alongside|including|to\b|who|that|which|at\b)\b|[.;:!?]|\s[-–]\s|\s\d)", re.I)
QUAL_RX = [
    re.compile(r"\b(CIPD|CIPR|CIM|NCTJ|AAT|ACCA|CIMA|ICAEW|PRINCE ?2|IOSH|NEBOSH|PGCE|QTS|CSCS|CeMAP|ILM|SIA licen[cs]e)\b"
               r"(?:[^.;,]{0,25}?\b[Ll]evel ?[1-7])?"),
    re.compile(r"\b(?:BSL|Signature)(?: BSL| Signature)?(?: [Ll]evel ?[1-7]| qualification| to a minimum of [Ll]evel ?[1-7])"),
    re.compile(r"\b(?:NVQ|QCF|RQF|BTEC|HNC|HND)\b(?:,? ?(?:NVQ|BTEC)?\s*\(?[Ll]evel\s*[1-7](?:/[1-7])?\)?)?(?:\s+or equivalent)?(?:[^.;]{0,25}?\bin\s+[A-Z][\w&/ ,'-]{2,60})?"),
    re.compile(r"\b[Ll]evel\s*[1-7](?:/[1-7])?\s+(?:[A-Z]\w+\s+){0,2}(?:[Dd]iploma|[Cc]ertificate|[Qq]ualification|[Aa]ward)\b(?:\s+in\s+[A-Z][\w&/ '-]{2,60})?"),
    re.compile(r"\b(?:[Dd]iploma|[Cc]ertificate)\s+in\s+[A-Z][\w&/ '-]{2,60}"),
    re.compile(r"\b(?:registered with|registration with)\s+(?:the\s+)?(?:HCPC|NMC|Social Work England|GMC|GPhC|BACP|UKCP|SRA)\b"),
    re.compile(r"\b(?:[Qq]ualified|[Rr]egistered) (?:accountant|teacher|nurse|social worker|solicitor|counsellor|lawyer|surveyor|electrician|paralegal)\b"),
    re.compile(r"\b(?:[Ss]ocial [Ww]ork|[Tt]eaching|[Nn]ursing|[Cc]ounselling|[Ll]egal) qualification\b"),
]
QUAL_TRAIL = re.compile(r"\s+(?:or|and|would|is|are|with|desirable|essential|preferred|required|ideally|as|to|in a|in an|in the|qualification|"
                        r"What|Why|Our|We|You|About|Salary|Benefits|Apply|Location|Hours|The|This)\b.*$|[\s,(]+$")
GCSE_RX = re.compile(r"\bGCSEs?\b|\bA[- ]levels?\b")
WANT_DESIRABLE = re.compile(r"desirabl|advantage|preferred|preferabl|ideally|\bideal\b|nice to have|\bbonus\b|would be (a )?(plus|beneficial|helpful|useful)|"
                            r"not essential|beneficial|particularly interested|welcome(d)?\b|is a plus", re.I)
WANT_ESSENTIAL = re.compile(r"essential|\bmust\b|\brequired\b|requirement|you('ll| will) (need|hold|have|possess)|minimum|\bneed (a|an|to have)\b|"
                            r"necessary|to be (considered|successful)|you hold", re.I)
WANT_TRAINING = re.compile(r"willing(ness)? to (obtain|achieve|gain|work towards|study|complete)|or willingness|working towards|"
                           r"(training|support) (will be |is |can be )?(provided|given|offered)|we (will|can) (provide|offer|fund|support)|"
                           r"support you (to|in) (gain|achiev|obtain|complet)|opportunity to (gain|achieve|study|obtain|complete)|"
                           r"expectation to study|fully funded|study towards|(achieve|complete|obtain)d? within|able to offer .{0,30}training|"
                           r"if not already qualified", re.I)
SECTION_DES = re.compile(r"desirable|nice to have|bonus points|advantageous", re.I)
SECTION_ESS = re.compile(r"essential|requirements|what you('ll| will) need|you (will|must) have|must have|skills you'll need", re.I)
ALT_EXPERIENCE = re.compile(r"or (relevant |equivalent |similar |significant |demonstrable )?(work |professional |practical )?experience|"
                            r"equivalent (work |professional )?experience|experience in lieu", re.I)
ALT_EQUIV = re.compile(r"or (an? )?(equivalent|similar|comparable)|equivalent qualification", re.I)
LEVEL_RANK = {"essential": 3, "stated": 2, "desirable": 1, "training": 0}


def _cut(s: str, limit: int = 60) -> str:
    s = re.sub(r"\s+", " ", s).strip(" ,/&-")
    s = re.sub(r",?\s+(?:or|and|and/or)$", "", s).strip(" ,/&-")
    if len(s) > limit:
        s = s[:limit].rsplit(" ", 1)[0].rstrip(" ,/&-") + "…"
    return s


def _degree_subject(clause: str):
    """'' = any subject, 'relevant' = a relevant subject (not named), else the subject text."""
    if re.search(r"\bin:?\s*$|subjects? (outlined|listed|above|below|mentioned)", clause, re.I):
        return "relevant"
    m = DEGREE_SUBJ.search(clause)
    if m:
        subj = re.sub(r"^(?:an?|any)\s+(?:suitable|relevant|related|appropriate)\s+(?:subject|field|discipline|area)s?,?\s*"
                      r"(?:such as|e\.?g\.?|like|for example|including)\s+", "", m.group(1), flags=re.I)
        subj = SUBJ_STOP.split(subj, 1)[0]
        subj = _cut(subj)
        if subj and not GENERIC_SUBJ.match(subj):
            return subj
        return "relevant"
    m = DEGREE_PREFIX.search(clause)
    if m:
        words = m.group(1).split()
        while words and words[0] in PREFIX_NOISE:
            words.pop(0)
        if words and words[-1] not in PREFIX_NOISE:
            return " ".join(words)
    if re.search(r"(relevant|related|suitable|appropriate) (degree|subject|discipline|field)", clause, re.I):
        return "relevant"
    return ""


def _want_level(clause: str, after: str, before: str) -> str:
    if WANT_TRAINING.search(clause):
        return "training"
    if WANT_DESIRABLE.search(clause) or re.match(r"\s*(this is )?(not essential|desirable|an advantage|a plus)", after, re.I):
        return "desirable"
    if WANT_ESSENTIAL.search(clause):
        return "essential"
    des = [m.end() for m in SECTION_DES.finditer(before)]
    ess = [m.end() for m in SECTION_ESS.finditer(before)]
    if des or ess:
        return "desirable" if (des[-1] if des else -1) > (ess[-1] if ess else -1) else "essential"
    return "stated"


def requirements_for(text: str, limit: int = 4) -> list[dict]:
    clauses = [c for c in REQ_SPLIT.split(text or "") if c and len(c) > 6]
    found: dict = {}

    def add(kind, name, clause, i):
        after = clauses[i + 1] if i + 1 < len(clauses) else ""
        before = " ".join(clauses[max(0, i - 8):i])[-600:]
        req = {"kind": kind, "name": name, "level": _want_level(clause, after[:60], before),
               "alt": "experience" if ALT_EXPERIENCE.search(clause) else ("equivalent" if ALT_EQUIV.search(clause) else None), "quote": _cut(clause, 200)}
        key = (kind, name.lower())
        old = found.get(key)
        if not old or LEVEL_RANK[req["level"]] > LEVEL_RANK[old["level"]]:
            found[key] = req

    for i, clause in enumerate(clauses):
        if REQ_SKIP.search(clause):
            continue
        plain = DEGREE_360.sub(" ", clause)
        if DEGREE_WORD.search(plain) or DEGREE_ABBR.search(plain):
            add("degree", _degree_subject(plain), clause, i)
        spans = []
        for rx in QUAL_RX:
            for m in rx.finditer(clause):
                if any(a < m.end() and m.start() < b for a, b in spans):
                    continue
                spans.append(m.span())
                name = _cut(QUAL_TRAIL.sub("", m.group(0)), 50)
                low = name.lower().rstrip("…")
                dup = next((key for key in found if key[0] == "qualification" and (low in key[1] or key[1].rstrip("…") in low)), None)
                if dup:
                    name = found[dup]["name"]
                if len(name) >= 3:
                    add("qualification", name, clause, i)
        if GCSE_RX.search(clause):
            subj = sorted({s.title() for s in re.findall(r"\b(english|maths|mathematics|science)\b", clause, re.I)})
            add("gcse", ("A-levels" if re.search(r"A[- ]level", clause) and not re.search(r"GCSE", clause) else "GCSEs")
                + (f" ({', '.join(subj)})" if subj else ""), clause, i)
    reqs = sorted(found.values(), key=lambda r: (-LEVEL_RANK[r["level"]], ["degree", "qualification", "gcse"].index(r["kind"])))
    return reqs[:limit]


PORTALS = {
    "webitrent.com": "council / public-sector portal (iTrent)",
    "jobs.ac.uk": "jobs.ac.uk university portal",
    "trac.jobs": "NHS (Trac) application form",
    "jobs.nhs.uk": "NHS Jobs website",
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
    elif source == "Jooble":
        kind = "Via Jooble to the employer / agency site"
        low, high = 30, 75
        steps += ["Open the listing (Jooble forwards you to the original advert)", "Follow the advertiser's apply steps",
                  "Upload a tailored CV and submit"]
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


def jooble_search(key, keywords, loc) -> list[dict]:
    """Official Jooble REST API (POST https://uk.jooble.org/api/<key>). A UK key only works on the UK domain."""
    if FIXTURES:
        return (fixture(f"jooble_search_{loc['id']}.json") or {}).get("jobs", [])
    body = {"keywords": keywords + (" remote" if loc.get("remote") else ""),
            "location": "United Kingdom" if loc.get("remote") else loc.get("jooble", loc["adzuna"]),
            "page": "1", "ResultOnPage": SEARCHES.get("jooble_results_per_search", 30)}
    if not loc.get("remote") and loc.get("jooble_radius_km") is not None:
        body["radius"] = str(loc["jooble_radius_km"])
    host = SEARCHES.get("jooble_host", "uk.jooble.org")
    return http_json(f"https://{host}/api/{urllib.parse.quote(key, safe='')}", body=body).get("jobs", []) or []


def nhs_search(keywords, loc) -> list[dict]:
    """Official NHS Jobs search API (no key): https://www.jobs.nhs.uk/api/v1/search_xml — published by NHSBSA for job boards."""
    if FIXTURES:
        path = os.path.join(FIXTURES, f"nhs_search_{loc['id']}.xml")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            xml_text = f.read()
    else:
        params = {"keyword": keywords, "location": loc.get("nhs", loc["adzuna"]), "distance": loc["distance"],
                  "limit": SEARCHES.get("nhs_results_per_search", 50)}  # default sort is relevance
        req = urllib.request.Request("https://www.jobs.nhs.uk/api/v1/search_xml?" + urllib.parse.urlencode(params),
                                     headers={"User-Agent": API_UA, "Accept": "application/xml"})
        xml_text = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    xml_text = resp.read().decode("utf-8")
                break
            except (urllib.error.URLError, TimeoutError):
                if attempt == 2:
                    raise
                time.sleep(3 * (attempt + 1))
    root = ET.fromstring(xml_text)
    out = []
    for v in root.iter("vacancyDetails"):
        rec = {child.tag: (child.text or "").strip() for child in v if child.tag != "locations"}
        rec["locations"] = [(l.text or "").strip() for l in v.iter("location") if (l.text or "").strip()]
        out.append(rec)
    return out


def strip_tags(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def salary_range(s: str) -> tuple[int | None, int | None]:
    """Pull an annual min/max out of free-text salaries like '£25,000 - £28,000'. Hourly/daily rates are ignored."""
    nums = [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", s or "")]
    nums = [n * 1000 if re.search(r"\d\s*k\b", s or "", re.I) and n < 1000 else n for n in nums]
    nums = [int(n) for n in nums if n >= 5000]
    return (min(nums), max(nums)) if nums else (None, None)


def excluded_title(title: str) -> bool:
    t = title.lower()
    return any(term in t for term in SEARCHES["exclude_title_terms"])


SOURCE_RANK = {"Reed": 0, "NHS Jobs": 1, "Adzuna": 2, "Jooble": 3}


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


def collect_jooble(key: str, errors: list) -> dict[str, dict]:
    found: dict[str, dict] = {}
    calls_left = SEARCHES.get("jooble_max_calls_per_run", 32)  # free keys allow 100 requests/day
    for cat in SEARCHES["categories"]:
        for kw in cat.get("jooble_keywords", cat["keywords"][:1]):
            for loc in SEARCHES["locations"]:
                if calls_left <= 0:
                    return found
                calls_left -= 1
                try:
                    results = jooble_search(key, kw, loc)
                except Exception as e:
                    errors.append(f"Jooble '{kw}' / {loc['label']}: {e}")
                    continue
                for r in results:
                    title = strip_tags(r.get("title") or "")
                    if not title or excluded_title(title):
                        continue
                    if loc.get("remote") and not REMOTE_RX.search(f"{title} {strip_tags(r.get('snippet') or '')} {r.get('location', '')}"):
                        continue
                    jid = f"jooble-{r.get('id')}"
                    item = found.setdefault(jid, {"raw": r, "categories": set(), "areas": set()})
                    item["categories"].add(cat["id"])
                    item["areas"].add(loc["id"])
                if not FIXTURES:
                    time.sleep(0.5)
    return found


def nhs_title_matches(title: str, keyword: str) -> bool:
    """NHS Jobs keyword search is fuzzy and always fills the page, so keep only titles that share a real word with the search."""
    words = [w.rstrip("s") for w in re.findall(r"[a-z]+", keyword.lower()) if len(w) >= 5]
    t = title.lower()
    return not words or any(w in t for w in words)


def collect_nhs(errors: list) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for cat in SEARCHES["categories"]:
        for kw in cat.get("nhs_keywords", []):
            for loc in SEARCHES["locations"]:
                if loc.get("remote"):  # NHS Jobs search is location-based
                    continue
                try:
                    results = nhs_search(kw, loc)
                except Exception as e:
                    errors.append(f"NHS Jobs '{kw}' / {loc['label']}: {e}")
                    continue
                for r in results:
                    title = strip_tags(r.get("title") or "")
                    if not title or excluded_title(title) or not r.get("reference") or not nhs_title_matches(title, kw):
                        continue
                    jid = f"nhs-{r['reference']}"
                    item = found.setdefault(jid, {"raw": r, "categories": set(), "areas": set()})
                    item["categories"].add(cat["id"])
                    item["areas"].add(loc["id"])
                if not FIXTURES:
                    time.sleep(0.5)
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
    elif source == "NHS Jobs":
        title = strip_tags(raw.get("title") or "")
        employer = strip_tags(raw.get("employer") or "")
        location = "; ".join(raw.get("locations") or [])
        desc_html = raw.get("description") or ""
        ref = urllib.parse.quote(raw.get("reference") or "", safe="-")
        listing_url = f"https://www.jobs.nhs.uk/candidate/jobadvert/{ref}" if ref else (raw.get("url") or "")
        apply_url = listing_url
        external = ""
        posted = parse_uk_date(raw.get("postDate"))
        closing = parse_uk_date(raw.get("closeDate"))
        raw_sal = strip_tags(raw.get("salary") or "")
        lo, hi = salary_range(raw_sal)
        sal = salary_text(lo, hi) if lo else (raw_sal or "Not stated")
        contract = strip_tags(raw.get("type") or "")
        apply_via = "NHS Jobs"
        detail_ok = False
    elif source == "Jooble":
        title = strip_tags(raw.get("title") or "")
        employer = strip_tags(raw.get("company") or "")
        location = strip_tags(raw.get("location") or "")
        desc_html = raw.get("snippet") or ""
        listing_url = (raw.get("link") or "").strip()
        apply_url = listing_url
        external = listing_url
        posted = parse_uk_date(raw.get("updated"))  # Jooble gives "last updated", the closest thing to a posted date
        closing = None
        sal = strip_tags(raw.get("salary") or "") or "Not stated"
        lo, hi = salary_range(sal)
        contract = strip_tags(raw.get("type") or "")
        apply_via = "Jooble → advertiser"
        detail_ok = False
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
        "requirements": requirements_for(text),
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
        pause = 1.0 if any(s in host for s in ("reed.co.uk", "adzuna", "jooble", "jobs.nhs.uk")) else 0.5
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


def min_score(job):
    """NHS Jobs gives only a ~150-character preview, so it gets its own (lower) bar; its titles are already filtered."""
    if job.get("source") == "NHS Jobs":
        return SEARCHES.get("nhs_min_score_to_keep", SEARCHES["min_score_to_keep"])
    return SEARCHES["min_score_to_keep"]


def main() -> int:
    reed_key = os.environ.get("REED_API_KEY", "").strip()
    az_id = os.environ.get("ADZUNA_APP_ID", "").strip()
    az_key = os.environ.get("ADZUNA_APP_KEY", "").strip()
    jooble_key = os.environ.get("JOOBLE_API_KEY", "").strip()
    if FIXTURES:
        reed_key = reed_key or "fixture"
        az_id, az_key = az_id or "fixture", az_key or "fixture"
        jooble_key = jooble_key or "fixture"

    previous, prev_meta = load_previous()
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        cache = {}
    errors: list[str] = []
    sources_used = []

    nhs_on = bool(SEARCHES.get("nhs_enabled", True))  # NHS Jobs needs no key
    if not reed_key and not (az_id and az_key) and not jooble_key and not nhs_on:
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
    if nhs_on:
        sources_used.append("NHS Jobs")
        for jid, item in collect_nhs(errors).items():
            raw[jid] = ("NHS Jobs", item)
    if az_id and az_key:
        sources_used.append("Adzuna")
        for jid, item in collect_adzuna(az_id, az_key, errors).items():
            raw[jid] = ("Adzuna", item)
    if jooble_key:
        sources_used.append("Jooble")
        for jid, item in collect_jooble(jooble_key, errors).items():
            raw[jid] = ("Jooble", item)
    log(f"Collected {len(raw)} raw listings; {len(errors)} search errors")

    # Rank Reed listings by snippet score so detail lookups go to the best ones first.
    def snippet_score(entry):
        src, item = entry[1]
        r = item["raw"]
        title = strip_tags(r.get("jobTitle") or r.get("title") or "")
        return match_score(title, strip_tags(r.get("jobDescription") or r.get("description") or r.get("snippet") or ""), [])["score"]

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
        if job["match"]["score"] < min_score(job):
            continue
        key = norm_key(job["title"], job["employer"])
        if key in dedupe:  # same job on several sources: prefer Reed (closing dates + full text), then Adzuna, then Jooble
            existing = jobs[dedupe[key]]
            areas = sorted(set(existing["areas"]) | set(job["areas"]))
            cats = sorted(set(existing["categories"]) | set(job["categories"]))
            existing["areas"], existing["categories"] = areas, cats
            if SOURCE_RANK.get(job["source"], 9) >= SOURCE_RANK.get(existing["source"], 9):
                continue
            job["areas"], job["categories"] = areas, cats
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
        if (prev.get("match") or {}).get("score", 0) < min_score(prev):
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
