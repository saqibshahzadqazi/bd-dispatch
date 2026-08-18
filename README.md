# Dispatch

Your team hands in the sheet of jobs each profile applied to. The system works
out which postings are the same job across every sheet, shows you how much
effort was spent twice, and gives each profile back the jobs it has never tried.

---

## The idea in one example

Ali runs the profile **Khuram**, an AI engineer. Sara runs **Zahid**, also an AI
engineer. Same skills, same job boards, two different candidates.

Khuram applied to 30 jobs. Zahid applied to 50. Ten of those were the same
posting found twice, so between them they reached **70 distinct jobs**.

Run the cycle:

| | applied | pool | comes back |
|---|---|---|---|
| Khuram | 30 | 70 | **40** |
| Zahid | 50 | 70 | **20** |

Khuram gets the 40 it has never seen. Zahid gets the 20 it has never seen. The
ten both had already used go to nobody.

Note that Khuram is handed jobs **Zahid already applied to**, and that is
correct. They are two candidates, not one person applying twice — the client
sees two applicants. The only thing the system will never do is offer a profile
a job that *same profile* has already used.

---

## Profiles, not people

This is the distinction the whole product turns on.

- A **person** signs in. Ali, Sara, the manager.
- A **profile** is the identity a job is applied under — the name and resume the
  client sees. "Khuram, AI Engineer".

One person can run several profiles. A profile can be handed to a different
person. All history — what has been applied to, what has been dispatched —
belongs to the **profile**, because that is what the client recognises.

Two profiles sharing a headline is not a problem to solve. It is the normal case.

---

## What happens when you press "Build the lists"

1. **Every row is fingerprinted.** Same job, different link, must resolve to the
   same identity. Four tiers, first hit wins:

   | Tier | Rule | Typical share |
   |---|---|---|
   | L1 | Platform's own job ID pulled out of the URL (Upwork `~01…`, LinkedIn `/jobs/view/…`, Indeed `jk=…`) | ~85% |
   | L2 | Canonical URL — protocol, `www.`, tracking params and trailing slash stripped | ~8% |
   | L3 | Client + title, when there is no usable link | ~6% |
   | L3f | L3 rows merged when client *and* title are both a close fuzzy match | reposts and reworded titles |

   The named platforms mint globally unique IDs, so an Upwork `~01…` is that job
   and nothing else. The generic fallbacks — "a long number in the path" — match
   a shape that repeats on every board in existence, so those keys carry the
   hostname too. Otherwise `example.com/careers/12345678` and
   `different.com/openings/12345678` would collapse into one job and one of the
   two postings would quietly vanish from the pool.

2. **Applications are recorded** — one row per profile per job, for good.

3. **The pool is built** from this cycle's sheets *plus* anything still sitting
   unworked on a participating profile's list from an earlier cycle. A job
   somebody ran out of time for does not fall through the cracks.

4. **The lists rebuild themselves.** A cycle stays open while the team works it.
   Every few minutes — you pick 5, 10, 15 or 30 when opening it — the server
   rebuilds every open cycle that has at least two sheets in it. Nobody presses
   anything: a job Ali logs at two o'clock is off the other profiles' lists by
   ten past.

   Rebuilding never disturbs work already done. Jobs a profile has marked
   **applied** or **skipped** keep their place and their status; only the
   untouched rows are recalculated. Closing the cycle is what stops the timer.

5. **Each profile is given what it has not used.** Two modes, chosen when you
   open the cycle:

   - **Cover every profile** (default) — each profile gets every pooled job it
     has not applied to or skipped. This is the Khuram-and-Zahid case above.
   - **Split the pool** — each job goes to exactly one profile, nobody overlaps.
     For a team where the profiles are really one identity and a second
     application would read as a repeat.

   A quota caps each list. When it bites, the jobs almost nobody is eligible for
   go out first, so a rare opening is not lost to a job everyone could have taken.

6. **The database holds the line.** `assignments` is unique on
   (batch, job, profile), so one cycle can never put the same job on one
   profile's list twice. Split cycles additionally carry a partial unique index
   on (batch, job) — so even with a bug, or two managers pressing the button at
   once, a split cycle cannot hand one posting to two profiles.

A job leaves a profile's rotation for good only when that profile marks it
**applied** or **skipped**. Anything left as *to do* comes back next cycle.

---

## Run it locally

You need Python 3.10+ and Node 18+. Nothing else.

### 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

cp .env.example .env               # Windows: copy .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
# paste that into JWT_SECRET in .env

python seed.py --samples           # accounts, profiles and test sheets
uvicorn app.main:app --reload --port 8000
```

Leave that running. API docs are at <http://localhost:8000/docs>.

Seeded accounts:

| Email | Password | Role | Runs |
|---|---|---|---|
| `admin@example.com` | `admin12345` | Manager | — |
| `ali@example.com` | `bdpass12345` | BD | Khuram · AI Engineer |
| `sara@example.com` | `bdpass12345` | BD | Zahid · AI Engineer |
| `hina@example.com` | `bdpass12345` | BD | Nadia · Full Stack Engineer |

**Change these before anyone else can reach the server.**

### 2. Frontend

New terminal:

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. Vite forwards `/api` to port 8000, so there is
nothing to configure.

---

## Test it end to end

`python seed.py --samples` writes three CSVs into `backend/sample_sheets/`,
built so the arithmetic is checkable by hand. Khuram's sheet holds jobs 0–29,
Zahid's holds 20–69 — exactly ten in common. Nadia's sheet deliberately uses
different column names, blank links on some rows and shouty uppercase titles, to
exercise the auto-mapper and the fuzzy tier.

**Walk it through by hand:**

1. Sign in as `admin@example.com`. Open a cycle called `Test`, cap 500, leaving
   **Cover every profile** selected.
2. Sign out. Sign in as `ali@example.com`, drop `khuram-applied.csv`. Sign out.
   Sign in as `sara@example.com`, drop `zahid-applied.csv`.
3. Sign back in as admin and press **Build the lists**.
4. Khuram should show 40 and Zahid 20, with ten jobs both had already applied to.
5. Sign in as Ali — Khuram's list is there, 40 jobs, none of them anything
   Khuram has touched before.

**Or let the tests do it:**

```bash
cd backend
pytest test_matching.py -v      # 26 rules: fingerprints, fuzzy merge, both modes
pytest test_e2e.py -v -s        # full round trip, prints the report
```

Expected output on the sample data:

```
Rows read                              80
Unique jobs                            70
Jobs two profiles both applied to      10
Duplicate applications                 10
Jobs nobody could take                 10
Jobs put on a list                     60

Khuram   AI Engineer   Ali Raza    40 jobs
Zahid    AI Engineer   Sara Khan   20 jobs
```

`test_e2e.py` asserts what matters: a profile is never handed a job it already
used, one person's two profiles do not restrict each other, unworked jobs come
back and worked ones do not, split cycles keep every job to one profile,
rebuilding gives the same answer, one cycle's report never counts another's, and
nothing a spreadsheet can contain becomes a live link or an Excel formula on a
colleague's machine.

---

## Using it for real

1. Sign in as manager → **People and profiles**. Add your team, then add a
   profile for each identity you apply under and say who runs it. Delete the
   samples.
2. **Batches** → open a cycle. Pick the mode, the cap, and how often the lists
   should rebuild. Then leave it alone.
3. Each person signs in and picks the profile they are working as. Two tabs:
   - **Jobs I applied to** — either *Add manually*, which gives a table where
     every **+ New entry** adds a row stamped with the current Eastern time, or
     *Upload a sheet* for anyone who already keeps a spreadsheet. Any column
     layout works; the mapper guesses and they can correct it.
   - **New jobs** — what this profile has never applied to, refreshed as the
     lists rebuild.
4. Nobody needs to press anything. The lists rebuild on the timer as sheets
   arrive; **Build now** is there if you want it immediately.
5. Work the list in the browser or download it as Excel. Marking jobs
   **applied** or **skipped** as you go is what keeps the next cycle accurate,
   and those marks survive every rebuild.
6. **Close cycle** when the round is done. That stops the rebuilds and stops
   accepting sheets. Reopen it if you closed too early.

Sheets can be any of `.xlsx`, `.xls`, `.csv`, `.tsv`. Only five columns are
read; everything else is ignored.

### Reading the overlap matrix

If two profiles show heavy overlap, they are running near-identical searches.
That is not automatically bad — two candidates covering the same ground is
sometimes the plan — but it means your *discovery* is duplicated even if your
applications are not. Fixing that at the source (different filters, different
boards, split by skill) widens the pool before this tool ever runs.

### What it does not do

It has no way to search a job board. The pool is only ever what your team typed
into their sheets, so a list is "jobs my colleagues found that this profile has
not used", never fresh leads. It also has no notion of skill matching: if a
full-stack profile hands in a sheet, those jobs are offered to your AI profiles
too. Keep unrelated specialisms in separate cycles if that matters to you.

---

## Upgrading an existing database

Version 1 keyed everything on the person who uploaded a sheet. Version 2 keys it
on the profile. The app upgrades itself on first start: it creates one profile
per existing person, carries their whole history onto it, labels every existing
cycle as a `split` cycle (which is what v1 always did), and rebuilds the tables
whose constraints changed. Nothing is lost and the step is idempotent.

Managers get a profile too, since v1 could not rule out that they had uploaded a
sheet. Retire it from **People and profiles** if it is not wanted.

Back up the file first anyway — it is one `cp`.

---

## Deploying

**Docker** (Postgres included):

```bash
JWT_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(48))") \
  docker compose up --build
# app on :8080, API on :8000
docker compose exec api python seed.py
```

**Cheap VPS**, roughly $6/month, no Docker:

```bash
# backend
pip install -r requirements.txt
gunicorn app.main:app -k uvicorn.workers.UvicornWorker -b 127.0.0.1:8000 -w 2

# frontend
npm run build          # serve frontend/dist with nginx, proxy /api to :8000
```

Put nginx in front with a Let's Encrypt certificate. `frontend/nginx.conf`
already has the proxy rule.

### The rebuild timer, when hosted

The timer runs inside the app process, so it only ticks while the app is awake.
On a plan that sleeps when idle — Render's free tier, for one — a cycle left
untouched overnight will not rebuild until someone next opens the page, at which
point it catches up on the first tick. Anything always-on rebuilds exactly on
schedule.

`AUTO_BUILD_TICK_SECONDS` sets how often it looks for due cycles (60 by
default); `0` switches the timer off entirely. Running several workers is safe:
a cycle is claimed with a conditional update before it is built, so only one
worker builds it.

### Before it faces the internet

- Set a real `JWT_SECRET` and remove every seeded account.
- Serve over HTTPS. Tokens are in `sessionStorage`; plain HTTP leaks them.
- Switch `DATABASE_URL` to Postgres and set up backups.
- Set `CORS_ORIGINS` to your real domain only.

---

## Layout

```
backend/
  app/
    main.py       FastAPI app, auth, all routes
    models.py     Tables, and the constraints that carry the guarantees
    matching.py   Fingerprints, fuzzy merge, cover and split — pure functions
    ingest.py     Spreadsheet reading and column auto-detection
    exports.py    Excel output
    schema.py     The v1 -> v2 upgrade
  seed.py         First accounts and profiles, and the sample data generator
  test_matching.py, test_e2e.py

frontend/
  src/
    App.jsx       Shell and role routing
    api.js        Fetch wrapper, token handling, downloads
    views/        Login, BdHome, AdminHome, People
```

All the dispatch logic lives in `matching.py` with no database or framework
imports, so you can change a rule and see the effect from the unit tests in
under a second.

### Tuning the matcher

In `matching.py`:

- `_ID_RULES` — add a pattern when you start using a new job board. This is the
  highest-value change; a native ID beats every other tier. The third element of
  each rule says whether the ID is only unique *within one site*: leave it `True`
  unless the board mints IDs that are unique across the whole internet, because a
  `False` there silently fuses jobs from unrelated boards.
- `fuzzy_merge(threshold=88, client_threshold=82)` — lower these to catch more
  reposts at the risk of fusing genuinely different jobs. Raise them if you see
  distinct jobs being merged.
- `_SUFFIX` — company-name noise words to ignore.

Change any of them, then run `pytest test_matching.py` to see what moved.
