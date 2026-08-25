"""Progress figures for the dashboards.

Reads only. Nothing here writes, so opening a dashboard can never disturb a
cycle that is mid-rebuild — which matters, because the lists rebuild on a timer
while people are looking at them.

Three words that look alike and are not:

  sheet rows  what a profile physically handed in — the raw line count.
  logged      distinct jobs that sheet turned into, counted after
              fingerprinting, so one posting listed twice under two different
              links counts once.
  assigned    what this cycle put on that profile's list. What it has been
              handed, not what it has done.

Work done is `applied`. Work declined is `skipped`. Everything still waiting is
`pending` — and only `pending` rows are thrown away and rebuilt by the timer,
which is why nothing here measures the age of an assignment. That number would
reset every ten minutes and mean nothing.

Queries are grouped over a whole cycle rather than filtered to a list of
profiles: one query answers for everybody, the caller keeps the rows it wants,
and there is no IN (...) to outgrow SQLite's bound-parameter limit.
"""
from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import assessments, interviews
from .models import (Application, Assignment, Batch, BatchApplication, Job,
                     Profile, Upload, User, to_working, working_today)

ACTIVITY_DAYS = 14        # the strip on a BD's own dashboard
ORG_ACTIVITY_DAYS = 30    # the manager sees further back
HISTORY_CYCLES = 8
RECENT_ROWS = 20
CYCLE_PICKER = 24

# Summed the same way everywhere: a person's row is their profiles added up,
# and the workspace row is every profile added up.
ROLLUP_KEYS = ("sheet_rows", "logged", "duplicates", "assigned",
               "applied", "skipped", "pending", "all_time")


def _pct(part: int, whole: int) -> int:
    return round(100 * part / whole) if whole else 0


def _working_day(value: Optional[dt.datetime]) -> Optional[dt.date]:
    """The team's calendar day for a stored UTC timestamp.

    models.to_working does the conversion — one implementation, so a chart and
    an interview can never disagree about which day something happened on.
    """
    return None if value is None else to_working(value).date()


def _today() -> dt.date:
    return working_today()


def blank_stats() -> dict:
    return {"sheet_rows": 0, "logged": 0, "duplicates": 0, "assigned": 0,
            "applied": 0, "skipped": 0, "pending": 0, "done_pct": 0, "applied_pct": 0}


# --------------------------------------------------------------------------- #
# Activity over time
# --------------------------------------------------------------------------- #

def activity(db: Session, profile_ids: Optional[Sequence[int]] = None,
             days: int = ACTIVITY_DAYS) -> list[dict]:
    """Jobs logged per working day, oldest first.

    Always exactly `days` long, zeros included, so the strip keeps its shape on
    a quiet week instead of collapsing to a couple of bars.
    """
    today = _today()
    window = [today - dt.timedelta(days=n) for n in range(days - 1, -1, -1)]
    if profile_ids is not None and not profile_ids:
        return [{"day": day.isoformat(), "count": 0} for day in window]

    # A day either side of the window in UTC: which working day a timestamp
    # belongs to is decided after the conversion, not by the filter.
    cutoff = (dt.datetime.now(dt.timezone.utc)
              - dt.timedelta(days=days + 1)).replace(tzinfo=None)
    query = select(Application.created_at).where(Application.created_at >= cutoff)
    if profile_ids is not None:
        query = query.where(Application.profile_id.in_(list(profile_ids)))

    tally: Counter = Counter()
    for (stamp,) in db.execute(query).all():
        day = _working_day(stamp)
        if day is not None:
            tally[day] += 1
    return [{"day": day.isoformat(), "count": tally.get(day, 0)} for day in window]


def streak(series: Sequence[dict]) -> int:
    """Consecutive working days up to today with at least one job logged.

    Today not being started yet is not a broken streak, so a zero on today alone
    is forgiven. A zero on the day before it is not.
    """
    counts = [row["count"] for row in series]
    if not counts:
        return 0
    walk = counts[:-1] if counts[-1] == 0 else counts
    run = 0
    for count in reversed(walk):
        if count <= 0:
            break
        run += 1
    return run


# --------------------------------------------------------------------------- #
# Per-profile figures
# --------------------------------------------------------------------------- #

def cycle_stats(db: Session, batch_id: Optional[int]) -> dict[int, dict]:
    """Every profile's figures for one cycle, keyed by profile id."""
    stats: dict[int, dict] = defaultdict(blank_stats)
    if not batch_id:
        return dict(stats)

    for profile_id, rows in db.execute(
        select(Upload.profile_id, func.sum(Upload.row_count))
        .where(Upload.batch_id == batch_id)
        .group_by(Upload.profile_id)
    ).all():
        if profile_id is not None:
            stats[profile_id]["sheet_rows"] = int(rows or 0)

    # A job two profiles both logged is the duplicated effort this whole product
    # exists to surface, so it is counted against each of them.
    by_job: dict[int, set[int]] = defaultdict(set)
    for job_id, profile_id in db.execute(
        select(BatchApplication.job_id, BatchApplication.profile_id)
        .where(BatchApplication.batch_id == batch_id)
    ).all():
        by_job[job_id].add(profile_id)
    for holders in by_job.values():
        shared = len(holders) > 1
        for profile_id in holders:
            stats[profile_id]["logged"] += 1
            if shared:
                stats[profile_id]["duplicates"] += 1

    for profile_id, status, count in db.execute(
        select(Assignment.profile_id, Assignment.status, func.count(Assignment.id))
        .where(Assignment.batch_id == batch_id)
        .group_by(Assignment.profile_id, Assignment.status)
    ).all():
        row = stats[profile_id]
        row["assigned"] += count
        if status in ("applied", "skipped", "pending"):
            row[status] += count

    for row in stats.values():
        row["done_pct"] = _pct(row["applied"] + row["skipped"], row["assigned"])
        row["applied_pct"] = _pct(row["applied"], row["assigned"])
    return dict(stats)


def all_time(db: Session) -> dict[int, int]:
    """Applications each profile has ever recorded, across every cycle."""
    return {profile_id: count for profile_id, count in db.execute(
        select(Application.profile_id, func.count(Application.id))
        .group_by(Application.profile_id)).all() if profile_id is not None}


def last_logged(db: Session) -> dict[int, dt.datetime]:
    return {profile_id: stamp for profile_id, stamp in db.execute(
        select(Application.profile_id, func.max(Application.created_at))
        .group_by(Application.profile_id)).all() if profile_id is not None}


def profile_rows(db: Session, profiles: Sequence[Profile], batch_id: Optional[int],
                 owners: dict[int, str]) -> list[dict]:
    """One row per profile, busiest first."""
    stats = cycle_stats(db, batch_id)
    totals = all_time(db)
    latest = last_logged(db)
    # Take-homes outstanding against each identity. On the row rather than in a
    # separate block, because a board that shows how much a profile applied for
    # while saying nothing about the test it owes a client is showing the half
    # of the picture that cannot lose the work.
    tests = assessments.by_profile(db, [p.id for p in profiles] if profiles else [])

    rows = []
    for profile in profiles:
        stamp = latest.get(profile.id)
        theirs = tests.get(profile.id) or {}
        rows.append({
            "profile_id": profile.id,
            "name": profile.name,
            "headline": profile.headline,
            "platform": profile.platform,
            "user_id": profile.user_id,
            "person": owners.get(profile.user_id),
            # Who the client would actually be meeting, and whether they could
            # take the work. Blank on a profile nobody has been attached to.
            "dev_user_id": profile.dev_user_id,
            "developer": owners.get(profile.dev_user_id),
            "availability": profile.availability or "open",
            # A NULL here is a row that predates the column, and the default is
            # to share — so only an explicit False takes a profile off the board.
            "shared": profile.share_progress is not False,
            "all_time": totals.get(profile.id, 0),
            "last_logged": stamp.isoformat() if stamp else None,
            "assessments_open": theirs.get("open", 0),
            "assessments_overdue": theirs.get("overdue", 0),
            **(stats.get(profile.id) or blank_stats()),
        })
    rows.sort(key=lambda row: (-row["applied"], -row["logged"], row["name"]))
    return rows


def duplication(db: Session, batch_id: Optional[int]) -> dict:
    """Duplicated effort across a whole cycle, counted once per posting.

    Adding up each profile's own duplicate count is the wrong sum here. A job
    Khuram and Zahid both logged appears in both their counts, so two profiles
    finding one posting reads as two duplicated jobs. That figure is right on a
    profile's own row — "ten of the jobs you logged, a colleague had too" — and
    wrong for the team, where the honest questions are how many postings were
    found more than once, and how many rows of typing that cost.

    Both are reported: `duplicates` is the postings, `wasted_rows` is the
    typing. They match the cycle report's own two lines.
    """
    blank = {"duplicates": 0, "wasted_rows": 0, "logged_rows": 0, "duplicate_pct": 0}
    if not batch_id:
        return blank

    by_job: dict[int, set[int]] = defaultdict(set)
    for job_id, profile_id in db.execute(
        select(BatchApplication.job_id, BatchApplication.profile_id)
        .where(BatchApplication.batch_id == batch_id)
    ).all():
        by_job[job_id].add(profile_id)

    found_twice = sum(1 for holders in by_job.values() if len(holders) > 1)
    wasted = sum(len(holders) - 1 for holders in by_job.values() if len(holders) > 1)
    rows = sum(len(holders) for holders in by_job.values())
    return {"duplicates": found_twice, "wasted_rows": wasted,
            "logged_rows": rows, "duplicate_pct": _pct(wasted, rows)}


def _rollup(rows: Sequence[dict]) -> dict:
    summed = {key: sum(row[key] for row in rows) for key in ROLLUP_KEYS}
    summed["done_pct"] = _pct(summed["applied"] + summed["skipped"], summed["assigned"])
    summed["applied_pct"] = _pct(summed["applied"], summed["assigned"])
    summed["duplicate_pct"] = _pct(summed["duplicates"], summed["logged"])
    return summed


# --------------------------------------------------------------------------- #
# Cycles
# --------------------------------------------------------------------------- #

def _brief(batch: Optional[Batch]) -> Optional[dict]:
    if batch is None:
        return None
    return {"id": batch.id, "name": batch.name, "status": batch.status,
            "mode": batch.mode, "quota": batch.quota,
            "auto_build_minutes": batch.auto_build_minutes or 0,
            "last_built_at": batch.last_built_at.isoformat() if batch.last_built_at else None,
            "report": batch.report or {}}


def pick_batch(db: Session, batch_id: Optional[int]) -> Optional[Batch]:
    """The cycle a dashboard should open on: the one asked for, else the newest
    cycle still running, else the newest there is."""
    if batch_id:
        return db.get(Batch, batch_id)
    running = db.scalars(select(Batch).where(Batch.status == "open")
                         .order_by(Batch.id.desc()).limit(1)).first()
    return running or db.scalars(select(Batch).order_by(Batch.id.desc()).limit(1)).first()


def cycle_list(db: Session, limit: int = CYCLE_PICKER) -> list[dict]:
    return [{"id": b.id, "name": b.name, "status": b.status}
            for b in db.scalars(select(Batch).order_by(Batch.id.desc()).limit(limit))]


def history(db: Session, limit: int = HISTORY_CYCLES) -> list[dict]:
    """Recent built cycles, oldest first so a trend reads left to right.

    The duplicate rate is the number worth watching: the share of the team's
    typing that two profiles spent on the same posting. It should fall as people
    split their searches up, and this is the only place that shows whether it is.
    """
    built = db.scalars(select(Batch).where(Batch.last_built_at.is_not(None))
                       .order_by(Batch.id.desc()).limit(limit)).all()
    out = []
    for batch in reversed(built):
        report = batch.report or {}
        rows_read = int(report.get("Rows read") or 0)
        duplicates = int(report.get("Duplicate applications") or 0)
        out.append({
            "id": batch.id, "name": batch.name, "status": batch.status,
            "built_at": batch.last_built_at.isoformat() if batch.last_built_at else None,
            "rows_read": rows_read,
            "unique_jobs": int(report.get("Unique jobs") or 0),
            "duplicates": duplicates,
            "dispatched": int(report.get("Jobs put on a list") or 0),
            "duplicate_pct": _pct(duplicates, rows_read),
        })
    return out


# --------------------------------------------------------------------------- #
# The three dashboards
# --------------------------------------------------------------------------- #

def for_person(db: Session, user: User, batch: Optional[Batch],
               team_visible: bool) -> dict:
    """What one person sees about their own work.

    A manager gets every profile here, because a manager who also runs one
    should still see it. The workspace-wide picture is a different screen.
    """
    query = select(Profile).where(Profile.is_active == True)  # noqa: E712
    if user.role != "admin":
        query = query.where(Profile.user_id == user.id)
    mine = list(db.scalars(query.order_by(Profile.name)))
    owners = {u.id: u.name for u in db.scalars(select(User))}

    rows = profile_rows(db, mine, batch.id if batch else None, owners)
    series = activity(db, [p.id for p in mine])

    totals = _rollup(rows)
    totals["profiles"] = len(rows)

    ids = [p.id for p in mine]
    return {"batch": _brief(batch), "batches": cycle_list(db),
            "profiles": rows, "totals": totals,
            "activity": series, "streak": streak(series),
            # What the typing produced. Every other figure on this screen goes
            # up when somebody works harder; these two only go up when the work
            # was worth sending.
            "interviews": interviews.summary(db, ids),
            "funnel": interviews.funnel(db, ids),
            # The third thing a client can ask for, and the one with a deadline
            # on it. A BD who cannot see it here finds out a take-home was
            # missed from the client's next email.
            "assessments": assessments.summary(db, ids),
            "team_visible": team_visible}


def team_board(db: Session, batch: Optional[Batch], include_private: bool) -> dict:
    """Every profile's progress side by side.

    `include_private` is the manager's view. A BD sees only the profiles the
    manager left on the board, and is told how many were held back rather than
    being quietly shown a short list and drawing its own conclusions.
    """
    profiles = list(db.scalars(select(Profile).where(Profile.is_active == True)  # noqa: E712
                               .order_by(Profile.name)))
    owners = {u.id: u.name for u in db.scalars(select(User))}
    rows = profile_rows(db, profiles, batch.id if batch else None, owners)

    hidden = 0
    if not include_private:
        hidden = sum(1 for row in rows if not row["shared"])
        rows = [row for row in rows if row["shared"]]
    for place, row in enumerate(rows, start=1):
        row["rank"] = place

    return {"batch": _brief(batch), "batches": cycle_list(db),
            "rows": rows, "hidden": hidden}


def overview(db: Session, batch: Optional[Batch]) -> dict:
    """The manager's screen: the whole workspace in one pass."""
    profiles = list(db.scalars(select(Profile).where(Profile.is_active == True)  # noqa: E712
                               .order_by(Profile.name)))
    users = list(db.scalars(select(User)))
    owners = {u.id: u.name for u in users}
    batch_id = batch.id if batch else None

    rows = profile_rows(db, profiles, batch_id, owners)
    for place, row in enumerate(rows, start=1):
        row["rank"] = place
    by_profile = {row["profile_id"]: row for row in rows}

    handed_in: set[int] = set()
    if batch_id:
        handed_in = {profile_id for (profile_id,) in db.execute(
            select(Upload.profile_id).where(Upload.batch_id == batch_id)).all()
            if profile_id is not None}

    # Each person, with their profiles rolled up. One person may run several,
    # so this is the only view that answers "how is Ali doing" rather than
    # "how is Khuram doing".
    people = []
    for person in users:
        if not person.is_active:
            continue
        theirs = [by_profile[p.id] for p in profiles if p.user_id == person.id]
        if not theirs and person.role == "admin":
            continue                      # a manager running nothing is not on the report
        rolled = _rollup(theirs)
        stamps = [row["last_logged"] for row in theirs if row["last_logged"]]
        people.append({
            "user_id": person.id, "name": person.name, "email": person.email,
            "role": person.role,
            # Whether they may open the dashboard this row describes. A manager
            # always may, whatever the column says.
            "dashboard_visible": person.role == "admin" or person.dashboard_visible is True,
            "profiles": [{"id": row["profile_id"], "name": row["name"]} for row in theirs],
            "runs": len(theirs),
            "handed_in": sum(1 for p in profiles
                             if p.user_id == person.id and p.id in handed_in),
            "last_logged": max(stamps) if stamps else None,
            **rolled,
        })
    people.sort(key=lambda row: (-row["applied"], -row["logged"], row["name"]))

    # The most actionable line on the screen: a cycle cannot be built until two
    # profiles have reported in, and these are the ones holding it up.
    missing = [{"profile_id": p.id, "name": p.name, "headline": p.headline,
                "person": owners.get(p.user_id)}
               for p in profiles if p.id not in handed_in] if batch_id else []

    org = {
        **_rollup(rows),
        # Overrides the summed per-profile duplicate count, which double-counts
        # a posting every profile that found it. See duplication().
        **duplication(db, batch_id),
        "profiles": len(profiles),
        "people": sum(1 for u in users if u.is_active and u.role == "bd"),
        "open_cycles": db.scalar(select(func.count(Batch.id))
                                 .where(Batch.status == "open")) or 0,
        "handed_in": len(handed_in),
        "expected": len(profiles),
    }

    return {"batch": _brief(batch), "batches": cycle_list(db),
            "org": org, "profiles": rows, "people": people, "missing": missing,
            "activity": activity(db, None, days=ORG_ACTIVITY_DAYS),
            "history": history(db),
            # The other half of the job. Everything above says how much was
            # sent; this says what came back, and who is free to take it.
            "interviews": interviews.summary(db),
            "funnel": interviews.funnel(db),
            "assessments": assessments.summary(db),
            "developers": interviews.developer_rows(db)}


def profile_detail(db: Session, profile: Profile, batch: Optional[Batch]) -> dict:
    """One profile, close up — for a manager checking on somebody, or a BD
    looking at their own record."""
    owners = {u.id: u.name for u in db.scalars(select(User))}
    batch_id = batch.id if batch else None
    stats = profile_rows(db, [profile], batch_id, owners)[0]

    recent = [
        {"title": job.title, "company": job.company, "platform": job.platform,
         "url": job.url, "applied_on": record.applied_on,
         "logged_at": record.created_at.isoformat() if record.created_at else None}
        for record, job in db.execute(
            select(Application, Job).join(Job, Job.id == Application.job_id)
            .where(Application.profile_id == profile.id)
            .order_by(Application.id.desc()).limit(RECENT_ROWS)).all()
    ]

    recent_cycles = db.scalars(select(Batch).order_by(Batch.id.desc()).limit(6)).all()
    per_cycle = []
    if recent_cycles:
        ids = [b.id for b in recent_cycles]
        logged = dict(db.execute(
            select(BatchApplication.batch_id, func.count(BatchApplication.id))
            .where(BatchApplication.batch_id.in_(ids),
                   BatchApplication.profile_id == profile.id)
            .group_by(BatchApplication.batch_id)).all())
        placed: dict[int, dict] = defaultdict(lambda: {"assigned": 0, "applied": 0})
        for cycle_id, status, count in db.execute(
            select(Assignment.batch_id, Assignment.status, func.count(Assignment.id))
            .where(Assignment.batch_id.in_(ids), Assignment.profile_id == profile.id)
            .group_by(Assignment.batch_id, Assignment.status)
        ).all():
            placed[cycle_id]["assigned"] += count
            if status == "applied":
                placed[cycle_id]["applied"] += count
        per_cycle = [{"id": b.id, "name": b.name, "logged": logged.get(b.id, 0),
                      **placed[b.id]} for b in reversed(recent_cycles)]

    series = activity(db, [profile.id], days=ORG_ACTIVITY_DAYS)
    return {
        "batch": _brief(batch), "batches": cycle_list(db),
        "profile": {"id": profile.id, "name": profile.name,
                    "headline": profile.headline, "platform": profile.platform,
                    "person": owners.get(profile.user_id),
                    "shared": profile.share_progress is not False,
                    # The developer, and what a client is handed when this
                    # identity applies.
                    "dev_user_id": profile.dev_user_id,
                    "developer": owners.get(profile.dev_user_id),
                    "email": profile.email or "",
                    "resume_url": profile.resume_url or "",
                    "skills": profile.skills or "",
                    "timezone": profile.timezone or "",
                    "rate": profile.rate or "",
                    "availability": profile.availability or "open",
                    "bio": profile.bio or ""},
        "stats": stats, "activity": series, "streak": streak(series),
        "recent": recent, "cycles": per_cycle,
        "interviews": interviews.summary(db, [profile.id]),
        "funnel": interviews.funnel(db, [profile.id]),
        "assessments": assessments.summary(db, [profile.id]),
    }


def for_developer(db: Session, person: User, batch: Optional[Batch]) -> dict:
    """A developer's own screen.

    The mirror of for_person, and pointed the other way. A BD's dashboard asks
    how much went out; a developer's asks what is coming back and when they
    have to be somewhere. Same cycle figures underneath, because the developer
    is entitled to know how hard their identities are being worked — but the
    thing at the top of the screen is the next interview, not the row count.

    Not gated by `dashboard_visible`. That switch is about being measured
    without anybody deciding to measure you; this is a calendar and a resume,
    and withholding it only means nobody turns up.
    """
    profiles = list(db.scalars(
        select(Profile).where(Profile.is_active == True,  # noqa: E712
                              Profile.dev_user_id == person.id)
        .order_by(Profile.name)))
    owners = {u.id: u.name for u in db.scalars(select(User))}

    rows = profile_rows(db, profiles, batch.id if batch else None, owners)
    # The contact details a BD pastes into an application, alongside the
    # figures, because this is the screen where the developer keeps them right.
    detail = {p.id: p for p in profiles}
    for row in rows:
        profile = detail[row["profile_id"]]
        row.update({"email": profile.email or "",
                    "resume_url": profile.resume_url or "",
                    "skills": profile.skills or "",
                    "timezone": profile.timezone or "",
                    "rate": profile.rate or "",
                    "bio": profile.bio or "",
                    "platform": profile.platform or ""})

    series = activity(db, [p.id for p in profiles], days=ORG_ACTIVITY_DAYS)
    totals = _rollup(rows)
    totals["profiles"] = len(rows)

    return {"batch": _brief(batch), "batches": cycle_list(db),
            "profiles": rows, "totals": totals,
            "activity": series, "streak": streak(series),
            # The take-homes sitting on this developer's weekend. Same reason
            # the diary is here and not behind the dashboard switch: it is not
            # a measurement of them, it is work they have been given.
            "assessments": assessments.summary(db, [p.id for p in profiles]),
            **interviews.for_developer(db, person, profiles)}
