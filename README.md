# Job Finder for 宝宝 · 宝宝的求职小助手

A small web app that lists graduate-level UK jobs in four areas: digital inclusion and community work, comms and content, admin and customer service, and older-people, youth and Mandarin-speaking support. It covers Manchester, Sheffield, London and remote roles.

The page works in English (the default) and Simplified Chinese: use the **English / 中文** switch in the header, or open the site with `?lang=zh`. The choice is remembered on that device. Job titles, employers and advert text stay in their original English.

A GitHub Action runs every morning. It:

1. Pulls live vacancies from the official **Reed** and **Adzuna** job APIs.
2. Adds a short summary, key responsibilities, the likely application process with a time estimate, a visa-sponsorship flag and a **match %** for each job.
3. Checks that each listing and apply link still loads, and drops jobs whose pages are gone or say they've closed.
4. Publishes the table to GitHub Pages.

## Setup (about 5 minutes)

1. **Get a Reed API key (free).** Sign up at <https://www.reed.co.uk/developers/jobseeker>. The key arrives by email.
2. **Optional: get Adzuna keys (free).** Register at <https://developer.adzuna.com> to get an App ID and App Key.
3. **Add them as repository secrets.** Go to *Settings → Secrets and variables → Actions → New repository secret* and add:
   - `REED_API_KEY`
   - `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` (optional)
4. **Turn on Pages.** Go to *Settings → Pages* and set **Source** to **GitHub Actions**.
5. **Run it.** Go to *Actions → Daily job update → Run workflow*. After that it runs every day at 05:37 UTC.

The site will be at `https://<your-username>.github.io/<repo-name>/`.

## How things are worked out

| Field | How it's produced |
|---|---|
| Links | Taken directly from the API: the Reed listing page, the employer's own apply URL where Reed provides one, or Adzuna's listing link. Each link is fetched daily. Pages that return 404/410 or say "vacancy closed" are removed. Sites that block automated checks are labelled "Open manually". |
| Closing date | From Reed. Adzuna doesn't provide one, so those show "Not stated". |
| Summary and responsibilities | Pulled from the advert text, using the bullet list under a "responsibilities" or "duties" heading where there is one. |
| Application process and time | Rules based on the apply site (for example, council iTrent portals or NHS forms mean a long form) and the advert wording (supporting statement, cover letter, portfolio, "no CVs"). |
| Qualifications | Degrees (with the subject where named), professional qualifications (CIPD, NVQ, Level 3 diplomas and so on) and GCSEs found in the advert. Each is marked *essential*, *desirable*, *training offered* or *asked for*, and notes when experience is accepted instead. The **Qualifications** filter can hide jobs that need a specific subject or qualification. The optional **My qualifications** box is saved only in the browser (never in this repo) and ticks off requirements already met. Short previews (Adzuna, Jooble, NHS Jobs) can miss requirements. |
| Paid internships & part-time tab | Extra searches in Sheffield and Manchester (set in `experience` in `config/searches.json`): Reed's part-time filter on every job-type keyword, internship/placement searches, and a few Adzuna and Jooble searches. Jobs are tagged *Internship* (paid only: unpaid or volunteer roles are left out) or *Part-time* (from the contract type, "part-time" wording, or under 30 hours a week). The tab uses a lower minimum match (20%) because these roles are often less specialised. Open it directly with `#experience`. |
| Visa | Flagged as *offered*, *not offered*, *right to work required* or *not stated*, based on the advert wording. |
| Match % | A weighted skills overlap with the CV themes in `config/profile.json`, plus bonuses (Mandarin, entry level, digital inclusion, older people) and penalties (senior roles, 2+ years' experience, driving licence, specialist qualifications). It's an estimate, not a verdict. |

## Customising

- **Searches, locations and excluded job titles:** edit `config/searches.json`.
- **Skills and match weights:** edit `config/profile.json`. Keep this to skills only, because the repo is public.
- **Look and feel:** edit `docs/style.css` and `docs/app.js`.
- **Translations:** edit `docs/i18n.js`. If you add a new process step, flag or match label in the fetcher or profile, add its Chinese version there too (untranslated text falls back to English).

## Privacy

The repo and the site are public on GitHub's free plan. They contain no names, contact details or CVs, only a skills profile and public job adverts.

## Tests

```bash
python -m unittest discover -s tests
```

These run offline against fixtures in `tests/fixtures`.
