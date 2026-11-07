# About Page Content Replacement Implementation Plan

> **For agentic workers:** Execute inline in this session. Work one task at a time and verify each task before continuing.

**Goal:** Replace the backend About page content with the user's eight Russian story slides and attach one relevant photo to every slide.

**Architecture:** Store the Russian source copy, order, and eight direct image URLs in a small backend content module. A guarded one-off command will back up current rows, atomically replace the `About` and `AboutSection` records, and enqueue translations through the existing translation worker.

**Tech Stack:** Python 3.12, SQLAlchemy, FastAPI catalogue models, existing translation queue, PostgreSQL, direct Unsplash image URLs.

## Global Constraints

- Preserve the supplied Russian wording and slide order; do not add Kyrgyz content.
- Store Russian as source and let the existing worker translate to `en`, `de`, and `zh`.
- Keep the existing API routes and database schema unchanged.
- Add one distinct image URL to each of the eight `AboutSection` rows.
- The repository contains backend code only; do not claim the frontend layout was updated.
- Back up all existing About and AboutSection rows before replacing them.
- Do not run the repository test suite; local test setup requires unavailable PostgreSQL DNS.

---

### Task 1: Define About copy and image mapping

**Files:**
- Create: `mysite/about_content.py`
- Verify: `mysite/database/models.py` (`About`, `AboutSection` image/title/description fields)

**Interfaces:**
- Produces `ABOUT_TITLE: str` and `ABOUT_SLIDES: tuple[dict, ...]`.
- Each slide dict has `title`, `description`, and `image` string fields; tuple order is display order.

- [ ] Add the parent title `МЫ СОЗДАЁМ ПУТЕШЕСТВИЯ, КОТОРЫЕ ОБЪЕДИНЯЮТ МИР.` and the following eight sections:

| Order | Section title | Photo subject and Unsplash photo ID |
|---:|---|---|
| 1 | С чего всё начиналось | Kyrgyzstan road trip vehicles, `photo-1761872802877-f4a229449340` |
| 2 | Первые шаги и развитие | Traveler on a mountain road in Grigorievka, `photo-1721901194224-d91f30cbeac5` |
| 3 | Международное развитие | Group on a mountain in Bishkek, `photo-1700321942503-1c66858a8737` |
| 4 | Мы — принимающая компания в Кыргызстане | Travelers arriving with luggage, `photo-1770010314050-c88979e98e1c` |
| 5 | Собственная организация и инфраструктура | Yurt camp in a Kyrgyz valley, `photo-1758822128239-8671831f2421` |
| 6 | Путешествия по всему миру | Travelers in front of a plane, `photo-1642325290930-30cc5f869169` |
| 7 | Священное направление — Умра | Pilgrims at the Kaaba, `photo-1693590614566-1d3ea9ef32f7` |
| 8 | Наша миссия и сегодняшний день | Ala-Archa mountain valley, `photo-1721486535037-5ecac8183437` |

- [ ] Use these direct image URL templates with the listed IDs: `https://images.unsplash.com/{photo_id}?auto=format&fit=crop&w=1600&q=85`.
- [ ] Preserve the user's copy in Russian. The `description` begins with the bold lead sentence as plain text, followed by the supplied paragraphs and bullets separated by newline characters. For slide 8, append `KyrgyzGo — путешествия, которым доверяют.`
- [ ] Keep slide headings in `title`; do not retain the `Слайд N.` prefix as user-facing text.

### Task 2: Implement safe database replacement

**Files:**
- Create: `scripts/replace_about_content.py`
- Use: `mysite/about_content.py`, `mysite/database/db.py`, `mysite/database/models.py`, `mysite/translations/content.py`, `mysite/translations/jobs.py`

**Interfaces:**
- `python -m scripts.replace_about_content --dry-run` reports the number of rows to replace and exits without writes.
- `python -m scripts.replace_about_content --apply --backup /path/to/about-backup.json` writes a complete JSON backup, then replaces rows in one database transaction.

- [ ] Serialize every current About and AboutSection column, including IDs and translations, to UTF-8 JSON before the transaction begins.
- [ ] Require `--apply` for writes and refuse to overwrite an existing backup file.
- [ ] Within one `SessionLocal` transaction, delete all old `AboutSection` and `About` rows, insert one active About record using `ABOUT_TITLE`, then insert the eight active sections with orders 1–8 and their image URLs. Flush the inserts and reset `order` to 1–8 after the model's `after_insert` listener assigns IDs as the initial order.
- [ ] Call `update_translations(record)` for the About record and every section before commit. After commit, collect `committed_jobs(session)`, close the session, and enqueue those jobs with `enqueue_translation(*job)` so translations use the existing worker.
- [ ] Print only row counts and translation queue count; do not print database credentials or stored unrelated content.

### Task 3: Apply replacement and verify API data

**Files:**
- Run: `scripts/replace_about_content.py` inside the deployed API environment; no schema migration.

**Interfaces:**
- Source locale endpoint: `GET /about-sections/?lang=ru` returns the eight active slides ordered 1–8.
- Parent endpoint: `GET /abouts/?lang=ru` returns the single active About headline.
- Translated endpoints use `lang=en`, `lang=de`, and `lang=zh`.

- [ ] Confirm the existing database backup is available and create the table-row JSON backup outside the container before applying.
- [ ] Run `--dry-run`; require counts of one About row and eight sections to be inserted.
- [ ] Run `--apply` with a unique backup path; require the command to report one About row and eight sections committed.
- [ ] Query both public endpoints in Russian and verify all eight titles, order, supplied body text, and eight non-empty image URLs.
- [ ] Verify translated reads use the stored translation when ready and fall back to Russian while asynchronous translations are pending.
- [ ] If the one-off command runs in a separate process, wait for its translation queue to drain; if a provider call fails, leave the stored Russian source intact and let the running app's translation recovery retry.

### Task 4: Update deployment guidance

**Files:**
- Modify: `DEPLOY.md`

- [ ] Document the About replacement command, mandatory backup path, and the fact that About text and slide photos come from backend API records.
- [ ] State that the frontend source is outside this repository and must already render the `AboutSection.image` field for photos to appear visually.

## Image sources

The eight photos were selected from Unsplash pages marked free to use under the Unsplash License:

1. [Kyrgyzstan road trip vehicles](https://unsplash.com/photos/two-vehicles-parked-on-a-hilltop-with-people-GpXJcT0U-3M)
2. [Traveler on a Kyrgyz mountain road](https://unsplash.com/photos/a-person-walking-down-a-dirt-road-in-the-mountains-wY1ZUbgTbqw)
3. [Group on a mountain in Bishkek](https://unsplash.com/photos/a-group-of-people-standing-on-top-of-a-mountain-BvhmiFX3pnw)
4. [Airport arrival](https://unsplash.com/photos/people-with-luggage-in-a-modern-airport-terminal-YxuI5Gax5JU)
5. [Kyrgyz yurt camp](https://unsplash.com/photos/a-cluster-of-white-yurts-nestled-in-a-grassy-valley-uI_Tol_cC70)
6. [Travelers at a plane](https://unsplash.com/photos/a-group-of-people-standing-in-front-of-an-airplane-VwtMm4ElF1A)
7. [Kaaba and pilgrims](https://unsplash.com/photos/kaaba-at-masjid-al-haram-in-mecca-ceNCWYqL8DY)
8. [Ala-Archa valley](https://unsplash.com/photos/a-scenic-view-of-a-mountain-valley-with-a-river-running-through-it-MWZS-ThJLJo)

Unsplash's [license](https://unsplash.com/license) permits free commercial use of its photos without required attribution.
