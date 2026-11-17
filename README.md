# Job Finder

A small web app that lists graduate-level UK jobs in four areas: digital inclusion and community work, comms and content, admin and customer service, and older-people, youth and Mandarin-speaking support. It covers Manchester, Sheffield, London and remote roles.

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
| Visa | Flagged as *offered*, *not offered*, *right to work required* or *not stated*, based on the advert wording. |
| Match % | A weighted skills overlap with the CV themes in `config/profile.json`, plus bonuses (Mandarin, entry level, digital inclusion, older people) and penalties (senior roles, 2+ years' experience, driving licence, specialist qualifications). It's an estimate, not a verdict. |

## Customising

- **Searches, locations and excluded job titles:** edit `config/searches.json`.
- **Skills and match weights:** edit `config/profile.json`. Keep this to skills only, because the repo is public.
- **Look and feel:** edit `docs/style.css` and `docs/app.js`.

## Privacy

The repo and the site are public on GitHub's free plan. They contain no names, contact details or CVs, only a skills profile and public job adverts.

## Tests

```bash
python -m unittest discover -s tests
```

These run offline against fixtures in `tests/fixtures`.
