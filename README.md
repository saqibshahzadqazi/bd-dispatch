# Dispatch

Your team hands in the sheet of jobs each profile applied to. The system works
out which postings are the same job across every sheet, shows you how much
effort was spent twice, and gives each profile back the jobs it has never tried.

Then it follows what all that typing turned into: who is interviewing today,
who is free to take work, and how much of it ended in an offer.

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

## Who is behind the profile

A profile is an identity. Somebody has to actually be it.

- The **BD** runs the account and does the applying. On screen: *run by*.
- The **developer** is who the profile sells — the person who sits the
  interview and writes the code. On screen: *developer*.

Two different people, kept apart on purpose. A BD is never handed the
developer's calendar to manage. A developer can never mark a job applied,
because that would put work into a BD's record that the BD did not do, and
retire a posting from the rotation on the strength of somebody who never
applied for it.

What the developer owns is their own information: the email a client replies
to, the resume link the BD attaches, their skills, their rate, the hours they
can actually be reached, and whether they can take work at all.

Those live on the **profile**, not on their account. One developer running two
identities may well send two different resumes into two different markets, and
hanging the fields off the person would force those two to be one.

They keep it current themselves. Routing "here is my new CV" through a manager
is how a stale link ends up on the next fifty applications.

---

## What the applications turned into

Everything above this counts effort — rows typed, duplication avoided, lists
worked through. A team can improve every one of those figures without winning a
single piece of work.

An **interview** is the first thing here that records an outcome.

When a client replies, whoever heard first logs it: the BD who runs the
account, or the developer the client emailed directly. Both may, because both
find out first about half the time, and the one who knows should not have to
ask somebody else to type it in.

- **The time is Eastern.** Always, said out loud on the form and again on every
  row. A BD in Karachi and a developer in Lisbon have to read one appointment
  as the same moment, so the browser never gets to decide what "half past two"
  means — the server does it once and hands back a preformatted string.
- **A double-booking is caught across identities.** Two profiles are two
  candidates as far as a client is concerned. They are also one person's
  Tuesday afternoon, and that is exactly where the clash hides. Booking over an
  existing interview for the same developer is flagged, with what it collides
  with. It is not refused: a reschedule legitimately overlaps the slot it is
  leaving, and an app that argues with the person who was on the call gets
  worked around rather than fixed.
- **The outcome is what moves the numbers** — *next round*, *offer*, *hired*,
  *no*. Recording one also records that the interview happened, because nobody
  says how a call went before it takes place.
- **A cancellation is never a rejection.** A client who pulled out before the
  call turned nobody down, and counting it as one makes a quiet week look like
  a bad one. It stays on the list, greyed, because a slot that vanishes
  silently reads the same as a slot that was never booked.

What comes out of it is the one figure in this product that cannot be improved
by typing faster:

```
applications  ->  interviews  ->  offers  ->  hired
    1,240             34             6          2
                 2.7% of         18% of
                 applications    interviews
```

And the number to read before any of them: **interviews that have been and gone
with nobody saying how they went**. Every rate above is understated until
somebody does, so the app counts them and says so, rather than quietly
reporting a figure it knows is too low.

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

## The dashboards

Both roles land on a dashboard. It is the screen that says what is waiting,
and every route out of it is one button away.

### Yours

Once your manager has opened it for you. It leads on the one number worth acting
on — jobs still sitting unworked on your list — with the
button that takes you to them.

Under it: what you logged this cycle, how much of it a colleague had already
found, how much of your list you have worked through, a fortnight of daily
activity, and a card per profile you run. The duplicate count is the one to
read twice. If ten of the thirty jobs you logged were already on somebody
else's sheet, your search and theirs are covering the same ground, and that is
fixable at the source in a way no amount of dispatching can match.

### The developer's

Their day, not their score.

It opens on the next interview — the time, the client, the identity they are
being sold as, and the button that joins the call. Today's list sits under it,
then what is coming in the fortnight.

Then their own record: how many applications have gone out in their name, how
many became conversations, what came of them. They are entitled to that. It is
their name on every one of those applications.

**My details** is the other half of the screen and the part a BD depends on:
resume link, email, skills, rate, the hours they can be reached — and one
switch that matters more than the rest. **Can you take work?** Marked *booked
up*, it appears on the BD's screen before they apply, because winning an
interview for somebody who cannot start costs the client's goodwill as well as
an afternoon.

Availability saves the moment it is pressed. Everything else on the card waits
for **Save** — a colleague acts on availability within the hour, and a draft
nobody submitted is a developer still quietly showing as free.

### The manager's

The same picture for the whole workspace, plus the things only a manager can
act on:

- **Who has not handed in.** Named, not counted. A cycle cannot be built until
  two profiles have reported in, so this is usually the thing holding it up.
- **Each person, rolled up.** One person may run several profiles, so this is
  the only view that answers "how is Ali doing" rather than "how is Khuram
  doing". **Open** on a row shows you their dashboard as they would see it, with
  the switch that decides whether they can.
- **Every profile**, ranked, clickable. Clicking one opens it: its figures, a
  month of activity, how it has done cycle by cycle, and the last twenty jobs
  it logged.
- **Duplicated effort over time.** The share of the team's typing that two
  profiles spent on the same posting, cycle by cycle. It is the number this
  whole tool exists to bring down, and the only place you can see whether it
  is going down.
- **What it all produced.** The funnel for the whole workspace, today's
  interviews by name and hour, and the count of interviews nobody has reported
  back on.
- **The developers.** Who is behind each profile, whether they could start on
  Monday, and what is in their diary. **Open** on a row is that developer's own
  screen, and outcomes can be recorded from it — the person chasing them is
  usually the one looking.

### Who may see whose numbers

Two switches, and they answer different questions. The manager sees everything
whatever they are set to.

**1. May this person see their own figures?**

Nobody gets a dashboard until the manager opens it, one person at a time. A new
account starts closed. Being measured on a screen should be a decision somebody
made, not a side effect of having a login.

The manager opens **Dashboard → Their dashboard**, hits **Open** on somebody's
row, and is looking at that person's dashboard — the real one, the same
component fed the same payload, so what you check before opening it is exactly
what they will get. The switch to hand it over sits on top of it. It is also in
the **Dashboard** column of **People and profiles** for when you already know.

Closing it takes nothing away from the work. Their list, the sheet they hand in,
everything under **My work** is untouched — only the screen of figures goes, and
the tab with it.

**2. May they see each other?**

The **team board** — every profile side by side, ranked — is the manager's by
default. One workspace-wide switch opens it to everybody who already has a
dashboard of their own; it never reaches somebody whose own is still closed.

Open it when the team should see the duplication they are creating between
them; leave it shut when a ranking is not what they need. One profile can be
taken off it without hiding everyone, from **People and profiles** or the
switch under the board. It stays on the manager's screen.

**3. And the developers?**

Neither switch touches them, deliberately. Both exist so that nobody is
*measured* on a screen without somebody deciding to measure them. A developer's
screen is their own calendar and their own resume — withholding it protects
nobody and just means they miss the call.

They see the identities they are sold under and nothing else. Another
developer's diary, another profile's list of jobs, the team board: all refused
on the server, not merely absent from the tabs.

Nobody ever sees another profile's *jobs*. The board carries totals; the
drill-down into one profile's record refuses anyone but its owner, its
developer, and the manager.

Both checks are on the server. A closed dashboard is not a hidden tab — it is a
`403`, and the tab is hidden only so nobody walks into one.

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

| Email | Password | Role | Profile |
|---|---|---|---|
| `admin@example.com` | `admin12345` | Manager | — |
| `ali@example.com` | `bdpass12345` | BD | applies as Khuram |
| `sara@example.com` | `bdpass12345` | BD | applies as Zahid |
| `hina@example.com` | `bdpass12345` | BD | applies as Nadia |
| `khuram.dev@example.com` | `devpass12345` | Developer | *is* Khuram |
| `zahid.dev@example.com` | `devpass12345` | Developer | *is* Zahid |
| `nadia.dev@example.com` | `devpass12345` | Developer | *is* Nadia |

The seed also writes a diary — two interviews today, some ahead, some behind,
and one that happened yesterday with no outcome recorded, so the screens have
something on them. It is skipped entirely once a single interview exists, so
re-running the seed never doubles anybody up.

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
   Khuram has touched before. **Who you are applying as** at the top carries
   Khuram's resume link and email, one click from being pasted into an
   application.
6. Still as Ali, open **Interviews** and log one for this afternoon. Sign out,
   sign in as `khuram.dev@example.com`, and it is at the top of their screen —
   nothing was emailed and nobody was told.

**Or let the tests do it:**

```bash
cd backend
pytest test_matching.py -v      # 26 rules: fingerprints, fuzzy merge, both modes
pytest test_e2e.py -v -s        # full round trip, prints the report
pytest test_dashboard.py -v     # the figures, and who may see whose
pytest test_developer.py -v     # the developer side: the clock, the clash, the funnel
pytest                          # all of it
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

1. Sign in as manager → **People and profiles**. Add your team — BDs, and a
   **developer** account for each person your profiles actually sell. Then add
   a profile per identity and say two things about it: which BD runs it, and
   which developer it is. Delete the samples. Decide there, or later from the
   dashboard, who gets to see their own figures — a new BD starts without, and
   a developer does not need the switch at all.
2. **Batches** → open a cycle. Pick the mode, the cap, and how often the lists
   should rebuild. Then leave it alone.
3. Each developer signs in once to fill in their own card under **My
   details** — resume link, email, skills, rate, hours. Nothing else asks them
   for it, and a profile with no resume link is a BD applying with nothing to
   attach.
4. Each BD signs in and picks the profile they are working as. Three tabs:
   - **Jobs I applied to** — either *Add manually*, which gives a table where
     every **+ New entry** adds a row stamped with the current Eastern time, or
     *Upload a sheet* for anyone who already keeps a spreadsheet. Any column
     layout works; the mapper guesses and they can correct it.
   - **New jobs** — what this profile has never applied to, refreshed as the
     lists rebuild.
   - **Interviews** — replies that turned into conversations, and the outcomes.
5. Nobody needs to press anything. The lists rebuild on the timer as sheets
   arrive; **Build now** is there if you want it immediately. **Dashboard**
   shows you who has handed in, who is working their list and who is not,
   without opening anything.
5. Work the list in the browser or download it as Excel. Marking jobs
   **applied** or **skipped** as you go is what keeps the next cycle accurate,
   and those marks survive every rebuild.
6. When a client replies, open **Interviews** and log it. Pick the identity,
   the time in Eastern, who the client is. It lands on the developer's screen
   without anybody forwarding an email, and you are told there and then if it
   collides with something they already have.
7. Afterwards, somebody records how it went — the developer usually, since they
   were in the room. That single field is what makes every rate in the app
   mean anything.
8. **Close cycle** when the round is done. That stops the rebuilds and stops
   accepting sheets. Reopen it if you closed too early. Interviews are not
   attached to a cycle and are unaffected: a reply that arrives three weeks
   late belongs to the work that earned it.

Sheets can be any of `.xlsx`, `.xls`, `.csv`, `.tsv`. Only five columns are
read; everything else is ignored.

### Reading the overlap matrix

If two profiles show heavy overlap, they are running near-identical searches.
That is not automatically bad — two candidates covering the same ground is
sometimes the plan — but it means your *discovery* is duplicated even if your
applications are not. Fixing that at the source (different filters, different
boards, split by skill) widens the pool before this tool ever runs.

### What it does not do

It sends no email and no notification. An interview logged here appears on the
developer's screen the next time it refreshes, which is within the minute, and
nowhere else. If somebody needs a phone to buzz, that is still a phone.

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

Version 2.2 added the developer behind a profile, and interviews. That one is
purely additive — a new table and eight optional columns, all empty — so
upgrading to it is a restart and nothing else. Every existing profile carries
on with nobody behind it and no diary, which is exactly how it behaved before
the columns existed, until a manager attaches somebody.

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
    dashboard.py  Progress figures — read-only queries, no writes anywhere
    interviews.py The diary and the funnel — read-only too
    ingest.py     Spreadsheet reading and column auto-detection
    exports.py    Excel output
    schema.py     The v1 -> v2 upgrade
  seed.py         First accounts, profiles, developers and the sample data
  test_matching.py, test_e2e.py, test_dashboard.py, test_developer.py

frontend/
  src/
    App.jsx       Shell and role routing
    api.js        Fetch wrapper, token handling, downloads
    views/
      Login.jsx            Sign in
      PersonDashboard.jsx  One person's progress — the screen itself
      Dashboard.jsx        Fetches it for the person whose it is
      ManagerDashboard.jsx The workspace, each person, and the two switches
      BdHome.jsx           Logging jobs and working the list
      DevHome.jsx          A developer's day — the diary and their record
      DevProfiles.jsx      What a client is handed, kept by the developer
      Interviews.jsx       Scheduling and the diary — one component, three screens
      AdminHome.jsx        Running cycles
      People.jsx           People, profiles, developers, and who is on the board
      widgets.jsx          Tiles, sparklines, progress bars, the board, the funnel
```

`dashboard.py` and `interviews.py` never write. A dashboard can be opened while
the timer is halfway through rebuilding a cycle without disturbing it.

Every interview timestamp is stored UTC and converted exactly once, in
`models.working_label`, which hands the browser the day, the time, a label and
the value a `datetime-local` input wants back. Nothing in the browser does date
arithmetic, so there is no second implementation of "what day is that" to drift
away from the first.

`PersonDashboard.jsx` is rendered by both the person it belongs to and the
manager looking at them — same component, same payload, one `viewingAs` prop
that changes "your list" to "Ali's list" and removes the buttons that would put
a manager inside somebody else's work. There is no second, approximate copy of
that screen to drift out of step with the real one.

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
