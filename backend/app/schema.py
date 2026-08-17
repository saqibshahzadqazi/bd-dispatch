"""Bring an existing database up to the current shape.

There is no migration framework here on purpose — one file of plain SQLAlchemy
is easier to read, and to distrust, than a chain of generated revisions.

Version 1 keyed everything on the person who uploaded a sheet. Version 2 keys it
on the profile the job was applied under, because a person may run several and a
profile may be handed between people. That is not a column you can bolt on: the
old `applications` table carries UNIQUE(job_id, user_id), which forbids exactly
the case v2 exists to support — one person's two profiles both applying to the
same job. So the affected tables are rebuilt rather than altered.

Everything below is idempotent. A brand new database skips it entirely.
"""
from __future__ import annotations

from sqlalchemy import Engine, MetaData, Table, inspect, insert, select, text

from .models import Base

# Tables whose primary key changed meaning between v1 and v2.
REKEYED = ("uploads", "applications", "batch_applications", "assignments")


def bring_up_to_date(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "uploads" not in tables:
        return                                   # fresh database; create_all did it all
    if "profile_id" in {c["name"] for c in inspector.get_columns("uploads")}:
        return                                   # already v2
    _upgrade_from_v1(engine)


def _upgrade_from_v1(engine: Engine) -> None:
    profile_of = _give_everyone_a_profile(engine)

    with engine.begin() as conn:
        if "mode" not in {c["name"] for c in inspect(conn).get_columns("batches")}:
            conn.execute(text("ALTER TABLE batches ADD COLUMN mode VARCHAR(16)"))
        # Every cycle computed under v1 split the pool, so label them honestly
        # rather than letting them inherit the new default.
        conn.execute(text("UPDATE batches SET mode = 'split' WHERE mode IS NULL"))

        for table in REKEYED:
            # An index follows its table through a rename and keeps its old
            # name, so create_all would then collide with it. These are about
            # to be thrown away with the table anyway.
            for index in inspect(conn).get_indexes(table):
                conn.execute(text(f"DROP INDEX {index['name']}"))
            conn.execute(text(f"ALTER TABLE {table} RENAME TO {table}_v1"))

    Base.metadata.create_all(engine)              # recreate them in the v2 shape

    old = MetaData()
    with engine.begin() as conn:
        for table in REKEYED:
            source = Table(f"{table}_v1", old, autoload_with=conn)
            target = Base.metadata.tables[table]
            rows = [_translate(table, dict(row), profile_of, target)
                    for row in conn.execute(select(source)).mappings()]
            rows = [row for row in rows if row is not None]
            if rows:
                conn.execute(insert(target), rows)
            conn.execute(text(f"DROP TABLE {table}_v1"))


def _give_everyone_a_profile(engine: Engine) -> dict[int, int]:
    """One profile per existing person, inheriting that person's whole history.

    Names have to be unique, and two colleagues can share a first name, so a
    clash gets the person's id appended rather than silently merging two
    people's application history into one identity.
    """
    profiles = Base.metadata.tables["profiles"]
    with engine.begin() as conn:
        taken = {name.lower() for (name,) in conn.execute(select(profiles.c.name))}
        mapping = dict(conn.execute(
            select(profiles.c.user_id, profiles.c.id)
            .where(profiles.c.user_id.is_not(None))).all())

        for user_id, name in conn.execute(text("SELECT id, name FROM users")).all():
            if user_id in mapping:
                continue
            candidate = name.strip() or f"Profile {user_id}"
            if candidate.lower() in taken:
                candidate = f"{candidate} ({user_id})"
            taken.add(candidate.lower())
            result = conn.execute(insert(profiles).values(
                name=candidate, headline="", platform="",
                user_id=user_id, is_active=True))
            mapping[user_id] = result.inserted_primary_key[0]
    return mapping


def _translate(table: str, row: dict, profile_of: dict[int, int], target: Table):
    """Rewrite one v1 row into its v2 form, or None to drop it."""
    user_id = row.get("user_id")
    profile_id = profile_of.get(user_id)
    if profile_id is None and table in ("uploads", "applications",
                                        "batch_applications", "assignments"):
        return None                               # orphaned row, nothing to attach it to

    row["profile_id"] = profile_id
    if table == "assignments":
        # v1 dispatched a job to exactly one person, always.
        row["exclusive"] = True
        row.setdefault("status", "pending")
    if table == "batch_applications":
        row.pop("user_id", None)

    return {column: row.get(column) for column in target.columns.keys()
            if column != "id" or row.get("id") is not None}
