"""Interviews, and what the applications turned into.

Reads only. Writing an interview is four lines in main.py and needs no help;
what needs help is answering the questions the screens actually ask, and every
one of them is a variation on "what is next, and did the last one work".

The distinction this module exists to hold:

  draft       a client replied and somebody started the row from the job
              record. No time is agreed yet, so it is in no rate, no funnel and
              no count of what is coming — none of that is true of it. It is
              its own list on every screen, because a reply nobody has answered
              is a thing to chase, not a thing to forget.
  scheduled   somebody agreed a time. It has not happened yet.
  done        it happened. `outcome` then says what came of it.
  no_show     it did not happen and nobody said so beforehand.
  cancelled   called off. Never counted in a rate — a client who pulled out
              before the call did not reject anybody, and counting it as a
              rejection would make a quiet week look like a bad one.

A `stage` runs across all of that: screening, technical, assessment, final,
offer. Where a conversation died matters more than that it died — a team losing
everyone at technical has a different problem from one losing them at final —
so the stage is carried on every row and counted in `by_stage` below.

`awaiting_outcome` is the number worth putting on a screen: interviews whose
time has come and gone while the status still says `scheduled`. Nobody has said
how they went, so every rate below is quietly understated until they do.

All timestamps are stored UTC and read back on the team's clock, because a BD
in Karachi and a developer in Lisbon have to see one interview as the same
moment. models.working_label does that conversion once, on the server, so no
screen has to.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import (INTERVIEW_STAGES, Application, BatchApplication, Interview,
                     Job, Profile, User, utcnow, working_label, working_today)

UPCOMING_DAYS = 14        # how far ahead "coming up" looks
RECENT_ROWS = 10          # how far back the finished list goes

# An interview that never happened is not a rejection, so these are the rows a
# rate is worked out over. `draft` is out for a different reason: nobody has
# agreed a time, so there is no conversation yet to have a rate about.
LIVE = ("scheduled", "done", "no_show")
WON = ("offer", "hired")
CLEARED = ("passed", "offer", "hired")


def _pct(part: int, whole: int) -> int:
    return round(100 * part / whole) if whole else 0


def _naive_utc(value: dt.datetime) -> dt.datetime:
    """Stored timestamps are naive UTC; utcnow() is aware. Comparing the two
    raises, so the marker comes off before anything is compared."""
    return value.replace(tzinfo=None) if value.tzinfo else value


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #

def load(db: Session, profile_ids: Optional[Sequence[int]] = None,
         *, include_cancelled: bool = True) -> list[Interview]:
    """Every interview for these profiles, soonest first.

    `profile_ids=None` means the whole workspace, which only a manager ever
    asks for. An empty list means this person is attached to no profile at all
    and the honest answer is nothing — not everything.
    """
    if profile_ids is not None and not profile_ids:
        return []
    query = select(Interview)
    if profile_ids is not None:
        query = query.where(Interview.profile_id.in_(list(profile_ids)))
    if not include_cancelled:
        query = query.where(Interview.status != "cancelled")
    return list(db.scalars(query.order_by(Interview.scheduled_at)))


def decorate(db: Session, rows: Sequence[Interview]) -> list[dict]:
    """Interview rows as the browser wants them.

    Two queries whatever the size of the list: the profiles behind the rows,
    and the people behind the profiles. The names are denormalised in rather
    than left as ids, because every screen that shows an interview shows who it
    is for and who is running it.
    """
    if not rows:
        return []
    profile_ids = {row.profile_id for row in rows}
    profiles = {p.id: p for p in db.scalars(
        select(Profile).where(Profile.id.in_(profile_ids)))}
    # The posting the conversation came from. Carried onto the row so a BD
    # reading a client's reply three weeks later has the wording that was
    # applied to, without going back to the job record to find it.
    job_ids = {row.job_id for row in rows} - {None}
    jobs = {j.id: j for j in db.scalars(
        select(Job).where(Job.id.in_(job_ids)))} if job_ids else {}
    wanted = {p.user_id for p in profiles.values()} | {p.dev_user_id for p in profiles.values()}
    # Whoever said how it went, which is usually but not always the developer
    # currently behind the profile — a profile can be handed on after the call.
    wanted |= {row.reported_by for row in rows}
    wanted.discard(None)
    people = {u.id: u for u in db.scalars(select(User).where(User.id.in_(wanted)))} if wanted else {}

    today = working_today()
    now = _naive_utc(utcnow())

    out = []
    for row in rows:
        profile = profiles.get(row.profile_id)
        developer = people.get(profile.dev_user_id) if profile else None
        runner = people.get(profile.user_id) if profile else None
        job = jobs.get(row.job_id)
        when = working_label(row.scheduled_at)
        day = dt.date.fromisoformat(when["day"])
        # A draft is parked an hour out and means nothing by it, so it is never
        # "past" and never in the count of things nobody reported on.
        gone = row.status != "draft" and _naive_utc(row.scheduled_at) < now
        out.append({
            "id": row.id,
            "profile_id": row.profile_id,
            "profile": profile.name if profile else "?",
            "headline": profile.headline if profile else "",
            "developer": developer.name if developer else None,
            "developer_id": profile.dev_user_id if profile else None,
            "bd": runner.name if runner else None,
            "job_id": row.job_id,
            "client": row.client,
            "role": row.role,
            "mode": row.mode,
            "link": row.link,
            "status": row.status,
            "stage": row.stage or "screening",
            "is_draft": row.status == "draft",
            # What the job record holds, when the interview came from one.
            "job": ({"id": job.id, "title": job.title or "", "company": job.company or "",
                     "url": job.url or "", "description_url": job.description_url or "",
                     "platform": job.platform or ""} if job else None),
            "outcome": row.outcome,
            # The two halves of the row, kept apart. `notes` is the BD's brief,
            # written when it was booked; `debrief` is what the person in the
            # room said afterwards.
            "notes": row.notes,
            "debrief": row.debrief or "",
            "reported_by": (people[row.reported_by].name
                            if row.reported_by in people else None),
            "reported_at": (working_label(row.reported_at)["label"]
                            if row.reported_at else None),
            "duration_minutes": row.duration_minutes,
            "when": when,
            "is_today": day == today,
            "is_past": gone,
            # The nag: it has happened and nobody has said how it went.
            "awaiting_outcome": gone and row.status == "scheduled",
        })
    return out


def split(rows: Sequence[dict], upcoming_days: int = UPCOMING_DAYS,
          recent: int = RECENT_ROWS) -> dict:
    """One decorated list, cut into the three lists a screen shows.

    Today keeps everything, including an interview that finished an hour ago —
    a person looking at their day wants the whole of it, not the rest of it.
    """
    today = working_today()
    horizon = today + dt.timedelta(days=upcoming_days)

    now: list[dict] = []
    soon: list[dict] = []
    done: list[dict] = []
    waiting: list[dict] = []
    for row in rows:
        day = dt.date.fromisoformat(row["when"]["day"])
        if row["status"] == "draft":
            # Never in the diary — there is no time in it to be in the diary
            # with. Newest first: the reply that just came in is the one
            # somebody is about to answer.
            waiting.append(row)
            continue
        if row["status"] == "cancelled":
            # Kept in the upcoming list rather than dropped, because a slot
            # that vanishes silently reads exactly like a slot that was never
            # booked. Still bounded by the horizon — a cancellation in
            # November is not news in August.
            if today <= day <= horizon:
                soon.append(row)
            continue
        if day == today:
            now.append(row)
        elif day > today:
            if day <= horizon:
                soon.append(row)
        else:
            done.append(row)

    soon.sort(key=lambda r: r["when"]["iso"])
    done.sort(key=lambda r: r["when"]["iso"], reverse=True)
    waiting.sort(key=lambda r: r["id"], reverse=True)
    return {"today": now, "upcoming": soon, "recent": done[:recent],
            "awaiting_time": waiting}


def counts(rows: Sequence[dict]) -> dict:
    """The figures a headline is made of."""
    today = working_today()
    week = today + dt.timedelta(days=7)
    live = [row for row in rows if row["status"] not in ("cancelled", "draft")]
    return {
        # Replies somebody started and has not agreed a time for. The one
        # number on this screen that is a thing to go and do.
        "awaiting_time": sum(1 for row in rows if row["status"] == "draft"),
        "today": sum(1 for row in live if row["is_today"]),
        "week": sum(1 for row in live
                    if today <= dt.date.fromisoformat(row["when"]["day"]) <= week),
        "scheduled": sum(1 for row in live if not row["is_past"]),
        "awaiting_outcome": sum(1 for row in live if row["awaiting_outcome"]),
        "total": len(live),
    }


def summary(db: Session, profile_ids: Optional[Sequence[int]] = None) -> dict:
    """Today, what is coming, what just happened, and the counts behind them."""
    rows = decorate(db, load(db, profile_ids))
    return {**split(rows), "counts": counts(rows)}


# --------------------------------------------------------------------------- #
# The funnel
# --------------------------------------------------------------------------- #

def funnel(db: Session, profile_ids: Optional[Sequence[int]] = None,
           batch_id: Optional[int] = None) -> dict:
    """Applications in, interviews out, offers at the end of it.

    The first figure in this product that a team cannot improve by typing
    faster. Every other number here goes up when people work harder; this one
    only goes up when the work was worth sending, which is why it is the one
    worth steering by.

    `applications` is all-time by default, and this cycle's when a cycle is
    named. Interviews are never filtered by cycle: a reply that arrives three
    weeks after the application belongs to the work that earned it, not to
    whatever cycle happened to be open when the client got round to answering.
    Filtering them would credit the wrong fortnight and flatter a slow week.
    """
    if batch_id:
        query = select(func.count(BatchApplication.id)).where(
            BatchApplication.batch_id == batch_id)
        if profile_ids is not None:
            query = query.where(BatchApplication.profile_id.in_(list(profile_ids)))
    else:
        query = select(func.count(Application.id))
        if profile_ids is not None:
            query = query.where(Application.profile_id.in_(list(profile_ids)))
    applications = db.scalar(query) or 0

    rows = load(db, profile_ids)
    live = [row for row in rows if row.status in LIVE]
    passed = sum(1 for row in live if row.outcome in CLEARED)
    offers = sum(1 for row in live if row.outcome in WON)
    hired = sum(1 for row in live if row.outcome == "hired")

    return {
        "applications": applications,
        "interviews": len(live),
        "passed": passed,
        "offers": offers,
        "hired": hired,
        "cancelled": sum(1 for row in rows if row.status == "cancelled"),
        "rejected": sum(1 for row in live if row.outcome == "rejected"),
        # Replies with no time agreed. Not part of any rate — nothing has
        # happened — but the number a team should clear before reading the
        # rest, because each one is a client waiting on an answer.
        "awaiting_time": sum(1 for row in rows if row.status == "draft"),
        "by_stage": by_stage(live),
        # Out of a hundred applications, how many got somebody talking.
        "interview_rate": _pct(len(live), applications),
        # Out of a hundred conversations, how many ended in an offer.
        "offer_rate": _pct(offers, len(live)),
        "scoped_to_cycle": bool(batch_id),
    }


# --------------------------------------------------------------------------- #
# Developers
# --------------------------------------------------------------------------- #

def by_stage(rows: Sequence[Interview]) -> list[dict]:
    """How many conversations reached each rung, and how many died there.

    The figure the funnel above cannot show. A team losing everybody at
    `technical` has a tooling problem; a team losing them at `final` has a
    rate or an availability problem, and those call for opposite fixes. Both
    look identical in a single interviews-to-offers percentage.

    `reached` counts every sitting at that rung. `cleared` is the ones that went
    on — an outcome of passed, offer or hired. `lost` is the ones that ended
    there. The rest are still open, which is why the three do not sum.
    """
    out = []
    for stage in INTERVIEW_STAGES:
        here = [row for row in rows if (row.stage or "screening") == stage]
        if not here:
            out.append({"stage": stage, "reached": 0, "cleared": 0, "lost": 0, "rate": 0})
            continue
        cleared = sum(1 for row in here if row.outcome in CLEARED)
        lost = sum(1 for row in here if row.outcome == "rejected")
        out.append({"stage": stage, "reached": len(here), "cleared": cleared,
                    "lost": lost, "rate": _pct(cleared, len(here))})
    return out


def developer_rows(db: Session) -> list[dict]:
    """Every developer, with the identities they are sold under.

    The manager's answer to "who is actually free next week". A developer with
    no profile attached is still listed: an account that can sign in and sees
    nothing is a thing somebody needs to notice and fix, not a row to hide.
    """
    devs = list(db.scalars(select(User).where(User.role == "dev",
                                              User.is_active == True)  # noqa: E712
                           .order_by(User.name)))
    if not devs:
        return []

    profiles = list(db.scalars(select(Profile).where(
        Profile.is_active == True,  # noqa: E712
        Profile.dev_user_id.in_([u.id for u in devs]))))
    by_dev: dict[int, list[Profile]] = defaultdict(list)
    for profile in profiles:
        by_dev[profile.dev_user_id].append(profile)

    rows = decorate(db, load(db, [p.id for p in profiles])) if profiles else []
    per_profile: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        per_profile[row["profile_id"]].append(row)

    out = []
    for dev in devs:
        theirs = by_dev.get(dev.id, [])
        mine = [row for profile in theirs for row in per_profile.get(profile.id, [])]
        tally = counts(mine)
        # The busiest state wins: a developer running one open profile and one
        # booked one is not simply "open", and a BD needs to see the harder
        # answer rather than the more convenient one.
        states = {p.availability or "open" for p in theirs}
        availability = ("booked" if "booked" in states
                        else "limited" if "limited" in states
                        else "open" if states else "")
        out.append({
            "user_id": dev.id, "name": dev.name, "email": dev.email,
            "availability": availability,
            "profiles": [{"id": p.id, "name": p.name, "headline": p.headline,
                          "availability": p.availability or "open",
                          "resume_url": p.resume_url or "",
                          "skills": p.skills or ""} for p in theirs],
            "runs": len(theirs),
            **tally,
        })
    out.sort(key=lambda row: (-row["week"], -row["scheduled"], row["name"]))
    return out


def for_developer(db: Session, dev: User, profiles: Sequence[Profile]) -> dict:
    """Everything one developer's own screen is made of.

    Deliberately not gated behind the dashboard switch the BDs have. That
    switch exists because being measured on a screen should be somebody's
    decision — but this screen is not a measurement of the developer, it is
    their own calendar and their own resume. Withholding it would only mean
    nobody turns up to the interview.
    """
    ids = [p.id for p in profiles]
    rows = decorate(db, load(db, ids))
    return {
        "developer": {"id": dev.id, "name": dev.name, "email": dev.email},
        **split(rows),
        "counts": counts(rows),
        "funnel": funnel(db, ids),
    }


def next_up(rows: Sequence[dict]) -> Optional[dict]:
    """The soonest interview still ahead, or None. What a headline points at."""
    ahead = [row for row in rows
             if not row["is_past"] and row["status"] == "scheduled"]
    return min(ahead, key=lambda row: row["when"]["iso"]) if ahead else None
