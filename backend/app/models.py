"""Database schema.

The unit of work is a PROFILE, not a person.

A profile is the identity a job is applied under — "Khuram, AI Engineer" on
Upwork. One person may run several; two people may share one during a handover.
What must never happen twice is the same *profile* approaching the same client,
because that is one identity applying twice. Two different profiles applying to
the same posting is not a duplicate at all — it is two candidates in the running,
which is the whole point of running more than one profile.

So every history record hangs off profile_id, and user_id rides along only to
answer "who did the typing".

The constraints that carry the product:

  applications  UNIQUE(job_id, profile_id)
      one identity can log a job only once, ever

  assignments   UNIQUE(batch_id, job_id, profile_id)
      a cycle never puts the same job on one profile's list twice

  assignments   UNIQUE(batch_id, job_id) WHERE exclusive
      only for split cycles, where the manager asked for no two profiles to
      share a job. It is a partial index because coverage cycles deliberately
      hand one job to everybody eligible, and a blanket constraint would
      forbid the normal case.
"""
from __future__ import annotations

import datetime as dt
import os

from sqlalchemy import (JSON, Boolean, Column, DateTime, ForeignKey, Index,
                        Integer, String, Text, UniqueConstraint)
from sqlalchemy.orm import declarative_base

Base = declarative_base()

COVER = "cover"      # everyone gets every job they have not worked
SPLIT = "split"      # one job goes to exactly one profile
MODES = (COVER, SPLIT)


# The team works to Eastern time, so that is what "applied on" means. Stored
# timestamps stay UTC; this is only for the stamp a person reads. Change it here
# and in the browser app's EntryTable if the team ever moves.
WORKING_TIMEZONE = os.getenv("TIMEZONE", "America/New_York")


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def applied_stamp() -> str:
    """Today's date and time where the team actually works.

    ZoneInfo needs the tzdata package on Windows, and a machine without it
    should not take the app down over a cosmetic timestamp — hence the fallback.
    """
    try:
        from zoneinfo import ZoneInfo
        now = dt.datetime.now(ZoneInfo(WORKING_TIMEZONE))
    except Exception:
        now = dt.datetime.now()
    return now.strftime("%Y-%m-%d %H:%M")


class User(Base):
    """A person who signs in. Managers run cycles; BDs work profiles."""
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(120), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(16), nullable=False, default="bd")  # admin | bd
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=utcnow)


class Profile(Base):
    """The identity a job is applied under.

    `name` is what the client sees — "Khuram". `headline` is the resume behind
    it — "AI Engineer". Two profiles with the same headline are exactly the
    case this system is built for: same skills, different candidates, both
    free to approach the same job.
    """
    __tablename__ = "profiles"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), unique=True, nullable=False, index=True)
    headline = Column(String(160), nullable=False, default="")
    platform = Column(String(120), nullable=False, default="")
    user_id = Column(Integer, ForeignKey("users.id"), index=True)  # who runs it
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=utcnow)


class Batch(Base):
    """One dispatch cycle. Sheets go in, lists come out."""
    __tablename__ = "batches"
    id = Column(Integer, primary_key=True)
    name = Column(String(160), nullable=False)
    status = Column(String(16), nullable=False, default="open")  # open | computed
    mode = Column(String(16), nullable=False, default=COVER)      # cover | split
    quota = Column(Integer, nullable=False, default=40)
    one_per_client = Column(Boolean, nullable=False, default=False)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=utcnow)
    computed_at = Column(DateTime, nullable=True)
    report = Column(JSON, default=dict)


class Upload(Base):
    """A raw sheet, handed in for one profile.

    Rows are kept verbatim so the column mapping stays editable right up until
    the cycle is computed.
    """
    __tablename__ = "uploads"
    id = Column(Integer, primary_key=True)
    batch_id = Column(Integer, ForeignKey("batches.id", ondelete="CASCADE"), index=True)
    profile_id = Column(Integer, ForeignKey("profiles.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)  # who uploaded
    filename = Column(String(255))
    row_count = Column(Integer, default=0)
    headers = Column(JSON, default=list)
    mapping = Column(JSON, default=dict)
    rows = Column(JSON, default=list)
    created_at = Column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("batch_id", "profile_id", name="uq_sheet_per_profile"),)


class Job(Base):
    """A posting, identified by fingerprint. Global, not per-cycle, so history
    carries across cycles."""
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True)
    fingerprint = Column(String(400), unique=True, nullable=False, index=True)
    tier = Column(String(8))
    title = Column(String(500))
    company = Column(String(300))
    company_key = Column(String(300), index=True)
    platform = Column(String(120))
    url = Column(Text)
    first_seen = Column(DateTime, default=utcnow)


class Application(Base):
    """All-time history: this profile has approached this job. Never re-issued."""
    __tablename__ = "applications"
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    profile_id = Column(Integer, ForeignKey("profiles.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=True)
    applied_on = Column(String(40))
    created_at = Column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("job_id", "profile_id", name="uq_application"),)


class BatchApplication(Base):
    """Who applied to what, *in this cycle*.

    `applications` is all-time and unique per (job, profile), so it cannot say
    who collided in cycle 12 once cycle 13 exists — the row belongs to whichever
    cycle saw it first. This keeps the per-cycle picture the report needs.
    """
    __tablename__ = "batch_applications"
    id = Column(Integer, primary_key=True)
    batch_id = Column(Integer, ForeignKey("batches.id", ondelete="CASCADE"), index=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    profile_id = Column(Integer, ForeignKey("profiles.id"), index=True)
    __table_args__ = (UniqueConstraint("batch_id", "job_id", "profile_id",
                                       name="uq_batch_application"),)


class Assignment(Base):
    """A job placed on one profile's list for one cycle.

    `exclusive` mirrors the cycle's mode onto the row so the partial unique
    index below can hold the split-mode guarantee at the database level, while
    leaving coverage cycles free to hand one job to every eligible profile.
    """
    __tablename__ = "assignments"
    id = Column(Integer, primary_key=True)
    batch_id = Column(Integer, ForeignKey("batches.id", ondelete="CASCADE"), index=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    profile_id = Column(Integer, ForeignKey("profiles.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    status = Column(String(16), default="pending")  # pending | applied | skipped
    exclusive = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=utcnow)
    __table_args__ = (
        UniqueConstraint("batch_id", "job_id", "profile_id", name="uq_job_per_profile"),
        Index("uq_job_dispatched_once", "batch_id", "job_id",
              unique=True,
              sqlite_where=Column("exclusive") == True,          # noqa: E712
              postgresql_where=Column("exclusive") == True),     # noqa: E712
    )
