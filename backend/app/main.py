"""Dispatch API.

Run locally:  uvicorn app.main:app --reload --port 8000
Interactive docs: http://localhost:8000/docs

The unit of work is a profile, not a person — see models.py.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import os
import re
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Iterable, Optional

import bcrypt
import jwt
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr
from sqlalchemy import create_engine, delete, func, insert, or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from . import dashboard, exports, ingest, interviews, matching
from .models import (AVAILABILITY, COVER, INTERVIEW_MODES, INTERVIEW_OUTCOMES,
                     INTERVIEW_STATUSES, MODES, ROLES, SPLIT, Application,
                     Assignment, Base, Batch, BatchApplication, Interview, Job,
                     Profile, Setting, Upload, User, applied_stamp,
                     from_working, utcnow, working_label)
from .schema import bring_up_to_date

def _database_url() -> str:
    """Hosted Postgres add-ons hand out `postgres://…`, which SQLAlchemy 2 no
    longer recognises, and none of them say so. Normalise it here so pasting the
    connection string straight from Render, Neon or Heroku just works."""
    url = os.getenv("DATABASE_URL", "sqlite:///./dispatch.db").strip()
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg2://" + url[len(prefix):]
    return url


DATABASE_URL = _database_url()
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-before-you-deploy-this")
JWT_HOURS = int(os.getenv("JWT_HOURS", "12"))
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

# Set when one process serves the built browser app as well as the API, which
# is how this deploys: one container, one URL, no proxy to wire up.
WEB_ROOT = os.getenv("WEB_ROOT", "")

MAX_UPLOAD_BYTES = 15 * 1024 * 1024

# SQLite caps the number of bound parameters in one statement, so every IN (…)
# built from user data is fed through in slices.
_PARAM_CHUNK = 500


def _chunks(items: Iterable, size: int = _PARAM_CHUNK):
    items = list(items)
    for start in range(0, len(items), size):
        yield items[start:start + size]


connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base.metadata.create_all(engine)
bring_up_to_date(engine)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Keep the lists current without anyone pressing anything."""
    ticker = asyncio.create_task(_auto_build_loop()) if AUTO_BUILD_TICK_SECONDS > 0 else None
    try:
        yield
    finally:
        if ticker:
            ticker.cancel()
            try:
                await ticker
            except asyncio.CancelledError:
                pass


app = FastAPI(title="Dispatch", version="2.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in CORS_ORIGINS if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
bearer = HTTPBearer(auto_error=False)


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #

def hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode(), hashed.encode())
    except ValueError:
        return False


def make_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=JWT_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(401, "Sign in to continue.")
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Your session expired. Sign in again.")
    except jwt.PyJWTError:
        raise HTTPException(401, "That session is not valid.")
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(401, "This account is no longer active.")
    return user


def admin_only(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Only a manager can do that.")
    return user


def can_see_dashboard(user: User) -> bool:
    """Whether this person may look at their own figures.

    A manager always may — both their own and anybody else's. For everyone
    else it is off until a manager opens it, which is the whole point: being
    measured on a screen should be a decision somebody made, not a side effect
    of having an account.
    """
    return user.role == "admin" or user.dashboard_visible is True


def require_dashboard(user: User) -> None:
    if not can_see_dashboard(user):
        raise HTTPException(403, "Your manager has not opened your dashboard yet.")


def owned_profile(profile_id: int, db: Session, user: User) -> Profile:
    """The profile, if this person is allowed to act *as* it.

    Working the list, handing in a sheet, marking a job applied — everything
    that speaks to a client in the profile's name. That is the BD who runs the
    account, and nobody else. The developer behind the profile is deliberately
    not included: they are the person the client will meet, not the person
    applying, and letting them mark jobs applied would put work in a colleague's
    record that colleague did not do.
    """
    profile = db.get(Profile, profile_id)
    if profile is None or not profile.is_active:
        raise HTTPException(404, "No such profile.")
    if user.role != "admin" and profile.user_id != user.id:
        raise HTTPException(403, "That profile belongs to someone else.")
    return profile


def linked_profile(profile_id: int, db: Session, user: User) -> Profile:
    """The profile, if this person has any business with it at all.

    A wider door than owned_profile, for the things both sides of a profile
    share — the interview, the resume, the record of how it is doing. Three
    ways to be through it: you manage the workspace, you run the account the
    applications go out from, or you are the developer the client will be
    talking to.
    """
    profile = db.get(Profile, profile_id)
    if profile is None or not profile.is_active:
        raise HTTPException(404, "No such profile.")
    if user.role == "admin" or profile.user_id == user.id:
        return profile
    if profile.dev_user_id is not None and profile.dev_user_id == user.id:
        return profile
    raise HTTPException(403, "That profile belongs to someone else.")


def visible_profile_ids(db: Session, user: User) -> Optional[list[int]]:
    """Whose interviews this person may see. None means every one of them,
    which is only ever a manager.

    A BD sees the profiles they run; a developer sees the ones they are sold
    under. An empty list is a real answer — somebody with no profile attached
    sees nothing, not everything.
    """
    if user.role == "admin":
        return None
    column = Profile.dev_user_id if user.role == "dev" else Profile.user_id
    return [row for (row,) in db.execute(
        select(Profile.id).where(Profile.is_active == True,  # noqa: E712
                                 column == user.id)).all()]


# Fields on a profile that describe the developer rather than the identity.
# The developer keeps these current themselves; everything else about a profile
# — its name, who runs it, whether it is on the team board — is the manager's.
DEV_EDITABLE = ("email", "resume_url", "skills", "timezone", "rate",
                "availability", "bio")


def _check_availability(value: str) -> str:
    cleaned = (value or "open").strip().lower()
    if cleaned not in AVAILABILITY:
        raise HTTPException(400, f"Availability must be one of {', '.join(AVAILABILITY)}.")
    return cleaned


def _check_email(value: str) -> str:
    cleaned = (value or "").strip()
    if cleaned and "@" not in cleaned:
        raise HTTPException(400, "That does not look like an email address.")
    return cleaned[:255]


def _check_link(value: str, what: str) -> str:
    """A link typed by a person, on its way into somebody else's href.

    Stricter than the sheet reader, which tolerates a bare hostname because
    spreadsheets are full of them. This one is typed into a form by somebody
    who can be told to fix it, and a relative link on a colleague's screen goes
    nowhere useful.
    """
    cleaned = (value or "").strip()
    if not cleaned:
        return ""
    if not re.match(r"^https?://", cleaned, re.I):
        raise HTTPException(400, f"The {what} needs to start with http:// or https://.")
    return cleaned[:2000]


# --------------------------------------------------------------------------- #
# Request and response shapes
# --------------------------------------------------------------------------- #

class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserIn(BaseModel):
    email: EmailStr
    name: str
    password: str
    role: str = "bd"
    dashboard_visible: bool = False


class UserPatch(BaseModel):
    dashboard_visible: Optional[bool] = None


class ProfileIn(BaseModel):
    name: str
    headline: str = ""
    platform: str = ""
    user_id: Optional[int] = None
    share_progress: bool = True
    # The developer behind the identity. All optional: a profile can be created
    # before anybody is attached to it, and filled in later by whoever it is.
    dev_user_id: Optional[int] = None
    email: str = ""
    resume_url: str = ""
    skills: str = ""
    timezone: str = ""
    rate: str = ""
    availability: str = "open"
    bio: str = ""


class ProfilePatch(BaseModel):
    name: Optional[str] = None
    headline: Optional[str] = None
    platform: Optional[str] = None
    user_id: Optional[int] = None
    share_progress: Optional[bool] = None
    dev_user_id: Optional[int] = None
    email: Optional[str] = None
    resume_url: Optional[str] = None
    skills: Optional[str] = None
    timezone: Optional[str] = None
    rate: Optional[str] = None
    availability: Optional[str] = None
    bio: Optional[str] = None


class InterviewIn(BaseModel):
    profile_id: int
    # "2026-08-24T14:30", read as the clock the team works to. See
    # models.from_working — the browser never decides what that means.
    scheduled_at: str
    client: str = ""
    role: str = ""
    mode: str = "video"
    duration_minutes: int = 30
    link: str = ""
    notes: str = ""
    job_id: Optional[int] = None


class InterviewPatch(BaseModel):
    scheduled_at: Optional[str] = None
    client: Optional[str] = None
    role: Optional[str] = None
    mode: Optional[str] = None
    duration_minutes: Optional[int] = None
    link: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    outcome: Optional[str] = None


class SettingsIn(BaseModel):
    team_board_visible: Optional[bool] = None


class BatchIn(BaseModel):
    name: str
    quota: int = 40
    mode: str = COVER
    one_per_client: bool = False
    auto_build_minutes: int = 10


class MappingIn(BaseModel):
    mapping: dict


class EntryIn(BaseModel):
    url: str = ""
    title: str = ""
    company: str = ""
    platform: str = ""
    date: str = ""


class EntriesIn(BaseModel):
    rows: list[EntryIn]


class StatusIn(BaseModel):
    status: str


def user_json(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role,
            "is_active": u.is_active,
            # A manager's dashboard is never gated, so it reads True for them
            # whatever the column says.
            "dashboard_visible": can_see_dashboard(u)}


def profile_json(p: Profile, owner: Optional[User] = None,
                 developer: Optional[User] = None) -> dict:
    return {"id": p.id, "name": p.name, "headline": p.headline,
            "platform": p.platform, "user_id": p.user_id,
            "owner": owner.name if owner else None, "is_active": p.is_active,
            # A NULL predates the column and the default is to share, so only an
            # explicit False takes a profile off the board.
            "share_progress": p.share_progress is not False,
            # The developer, and what a client is handed when this identity
            # applies. Every one of these may be empty — a profile nobody has
            # filled in behaves exactly as it did before they existed, and the
            # screens show nothing rather than something wrong.
            "dev_user_id": p.dev_user_id,
            "developer": developer.name if developer else None,
            "developer_email": developer.email if developer else None,
            "email": p.email or "",
            "resume_url": p.resume_url or "",
            "skills": p.skills or "",
            "timezone": p.timezone or "",
            "rate": p.rate or "",
            "availability": p.availability or "open",
            "bio": p.bio or "",
            "label": p.name if not p.headline else f"{p.name} · {p.headline}"}


def batch_json(b: Batch) -> dict:
    return {"id": b.id, "name": b.name, "status": b.status, "quota": b.quota,
            "mode": b.mode, "one_per_client": b.one_per_client,
            "auto_build_minutes": b.auto_build_minutes or 0,
            "created_at": b.created_at.isoformat() if b.created_at else None,
            "computed_at": b.computed_at.isoformat() if b.computed_at else None,
            "last_built_at": b.last_built_at.isoformat() if b.last_built_at else None,
            "report": b.report or {}}


# --------------------------------------------------------------------------- #
# Auth routes
# --------------------------------------------------------------------------- #

@app.post("/api/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "That email and password do not match.")
    if not user.is_active:
        raise HTTPException(403, "This account has been switched off.")
    return {"token": make_token(user), "user": user_json(user)}


@app.get("/api/auth/me")
def me(user: User = Depends(current_user)):
    return user_json(user)


# --------------------------------------------------------------------------- #
# People (manager)
# --------------------------------------------------------------------------- #

@app.get("/api/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    return [user_json(u) for u in db.scalars(select(User).order_by(User.name)).all()]


@app.post("/api/users", status_code=201)
def create_user(body: UserIn, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(409, "Someone already uses that email.")
    if body.role not in ROLES:
        raise HTTPException(400, f"Role must be one of {', '.join(ROLES)}.")
    if len(body.password) < 8:
        raise HTTPException(400, "Use a password of at least 8 characters.")
    user = User(email=body.email.lower(), name=body.name.strip(),
                password_hash=hash_password(body.password), role=body.role,
                dashboard_visible=body.dashboard_visible)
    db.add(user)
    db.commit()
    return user_json(user)


@app.patch("/api/users/{user_id}")
def update_user(user_id: int, body: UserPatch, db: Session = Depends(get_db),
                _: User = Depends(admin_only)):
    """Open or close one person's dashboard."""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "No such person.")
    if body.dashboard_visible is not None:
        user.dashboard_visible = body.dashboard_visible
    db.commit()
    return user_json(user)


@app.delete("/api/users/{user_id}")
def deactivate_user(user_id: int, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    if user_id == admin.id:
        raise HTTPException(400, "You cannot switch off your own account.")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "No such person.")
    user.is_active = False
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Profiles — the identities jobs are applied under
# --------------------------------------------------------------------------- #

@app.get("/api/profiles")
def list_profiles(mine: bool = False, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    """Managers see every profile. A BD sees the ones they run, a developer the
    ones they are sold under."""
    query = select(Profile).where(Profile.is_active == True)  # noqa: E712
    if user.role == "dev":
        query = query.where(Profile.dev_user_id == user.id)
    elif mine or user.role != "admin":
        query = query.where(Profile.user_id == user.id)
    owners = {u.id: u for u in db.scalars(select(User)).all()}
    return [profile_json(p, owners.get(p.user_id), owners.get(p.dev_user_id))
            for p in db.scalars(query.order_by(Profile.name)).all()]


@app.get("/api/profiles/{profile_id}")
def get_profile(profile_id: int, db: Session = Depends(get_db),
                user: User = Depends(current_user)):
    """One profile in full — the identity and the developer behind it.

    Readable by both sides of it, because both need it: the BD is about to
    paste that resume link into an application, and the developer wrote it.
    """
    profile = linked_profile(profile_id, db, user)
    return profile_json(profile,
                        db.get(User, profile.user_id) if profile.user_id else None,
                        db.get(User, profile.dev_user_id) if profile.dev_user_id else None)


@app.post("/api/profiles", status_code=201)
def create_profile(body: ProfileIn, db: Session = Depends(get_db),
                   _: User = Depends(admin_only)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Give the profile a name — whatever the client sees.")
    clash = db.scalar(select(Profile).where(func.lower(Profile.name) == name.lower()))
    if clash:
        raise HTTPException(409, f"There is already a profile called {clash.name}. "
                                 "Two profiles with one name would split its history in half.")
    if body.user_id is not None and not db.get(User, body.user_id):
        raise HTTPException(400, "No such person to run it.")
    if body.dev_user_id is not None and not db.get(User, body.dev_user_id):
        raise HTTPException(400, "No such person to be the developer behind it.")
    profile = Profile(name=name, headline=body.headline.strip(),
                      platform=body.platform.strip(), user_id=body.user_id,
                      share_progress=body.share_progress,
                      dev_user_id=body.dev_user_id,
                      email=_check_email(body.email),
                      resume_url=_check_link(body.resume_url, "resume link"),
                      skills=body.skills.strip()[:400],
                      timezone=body.timezone.strip()[:64],
                      rate=body.rate.strip()[:40],
                      availability=_check_availability(body.availability),
                      bio=body.bio.strip())
    db.add(profile)
    db.commit()
    return profile_json(profile,
                        db.get(User, profile.user_id) if profile.user_id else None,
                        db.get(User, profile.dev_user_id) if profile.dev_user_id else None)


@app.patch("/api/profiles/{profile_id}")
def update_profile(profile_id: int, body: ProfilePatch, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    """The manager edits anything. The developer edits their own details.

    Which resume link goes out, which address a client replies to, whether they
    can take work next week — that is the developer's own information, and
    routing every correction through a manager is how it ends up out of date.
    The identity itself — its name, who runs it, whether it is on the team
    board — stays the manager's, because those decide what other people see.
    """
    profile = db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(404, "No such profile.")

    asked = set(body.model_dump(exclude_unset=True))
    if user.role != "admin":
        if profile.dev_user_id is None or profile.dev_user_id != user.id:
            raise HTTPException(403, "Only a manager can change that profile.")
        beyond = sorted(asked - set(DEV_EDITABLE))
        if beyond:
            raise HTTPException(
                403, f"Only a manager can change {', '.join(beyond)}. "
                     "Your own details — email, resume, skills, rate, timezone, "
                     "availability — are yours to keep current.")

    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(400, "A profile needs a name.")
        clash = db.scalar(select(Profile).where(func.lower(Profile.name) == name.lower(),
                                                Profile.id != profile_id))
        if clash:
            raise HTTPException(409, f"There is already a profile called {clash.name}.")
        profile.name = name
    if body.headline is not None:
        profile.headline = body.headline.strip()
    if body.platform is not None:
        profile.platform = body.platform.strip()
    if body.user_id is not None:
        if not db.get(User, body.user_id):
            raise HTTPException(400, "No such person to run it.")
        profile.user_id = body.user_id
    if body.share_progress is not None:
        profile.share_progress = body.share_progress
    if body.dev_user_id is not None:
        if not db.get(User, body.dev_user_id):
            raise HTTPException(400, "No such person to be the developer behind it.")
        profile.dev_user_id = body.dev_user_id
    if body.email is not None:
        profile.email = _check_email(body.email)
    if body.resume_url is not None:
        profile.resume_url = _check_link(body.resume_url, "resume link")
    if body.skills is not None:
        profile.skills = body.skills.strip()[:400]
    if body.timezone is not None:
        profile.timezone = body.timezone.strip()[:64]
    if body.rate is not None:
        profile.rate = body.rate.strip()[:40]
    if body.availability is not None:
        profile.availability = _check_availability(body.availability)
    if body.bio is not None:
        profile.bio = body.bio.strip()
    db.commit()
    return profile_json(profile,
                        db.get(User, profile.user_id) if profile.user_id else None,
                        db.get(User, profile.dev_user_id) if profile.dev_user_id else None)


@app.delete("/api/profiles/{profile_id}")
def retire_profile(profile_id: int, db: Session = Depends(get_db),
                   _: User = Depends(admin_only)):
    profile = db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(404, "No such profile.")
    profile.is_active = False
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Batches
# --------------------------------------------------------------------------- #

@app.get("/api/batches")
def list_batches(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [batch_json(b) for b in db.scalars(select(Batch).order_by(Batch.id.desc())).all()]


@app.post("/api/batches", status_code=201)
def create_batch(body: BatchIn, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    if body.mode not in MODES:
        raise HTTPException(400, f"Mode must be one of {', '.join(MODES)}.")
    batch = Batch(name=body.name.strip() or f"Batch {utcnow():%d %b}",
                  quota=max(1, body.quota), mode=body.mode,
                  one_per_client=body.one_per_client,
                  auto_build_minutes=max(0, body.auto_build_minutes),
                  created_by=admin.id)
    db.add(batch)
    db.commit()
    return batch_json(batch)


@app.get("/api/batches/{batch_id}")
def get_batch(batch_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    batch = db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404, "No such batch.")
    uploads = db.scalars(select(Upload).where(Upload.batch_id == batch_id)).all()
    profiles = {p.id: p for p in db.scalars(select(Profile)).all()}
    owners = {u.id: u.name for u in db.scalars(select(User)).all()}
    return {
        **batch_json(batch),
        "uploads": [
            {"id": u.id, "profile_id": u.profile_id,
             "profile": profiles[u.profile_id].name if u.profile_id in profiles else "?",
             "headline": profiles[u.profile_id].headline if u.profile_id in profiles else "",
             "person": owners.get(u.user_id, "?"),
             "filename": u.filename, "row_count": u.row_count,
             "headers": u.headers, "mapping": u.mapping}
            for u in uploads
        ],
    }


# --------------------------------------------------------------------------- #
# Uploads — one sheet per profile, per cycle
# --------------------------------------------------------------------------- #

@app.post("/api/batches/{batch_id}/uploads", status_code=201)
def upload_sheet(batch_id: int, profile_id: int = Form(...), file: UploadFile = File(...),
                 db: Session = Depends(get_db), user: User = Depends(current_user)):
    batch = db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404, "No such batch.")
    if batch.status != "open":
        raise HTTPException(400, "This batch is already computed. Ask your manager to open a new one.")
    profile = owned_profile(profile_id, db, user)

    too_big = "That file is over 15 MB. Split it or remove extra columns."
    if (file.size or 0) > MAX_UPLOAD_BYTES:      # rejected before it is read
        raise HTTPException(413, too_big)
    raw = file.file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, too_big)
    try:
        frame = ingest.read_table(raw, file.filename or "sheet.csv")
    except Exception as exc:
        raise HTTPException(400, f"Could not read that file: {exc}")

    headers = list(frame.columns)
    rows = frame.to_dict(orient="records")
    mapping = ingest.auto_map(headers)

    # One sheet per profile per batch — a re-upload replaces the old one.
    existing = db.scalar(select(Upload).where(Upload.batch_id == batch_id,
                                              Upload.profile_id == profile.id))
    if existing:
        db.delete(existing)
        db.flush()

    upload = Upload(batch_id=batch_id, profile_id=profile.id, user_id=user.id,
                    filename=file.filename, row_count=len(rows), headers=headers,
                    mapping=mapping, rows=rows)
    db.add(upload)
    db.commit()

    return {"id": upload.id, "profile_id": profile.id, "profile": profile.name,
            "filename": upload.filename, "row_count": upload.row_count,
            "headers": headers, "mapping": mapping,
            "preview": rows[:5], "fields": ingest.FIELDS}


@app.patch("/api/uploads/{upload_id}/mapping")
def set_mapping(upload_id: int, body: MappingIn, db: Session = Depends(get_db),
                user: User = Depends(current_user)):
    upload = db.get(Upload, upload_id)
    if not upload:
        raise HTTPException(404, "No such upload.")
    owned_profile(upload.profile_id, db, user)
    upload.mapping = {k: v for k, v in body.mapping.items()
                      if k in {f["key"] for f in ingest.FIELDS}}
    db.commit()
    return {"ok": True, "mapping": upload.mapping}


# --------------------------------------------------------------------------- #
# Typing jobs in by hand — the same sheet, entered a row at a time
# --------------------------------------------------------------------------- #

# Column names used when a profile's sheet is typed rather than uploaded. The
# mapping is then the identity, so hand-entered and uploaded sheets travel
# through exactly the same code from here on.
TYPED_HEADERS = {"url": "Job link", "title": "Job title", "company": "Client",
                 "platform": "Platform", "date": "Applied on"}


@app.get("/api/batches/{batch_id}/profiles/{profile_id}/entries")
def list_entries(batch_id: int, profile_id: int, db: Session = Depends(get_db),
                 user: User = Depends(current_user)):
    profile = owned_profile(profile_id, db, user)
    upload = db.scalar(select(Upload).where(Upload.batch_id == batch_id,
                                            Upload.profile_id == profile.id))
    if not upload:
        return {"rows": [], "filename": None, "row_count": 0, "typed": True}
    rows = ingest.project_rows(upload.rows or [], upload.mapping or {})
    return {"rows": rows, "filename": upload.filename, "row_count": len(rows),
            "typed": (upload.mapping or {}) == TYPED_HEADERS}


@app.put("/api/batches/{batch_id}/profiles/{profile_id}/entries")
def save_entries(batch_id: int, profile_id: int, body: EntriesIn,
                 db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Replace this profile's sheet with what is on screen.

    Saving rewrites the sheet in canonical columns. For a sheet that arrived as
    a file that means any extra columns are dropped — only these five are ever
    read anyway, and the alternative is an editor that quietly disagrees with
    what is stored.
    """
    batch = db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404, "No such batch.")
    if batch.status != "open":
        raise HTTPException(400, "This cycle is closed. Ask your manager to open a new one.")
    profile = owned_profile(profile_id, db, user)

    if len(body.rows) > ingest.MAX_ROWS:
        raise HTTPException(413, f"That is over {ingest.MAX_ROWS} rows. Upload it as a file instead.")

    kept = []
    for entry in body.rows:
        record = {"url": ingest.safe_url(entry.url), "title": entry.title.strip(),
                  "company": entry.company.strip(), "platform": entry.platform.strip(),
                  "date": entry.date.strip()}
        # Judge on the fields that identify a job. The timestamp is stamped for
        # the user the moment they add a row, so every untouched row carries one
        # — counting it would file a blank row as work.
        if ingest.is_usable(record):
            kept.append({TYPED_HEADERS[key]: value for key, value in record.items()})

    upload = db.scalar(select(Upload).where(Upload.batch_id == batch_id,
                                            Upload.profile_id == profile.id))

    if not kept:
        # Nothing typed is nothing handed in. Without this, opening the entry
        # screen and clicking away would leave an empty sheet behind, which the
        # manager would see as a profile having reported in.
        if upload is not None:
            db.delete(upload)
            db.commit()
        return {"ok": True, "row_count": 0, "usable": 0, "filename": None}

    if upload is None:
        upload = Upload(batch_id=batch_id, profile_id=profile.id, user_id=user.id,
                        filename="Typed in")
        db.add(upload)
    elif upload.mapping != TYPED_HEADERS:
        upload.filename = f"{upload.filename} (edited)" if upload.filename else "Typed in"
    upload.headers = list(TYPED_HEADERS.values())
    upload.mapping = dict(TYPED_HEADERS)
    upload.rows = kept
    upload.row_count = len(kept)
    upload.user_id = user.id
    db.commit()

    usable = sum(1 for row in ingest.apply_mapping(kept, TYPED_HEADERS))
    return {"ok": True, "row_count": len(kept), "usable": usable,
            "filename": upload.filename}


@app.delete("/api/uploads/{upload_id}")
def delete_upload(upload_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    upload = db.get(Upload, upload_id)
    if not upload:
        raise HTTPException(404, "No such upload.")
    owned_profile(upload.profile_id, db, user)
    db.delete(upload)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Compute — the heart of it
# --------------------------------------------------------------------------- #

@app.post("/api/batches/{batch_id}/compute")
def compute(batch_id: int, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    """Build the lists now. The timer calls build_lists directly."""
    batch = db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404, "No such batch.")
    return build_lists(db, batch)


def build_lists(db: Session, batch: Batch) -> dict:
    batch_id = batch.id
    uploads = db.scalars(select(Upload).where(Upload.batch_id == batch_id)).all()
    if len(uploads) < 2:
        raise HTTPException(400, "At least two sheets are needed before anything can be compared.")

    # 1. Flatten every sheet into canonical records tagged with the profile it
    #    was handed in for.
    records = []
    for upload in uploads:
        for row in ingest.apply_mapping(upload.rows or [], upload.mapping or {}):
            fp, tier = matching.fingerprint(row["url"], row["title"], row["company"])
            if not fp:
                continue
            records.append({**row, "fp": fp, "tier": tier, "profile_id": upload.profile_id})

    if not records:
        raise HTTPException(400, "No usable rows. Check that a job link, or a title and client, is mapped.")

    # 2. Collapse near-duplicate L3 fingerprints.
    remap = matching.fuzzy_merge(records)
    for record in records:
        if record["fp"] in remap:
            record["fp"] = remap[record["fp"]]
            record["tier"] = "L3f"

    # 3. Upsert jobs, then record applications. Every lookup here is done in
    #    bulk: one query per few hundred fingerprints rather than one query per
    #    row, which is the difference between a snappy Compute and a minute of
    #    staring at a spinner on a real team's sheets.
    known: dict[str, Job] = {}
    for chunk in _chunks({record["fp"] for record in records}):
        for job in db.scalars(select(Job).where(Job.fingerprint.in_(chunk))):
            known[job.fingerprint] = job

    seen: dict[str, Job] = {}
    fresh: list[Job] = []
    for record in records:
        fp = record["fp"]
        if fp in seen:
            continue
        job = known.get(fp)
        if job is None:
            job = Job(fingerprint=fp, tier=record["tier"], title=record["title"][:500],
                      company=record["company"][:300],
                      company_key=matching.normalize_text(record["company"])[:300],
                      platform=record["platform"][:120], url=record["url"])
            fresh.append(job)
        else:
            job.title = job.title or record["title"][:500]
            job.company = job.company or record["company"][:300]
            job.url = job.url or record["url"]
        seen[fp] = job
    if fresh:
        db.add_all(fresh)
        db.flush()

    applied_by: dict[int, set[int]] = {}
    applied_on: dict[tuple[int, int], str] = {}
    for record in records:
        job = seen[record["fp"]]
        applied_by.setdefault(job.id, set()).add(record["profile_id"])
        stamp = (record.get("date") or "").strip()
        if stamp:
            applied_on.setdefault((job.id, record["profile_id"]), stamp[:40])

    owner_of = {p.id: p.user_id for p in db.scalars(select(Profile)).all()}

    have: set[tuple[int, int]] = set()
    for chunk in _chunks(applied_by):
        have.update(map(tuple, db.execute(
            select(Application.job_id, Application.profile_id)
            .where(Application.job_id.in_(chunk))).all()))
    new_applications = [
        {"job_id": job_id, "profile_id": pid, "user_id": owner_of.get(pid),
         "batch_id": batch_id, "applied_on": applied_on.get((job_id, pid))}
        for job_id, pids in applied_by.items() for pid in pids
        if (job_id, pid) not in have
    ]
    if new_applications:
        db.execute(insert(Application), new_applications)

    # The per-cycle record. `applications` is all-time and unique per
    # (job, profile), so it cannot say who collided *in this cycle* once a later
    # cycle exists — that is what the manager's report needs.
    db.execute(delete(BatchApplication).where(BatchApplication.batch_id == batch_id))
    this_cycle = [{"batch_id": batch_id, "job_id": job_id, "profile_id": pid}
                  for job_id, pids in applied_by.items() for pid in pids]
    if this_cycle:
        db.execute(insert(BatchApplication), this_cycle)
    db.flush()

    participants = sorted({u.profile_id for u in uploads if u.profile_id})

    # 4. Anything still sitting unworked on a participant's list from an earlier
    #    cycle comes back into the pool. A job someone simply ran out of time
    #    for should not fall through the cracks because a new cycle opened.
    carried = db.execute(
        select(Assignment.job_id, Assignment.profile_id)
        .where(Assignment.batch_id != batch_id,
               Assignment.status == "pending",
               Assignment.profile_id.in_(participants))
    ).all() if participants else []

    pool_ids = {job.id for job in seen.values()} | {job_id for job_id, _ in carried}

    # 5. What each profile may NOT be given: anything it has already applied to
    #    (all-time), and anything it looked at and skipped. Note this is per
    #    profile, not per person — Khuram having applied says nothing about
    #    whether Zahid should.
    blocked: dict[int, set[int]] = defaultdict(set)
    for chunk in _chunks(pool_ids):
        for job_id, pid in db.execute(
            select(Application.job_id, Application.profile_id)
            .where(Application.job_id.in_(chunk))
        ).all():
            blocked[job_id].add(pid)
        for job_id, pid in db.execute(
            select(Assignment.job_id, Assignment.profile_id)
            .where(Assignment.job_id.in_(chunk), Assignment.status == "skipped")
        ).all():
            blocked[job_id].add(pid)

    job_rows: dict[int, Job] = {job.id: job for job in seen.values()}
    missing = pool_ids - set(job_rows)
    for chunk in _chunks(missing):
        for job in db.scalars(select(Job).where(Job.id.in_(chunk))):
            job_rows[job.id] = job

    pool = [
        {"job_id": job_id, "company_key": job_rows[job_id].company_key or "",
         "blocked_for": blocked.get(job_id, set())}
        for job_id in sorted(pool_ids) if job_id in job_rows
    ]

    place = matching.cover if batch.mode == COVER else matching.partition
    assigned, stats = place(pool, participants, batch.quota, batch.one_per_client)

    # Only the untouched rows are replaced. A job somebody has already marked
    # applied or skipped is their record of this cycle's work, and rebuilding —
    # which now happens on a timer, not just when a manager asks — must not make
    # it vanish from under them.
    worked = {(a.profile_id, a.job_id) for a in db.scalars(
        select(Assignment).where(Assignment.batch_id == batch_id,
                                 Assignment.status != "pending"))}
    db.execute(delete(Assignment).where(Assignment.batch_id == batch_id,
                                        Assignment.status == "pending"))
    db.flush()
    dispatch = [{"batch_id": batch_id, "job_id": job_id, "profile_id": pid,
                 "user_id": owner_of.get(pid), "status": "pending",
                 "exclusive": batch.mode == SPLIT}
                for pid, job_ids in assigned.items() for job_id in job_ids
                if (pid, job_id) not in worked]
    if dispatch:
        db.execute(insert(Assignment), dispatch)

    # A job that has moved onto this cycle's list should not still be sitting
    # open on an earlier one, or the same work shows up once per cycle forever.
    # Anything NOT re-dispatched keeps its old row, so it stays in the running.
    placed = {(profile_id, job_id)
              for profile_id, job_ids in assigned.items() for job_id in job_ids}
    if placed:
        stale = [row_id for row_id, profile_id, job_id in db.execute(
            select(Assignment.id, Assignment.profile_id, Assignment.job_id)
            .where(Assignment.batch_id != batch_id,
                   Assignment.status == "pending",
                   Assignment.profile_id.in_(participants))).all()
            if (profile_id, job_id) in placed]
        for chunk in _chunks(stale):
            db.execute(delete(Assignment).where(Assignment.id.in_(chunk)))

    # 6. Report for the manager.
    profiles = {p.id: p for p in db.scalars(select(Profile)).all()}
    owners = {u.id: u.name for u in db.scalars(select(User)).all()}
    matrix = matching.overlap_matrix(
        [{"applied_by": v} for v in applied_by.values()], participants)
    collisions = sum(1 for v in applied_by.values() if len(v) > 1)
    wasted = sum(len(v) - 1 for v in applied_by.values() if len(v) > 1)
    reached = len({job_id for job_ids in assigned.values() for job_id in job_ids})

    batch.report = {
        "Rows read": len(records),
        "Unique jobs": len(seen),
        "Jobs carried over unworked": len(pool_ids) - len(seen),
        "Jobs two profiles both applied to": collisions,
        "Duplicate applications": wasted,
        "Jobs nobody could take": stats["saturated"],
        "Jobs held back by the client rule": stats["held_back_client"],
        "Jobs held back by the quota": stats["held_back_quota"],
        "Jobs put on a list": reached,
        "Places on lists": stats["placements"],
    }
    # Building no longer closes the cycle. People keep logging jobs into an open
    # cycle and the timer keeps the lists current; closing it is a separate act.
    batch.last_built_at = utcnow()
    batch.computed_at = batch.last_built_at
    db.commit()

    counts = dict(db.execute(
        select(Assignment.profile_id, func.count(Assignment.id))
        .where(Assignment.batch_id == batch_id)
        .group_by(Assignment.profile_id)).all())

    return {
        **batch_json(batch),
        "participants": _participant_json(participants, profiles, owners, counts=counts),
        "matrix": {"names": [profiles[p].name if p in profiles else "?" for p in participants],
                   "rows": [[matrix[a][b] for b in participants] for a in participants]},
    }


def _participant_json(participants, profiles, owners, assigned=None, counts=None) -> list[dict]:
    out = []
    for pid in participants:
        profile = profiles.get(pid)
        out.append({
            "id": pid,
            "name": profile.name if profile else "?",
            "headline": profile.headline if profile else "",
            "person": owners.get(profile.user_id) if profile else None,
            "assigned": len(assigned[pid]) if assigned is not None else counts.get(pid, 0),
        })
    return out


@app.post("/api/batches/{batch_id}/close")
def close_batch(batch_id: int, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    """Stop the rebuilds and stop accepting sheets. Lists stay readable."""
    batch = db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404, "No such batch.")
    batch.status = "computed"
    db.commit()
    return batch_json(batch)


@app.post("/api/batches/{batch_id}/reopen")
def reopen_batch(batch_id: int, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    batch = db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404, "No such batch.")
    batch.status = "open"
    db.commit()
    return batch_json(batch)


# --------------------------------------------------------------------------- #
# Rebuilding on a timer
# --------------------------------------------------------------------------- #

AUTO_BUILD_TICK_SECONDS = int(os.getenv("AUTO_BUILD_TICK_SECONDS", "60"))
# If a build dies mid-flight the claim would block every later one, so a claim
# older than this is treated as abandoned.
BUILD_CLAIM_TIMEOUT = dt.timedelta(minutes=15)


def _naive_utc(value: Optional[dt.datetime]) -> Optional[dt.datetime]:
    """SQLite hands back naive datetimes and utcnow() is aware; comparing the
    two raises. Everything stored is UTC, so drop the marker and compare."""
    if value is None:
        return None
    return value.replace(tzinfo=None) if value.tzinfo else value


def _due_for_build(batch: Batch, now: dt.datetime) -> bool:
    if batch.status != "open" or not batch.auto_build_minutes:
        return False
    last = _naive_utc(batch.last_built_at)
    if last is None:
        return True
    return now - last >= dt.timedelta(minutes=batch.auto_build_minutes)


def run_due_builds() -> list[int]:
    """Rebuild every open cycle whose timer has come round. Returns what it built."""
    built: list[int] = []
    db = SessionLocal()
    try:
        now = _naive_utc(utcnow())
        open_cycles = db.scalars(select(Batch).where(Batch.status == "open")).all()
        for batch in open_cycles:
            if not _due_for_build(batch, now):
                continue

            # Claim it with a conditional update: whoever's UPDATE matches a row
            # owns the build. Two workers, or the timer and a manager pressing
            # the button, cannot both be inside build_lists for one cycle.
            claimed = db.execute(
                update(Batch)
                .where(Batch.id == batch.id,
                       or_(Batch.building_since.is_(None),
                           Batch.building_since < now - BUILD_CLAIM_TIMEOUT))
                .values(building_since=now))
            db.commit()
            if claimed.rowcount != 1:
                continue

            try:
                build_lists(db, batch)
                built.append(batch.id)
            except HTTPException:
                pass                    # fewer than two sheets yet; try again next tick
            except Exception as exc:    # noqa: BLE001 — one bad cycle must not stop the rest
                db.rollback()
                print(f"auto-build failed for cycle {batch.id}: {exc}")
            finally:
                db.execute(update(Batch).where(Batch.id == batch.id)
                           .values(building_since=None))
                db.commit()
    finally:
        db.close()
    return built


async def _auto_build_loop() -> None:
    while True:
        await asyncio.sleep(AUTO_BUILD_TICK_SECONDS)
        try:
            await asyncio.to_thread(run_due_builds)
        except asyncio.CancelledError:
            raise
        except Exception as exc:        # noqa: BLE001
            print("auto-build tick failed:", exc)


@app.get("/api/batches/{batch_id}/report")
def report(batch_id: int, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    batch = db.get(Batch, batch_id)
    if not batch or not batch.last_built_at:
        raise HTTPException(404, "That batch has not been built yet.")

    profiles = {p.id: p for p in db.scalars(select(Profile)).all()}
    owners = {u.id: u.name for u in db.scalars(select(User)).all()}
    participants = sorted({u.profile_id for u in
                           db.scalars(select(Upload).where(Upload.batch_id == batch_id)).all()
                           if u.profile_id})

    # Only what was handed in for THIS cycle.
    rows = db.execute(
        select(BatchApplication.job_id, BatchApplication.profile_id)
        .where(BatchApplication.batch_id == batch_id)
    ).all()
    applied_by: dict[int, set[int]] = {}
    for job_id, profile_id in rows:
        applied_by.setdefault(job_id, set()).add(profile_id)

    matrix = matching.overlap_matrix(
        [{"applied_by": v} for v in applied_by.values()], participants)

    counts = dict(db.execute(
        select(Assignment.profile_id, func.count(Assignment.id))
        .where(Assignment.batch_id == batch_id)
        .group_by(Assignment.profile_id)
    ).all())

    hit_twice = [job_id for job_id, pids in applied_by.items() if len(pids) > 1]
    jobs: dict[int, Job] = {}
    for chunk in _chunks(hit_twice):
        for job in db.scalars(select(Job).where(Job.id.in_(chunk))):
            jobs[job.id] = job
    collisions = [
        {"title": jobs[job_id].title, "company": jobs[job_id].company,
         "platform": jobs[job_id].platform, "url": jobs[job_id].url,
         "applied_by": [profiles[p].name if p in profiles else "?"
                        for p in applied_by[job_id]]}
        for job_id in hit_twice if job_id in jobs
    ]

    return {
        **batch_json(batch),
        "participants": _participant_json(participants, profiles, owners, counts=counts),
        "matrix": {"names": [profiles[p].name if p in profiles else "?" for p in participants],
                   "rows": [[matrix[a][b] for b in participants] for a in participants]},
        "collisions": sorted(collisions, key=lambda c: -len(c["applied_by"]))[:400],
    }


# --------------------------------------------------------------------------- #
# Assignments
# --------------------------------------------------------------------------- #

def _row_json(a: Assignment, j: Job) -> dict:
    return {"id": a.id, "status": a.status, "title": j.title, "company": j.company,
            "platform": j.platform, "url": j.url}


def _assignment_rows(db: Session, batch_id: int, profile_id: int) -> list[dict]:
    rows = db.execute(
        select(Assignment, Job).join(Job, Job.id == Assignment.job_id)
        .where(Assignment.batch_id == batch_id, Assignment.profile_id == profile_id)
        .order_by(Job.company, Job.title)
    ).all()
    return [_row_json(a, j) for a, j in rows]


def _all_assignment_rows(db: Session, batch_id: int) -> dict[int, list[dict]]:
    """Every profile's sheet in one pass, for the whole-batch workbook."""
    rows = db.execute(
        select(Assignment, Job).join(Job, Job.id == Assignment.job_id)
        .where(Assignment.batch_id == batch_id)
        .order_by(Job.company, Job.title)
    ).all()
    grouped: dict[int, list[dict]] = defaultdict(list)
    for a, j in rows:
        grouped[a.profile_id].append(_row_json(a, j))
    return grouped


@app.get("/api/batches/{batch_id}/my-sheets")
def my_sheets(batch_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Every profile this person runs, each with its own list."""
    query = select(Profile).where(Profile.is_active == True)  # noqa: E712
    if user.role != "admin":
        query = query.where(Profile.user_id == user.id)
    mine = db.scalars(query.order_by(Profile.name)).all()
    people = {u.id: u for u in db.scalars(select(User)).all()}
    return {"batch_id": batch_id,
            "profiles": [{**profile_json(p, people.get(p.user_id),
                                         people.get(p.dev_user_id)),
                          "jobs": _assignment_rows(db, batch_id, p.id)} for p in mine]}


@app.get("/api/batches/{batch_id}/profiles/{profile_id}/sheet")
def profile_sheet(batch_id: int, profile_id: int, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    profile = owned_profile(profile_id, db, user)
    return {"batch_id": batch_id, "profile": profile_json(profile),
            "jobs": _assignment_rows(db, batch_id, profile.id)}


@app.patch("/api/assignments/{assignment_id}")
def set_status(assignment_id: int, body: StatusIn, db: Session = Depends(get_db),
               user: User = Depends(current_user)):
    row = db.get(Assignment, assignment_id)
    if not row:
        raise HTTPException(404, "No such job on your sheet.")
    owned_profile(row.profile_id, db, user)
    if body.status not in ("pending", "applied", "skipped"):
        raise HTTPException(400, "Status must be pending, applied or skipped.")
    row.status = body.status

    # Marking it applied closes the loop: it counts as this profile's history
    # from now on, so no later cycle offers it again.
    if body.status == "applied":
        exists = db.scalar(select(Application).where(Application.job_id == row.job_id,
                                                     Application.profile_id == row.profile_id))
        if not exists:
            db.add(Application(job_id=row.job_id, profile_id=row.profile_id,
                               user_id=row.user_id, batch_id=row.batch_id,
                               applied_on=applied_stamp()))
    db.commit()
    return {"ok": True, "status": row.status}


# --------------------------------------------------------------------------- #
# Workspace switches
# --------------------------------------------------------------------------- #

# Every switch and its value on a workspace that has never touched the screen.
# Reading falls back to these, so a missing row is the default rather than an
# error, and adding a switch never needs a migration.
SETTING_DEFAULTS = {"team_board_visible": False}


def read_settings(db: Session) -> dict:
    stored = {row.key: row.value for row in db.scalars(select(Setting))}
    return {key: stored.get(key, fallback) for key, fallback in SETTING_DEFAULTS.items()}


@app.get("/api/settings")
def get_settings(db: Session = Depends(get_db), _: User = Depends(current_user)):
    """Readable by everyone: a BD's app needs to know whether to offer the
    team board at all, and hiding the switch from them would not hide the tab."""
    return read_settings(db)


@app.patch("/api/settings")
def update_settings(body: SettingsIn, db: Session = Depends(get_db),
                    _: User = Depends(admin_only)):
    for key, value in body.model_dump(exclude_none=True).items():
        if key not in SETTING_DEFAULTS:
            continue
        row = db.get(Setting, key)
        if row is None:
            db.add(Setting(key=key, value=value))
        else:
            row.value = value
    db.commit()
    return read_settings(db)


# --------------------------------------------------------------------------- #
# Dashboards
# --------------------------------------------------------------------------- #

def _person_dashboard(db: Session, person: User, batch_id: Optional[int]) -> dict:
    board_open = read_settings(db)["team_board_visible"] or person.role == "admin"
    return {**dashboard.for_person(db, person, dashboard.pick_batch(db, batch_id),
                                   team_visible=board_open),
            "person": user_json(person)}


@app.get("/api/dashboard/me")
def dashboard_me(batch_id: Optional[int] = None, db: Session = Depends(get_db),
                 user: User = Depends(current_user)):
    """Your own progress — but only once a manager has opened it for you.

    Checked here rather than only in the browser, because hiding a tab is not
    the same as refusing a request.
    """
    require_dashboard(user)
    return _person_dashboard(db, user, batch_id)


@app.get("/api/dashboard/people/{user_id}")
def dashboard_person(user_id: int, batch_id: Optional[int] = None,
                     db: Session = Depends(get_db), _: User = Depends(admin_only)):
    """One person's dashboard, exactly as they would see it.

    The same payload /dashboard/me returns for them, so what a manager checks
    before opening it is what the person actually gets — not an approximation
    of it built somewhere else.
    """
    person = db.get(User, user_id)
    if person is None:
        raise HTTPException(404, "No such person.")
    return _person_dashboard(db, person, batch_id)


@app.get("/api/dashboard/team")
def dashboard_team(batch_id: Optional[int] = None, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    """Every profile side by side.

    Two gates, and both must be open: this person has a dashboard at all, and
    the workspace shows the board to people who do.
    """
    require_dashboard(user)
    if user.role != "admin" and not read_settings(db)["team_board_visible"]:
        raise HTTPException(403, "Your manager has not opened the team board yet.")
    return dashboard.team_board(db, dashboard.pick_batch(db, batch_id),
                                include_private=user.role == "admin")


@app.get("/api/dashboard/overview")
def dashboard_overview(batch_id: Optional[int] = None, db: Session = Depends(get_db),
                       _: User = Depends(admin_only)):
    return {**dashboard.overview(db, dashboard.pick_batch(db, batch_id)),
            "settings": read_settings(db)}


@app.get("/api/dashboard/profiles/{profile_id}")
def dashboard_profile(profile_id: int, batch_id: Optional[int] = None,
                      db: Session = Depends(get_db), user: User = Depends(current_user)):
    """One profile close up. `linked_profile` is what stops a BD opening a
    colleague's record — the team board shows totals, not somebody else's diary.

    The developer behind a profile may open it without the dashboard switch a
    BD's figures sit behind. That switch exists so nobody is measured on a
    screen without somebody deciding to; this is the record of an identity that
    goes out in their name, which they are entitled to read.
    """
    profile = linked_profile(profile_id, db, user)
    if not (user.role == "dev" and profile.dev_user_id == user.id):
        require_dashboard(user)
    return dashboard.profile_detail(db, profile, dashboard.pick_batch(db, batch_id))


@app.get("/api/dashboard/dev")
def dashboard_developer(batch_id: Optional[int] = None, db: Session = Depends(get_db),
                        user: User = Depends(current_user)):
    """A developer's own screen: their calendar, their identities, their record.

    Open to them from the moment the account exists. A developer who cannot see
    their own interviews misses them, which is a different kind of harm from a
    BD seeing a figure nobody meant to show them.
    """
    if user.role not in ("dev", "admin"):
        raise HTTPException(403, "This screen is for the developers behind the profiles.")
    return dashboard.for_developer(db, user, dashboard.pick_batch(db, batch_id))


@app.get("/api/dashboard/devs/{user_id}")
def dashboard_developer_as(user_id: int, batch_id: Optional[int] = None,
                           db: Session = Depends(get_db), _: User = Depends(admin_only)):
    """One developer's screen, exactly as they see it. Manager only."""
    person = db.get(User, user_id)
    if person is None:
        raise HTTPException(404, "No such person.")
    return dashboard.for_developer(db, person, dashboard.pick_batch(db, batch_id))


# --------------------------------------------------------------------------- #
# Interviews — the first thing here that records an outcome
# --------------------------------------------------------------------------- #

def _clash(db: Session, profile: Profile, when: dt.datetime, minutes: int,
           ignore: Optional[int] = None) -> Optional[dict]:
    """Whether the developer behind this profile is already busy then.

    Checked across every identity the same developer is sold under, not just
    this one. Two profiles are two candidates as far as a client is concerned,
    but they are one person's Tuesday afternoon, and that is exactly where a
    double-booking hides. A profile with nobody behind it is checked only
    against itself.

    Reported, never refused. Back-to-back rounds with the same client are
    normal, a rescheduled interview legitimately overlaps the slot it is
    moving out of, and an app that argues with the person who was on the call
    gets worked around rather than fixed.
    """
    ids = [profile.id]
    if profile.dev_user_id is not None:
        shared = [row for (row,) in db.execute(
            select(Profile.id).where(Profile.dev_user_id == profile.dev_user_id,
                                     Profile.is_active == True)).all()]  # noqa: E712
        ids = shared or ids
    ends = when + dt.timedelta(minutes=max(1, minutes))

    query = select(Interview).where(Interview.profile_id.in_(ids),
                                    Interview.status == "scheduled",
                                    Interview.scheduled_at < ends)
    if ignore is not None:
        query = query.where(Interview.id != ignore)
    for other in db.scalars(query.order_by(Interview.scheduled_at)):
        finish = other.scheduled_at + dt.timedelta(
            minutes=max(1, other.duration_minutes or 30))
        if finish > when:
            names = {p.id: p.name for p in db.scalars(
                select(Profile).where(Profile.id == other.profile_id))}
            return {"id": other.id, "profile": names.get(other.profile_id, "?"),
                    "client": other.client, "when": working_label(other.scheduled_at)}
    return None


def _when(text: str) -> dt.datetime:
    try:
        return from_working(text)
    except ValueError:
        raise HTTPException(400, "That is not a date and time this app can read. "
                                 "Use the picker, or 2026-08-24T14:30.")


def _interview_json(db: Session, row: Interview) -> dict:
    return interviews.decorate(db, [row])[0]


@app.get("/api/interviews")
def list_interviews(profile_id: Optional[int] = None, db: Session = Depends(get_db),
                    user: User = Depends(current_user)):
    """Today, what is coming, what just happened — for whoever is asking.

    Not behind the dashboard switch. That switch is about being *measured*;
    this is a calendar, and hiding somebody's calendar from them only means
    they miss the call.
    """
    if profile_id is not None:
        linked_profile(profile_id, db, user)
        ids: Optional[list[int]] = [profile_id]
    else:
        ids = visible_profile_ids(db, user)
    rows = interviews.decorate(db, interviews.load(db, ids))
    return {"rows": rows, "counts": interviews.counts(rows),
            "funnel": interviews.funnel(db, ids),
            # What the scheduling form starts on. Worked out here rather than
            # in the browser: the field means Eastern, and a machine in Karachi
            # prefilling its own clock would suggest a time nine hours from the
            # one it appears to say.
            "suggested_time": working_label(utcnow() + dt.timedelta(hours=1))["input"],
            **interviews.split(rows)}


@app.post("/api/interviews", status_code=201)
def create_interview(body: InterviewIn, db: Session = Depends(get_db),
                     user: User = Depends(current_user)):
    """Log a reply that turned into a conversation.

    Usually the BD, who runs the account the client answered. Sometimes the
    developer, who was the one emailed. Both may, because both find out first
    about half the time, and the one who knows should not have to ask somebody
    else to type it in.
    """
    profile = linked_profile(body.profile_id, db, user)
    when = _when(body.scheduled_at)
    if body.mode not in INTERVIEW_MODES:
        raise HTTPException(400, f"Mode must be one of {', '.join(INTERVIEW_MODES)}.")
    if body.job_id is not None and not db.get(Job, body.job_id):
        raise HTTPException(400, "No such job to attach it to.")

    minutes = min(600, max(5, body.duration_minutes or 30))
    clash = _clash(db, profile, when, minutes)

    row = Interview(profile_id=profile.id, job_id=body.job_id,
                    client=body.client.strip()[:300], role=body.role.strip()[:300],
                    scheduled_at=when, duration_minutes=minutes, mode=body.mode,
                    link=_check_link(body.link, "meeting link"),
                    notes=body.notes.strip(), created_by=user.id)
    db.add(row)
    db.commit()
    return {**_interview_json(db, row), "clash": clash}


@app.patch("/api/interviews/{interview_id}")
def update_interview(interview_id: int, body: InterviewPatch,
                     db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Move it, or say how it went."""
    row = db.get(Interview, interview_id)
    if not row:
        raise HTTPException(404, "No such interview.")
    profile = linked_profile(row.profile_id, db, user)

    clash = None
    if body.scheduled_at is not None:
        row.scheduled_at = _when(body.scheduled_at)
    if body.duration_minutes is not None:
        row.duration_minutes = min(600, max(5, body.duration_minutes))
    if body.scheduled_at is not None or body.duration_minutes is not None:
        clash = _clash(db, profile, row.scheduled_at, row.duration_minutes,
                       ignore=row.id)
    if body.client is not None:
        row.client = body.client.strip()[:300]
    if body.role is not None:
        row.role = body.role.strip()[:300]
    if body.mode is not None:
        if body.mode not in INTERVIEW_MODES:
            raise HTTPException(400, f"Mode must be one of {', '.join(INTERVIEW_MODES)}.")
        row.mode = body.mode
    if body.link is not None:
        row.link = _check_link(body.link, "meeting link")
    if body.notes is not None:
        row.notes = body.notes.strip()
    if body.status is not None:
        if body.status not in INTERVIEW_STATUSES:
            raise HTTPException(400, f"Status must be one of {', '.join(INTERVIEW_STATUSES)}.")
        row.status = body.status
    if body.outcome is not None:
        if body.outcome not in INTERVIEW_OUTCOMES:
            raise HTTPException(400, f"Outcome must be one of {', '.join(INTERVIEW_OUTCOMES)}.")
        row.outcome = body.outcome
        # Nobody records how an interview went before it happens. Saying it was
        # a rejection while the row still reads "scheduled" would leave it on
        # somebody's list of things to turn up to, and in the count of
        # interviews nobody has reported back on.
        if body.outcome != "pending" and row.status == "scheduled":
            row.status = "done"
    db.commit()
    return {**_interview_json(db, row), "clash": clash}


@app.delete("/api/interviews/{interview_id}")
def delete_interview(interview_id: int, db: Session = Depends(get_db),
                     user: User = Depends(current_user)):
    """Remove one entered by mistake.

    Cancelling is the usual thing and keeps the row, because a client who
    pulled out is worth knowing about. This is for the interview that was never
    real — so it is the manager's, or the person who typed it.
    """
    row = db.get(Interview, interview_id)
    if not row:
        raise HTTPException(404, "No such interview.")
    linked_profile(row.profile_id, db, user)
    if user.role != "admin" and row.created_by != user.id:
        raise HTTPException(403, "Cancel it instead, or ask whoever logged it to remove it.")
    db.delete(row)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Downloads
# --------------------------------------------------------------------------- #

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@app.get("/api/batches/{batch_id}/profiles/{profile_id}/sheet.xlsx")
def download_profile_sheet(batch_id: int, profile_id: int, db: Session = Depends(get_db),
                           user: User = Depends(current_user)):
    profile = owned_profile(profile_id, db, user)
    jobs = _assignment_rows(db, batch_id, profile.id)
    if not jobs:
        raise HTTPException(404, "Nothing has been dispatched to this profile in this batch.")
    data = exports.assignment_workbook(profile.name, jobs)
    filename = f"{profile.name.replace(' ', '-').lower()}-batch-{batch_id}.xlsx"
    return Response(data, media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/api/batches/{batch_id}/report.xlsx")
def download_report(batch_id: int, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    data = report(batch_id, db, _)
    grouped = _all_assignment_rows(db, batch_id)
    per_profile = {p["name"]: grouped.get(p["id"], []) for p in data["participants"]}
    payload = exports.report_workbook(
        data["report"], per_profile, data["collisions"],
        data["matrix"]["names"], data["matrix"]["rows"])
    return Response(payload, media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="dispatch-batch-{batch_id}.xlsx"'})


@app.get("/api/health")
def health():
    return {"ok": True, "time": utcnow().isoformat()}


# --------------------------------------------------------------------------- #
# First run, and serving the browser app
# --------------------------------------------------------------------------- #

def bootstrap_admin() -> None:
    """Create the first manager from the environment, once, on an empty database.

    A hosted deployment often has no shell to run seed.py in — on Render's free
    tier there is none at all — so the account that lets you in has to be able
    to create itself. Does nothing if any manager already exists, so it cannot
    resurrect an account you deliberately removed.
    """
    email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    password = os.getenv("ADMIN_PASSWORD", "")
    if not email or len(password) < 8:
        return
    db = SessionLocal()
    try:
        if db.scalar(select(User).where(User.role == "admin")):
            return
        db.add(User(email=email, name=os.getenv("ADMIN_NAME", "Manager").strip() or "Manager",
                    password_hash=hash_password(password), role="admin"))
        db.commit()
        print(f"Created the first manager account: {email}")
    finally:
        db.close()


bootstrap_admin()

if WEB_ROOT and os.path.isdir(WEB_ROOT):
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    _INDEX = os.path.join(WEB_ROOT, "index.html")
    app.mount("/assets", StaticFiles(directory=os.path.join(WEB_ROOT, "assets")),
              name="assets")

    # Registered last, so every /api route above already owns its path. React
    # does its own routing, so anything else hands back index.html rather than
    # a 404 — but a wrong /api path must still fail like an API, not like a page.
    @app.get("/{path:path}", include_in_schema=False)
    def browser_app(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "No such endpoint.")
        candidate = os.path.join(WEB_ROOT, path)
        if path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(_INDEX)
