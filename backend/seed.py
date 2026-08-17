"""Create the first accounts and profiles, and optionally sample sheets.

    python seed.py                 # accounts and profiles only
    python seed.py --samples       # plus CSVs in ./sample_sheets

The sample data is built to show the thing that matters: two profiles with the
same skills, run by two different people, each handing in what they applied to.
Ali runs Khuram and logs 30 jobs; Sara runs Zahid and logs 50. Ten of those are
the same posting found twice. Run the cycle and Khuram gets back the 40 jobs it
has never seen, Zahid the 20 it has never seen.
"""
from __future__ import annotations

import argparse
import csv
import os
import random
from pathlib import Path

from sqlalchemy import select

from app.main import SessionLocal, engine, hash_password
from app.models import Base, Profile, User

TEAM = [
    ("ali@example.com", "Ali Raza"),
    ("sara@example.com", "Sara Khan"),
    ("hina@example.com", "Hina Malik"),
]

# name -> (headline, platform, whose account runs it)
PROFILES = [
    ("Khuram", "AI Engineer", "Upwork", "ali@example.com"),
    ("Zahid", "AI Engineer", "Upwork", "sara@example.com"),
    ("Nadia", "Full Stack Engineer", "Upwork", "hina@example.com"),
]

CLIENTS = [
    "Northwind Digital", "Ravensberg GmbH", "Bluepeak Studio", "Talloak Systems",
    "Verdant Labs", "Kite & Compass", "Orchard Retail Pvt Ltd", "Sable Analytics",
    "Copperline Media", "Harbourstone LLC", "Fernwood Health", "Quillmark Inc",
    "Alderpoint AI", "Mistvale Robotics", "Cobalt & Fern", "Larkspur Data",
]

ROLES = [
    "LLM Fine-tuning Engineer", "RAG Pipeline Developer", "Computer Vision Engineer",
    "ML Ops Engineer - AWS", "Chatbot Developer (OpenAI API)", "Data Scraping Automation",
    "Python Automation Scripts", "Recommendation System Engineer",
    "Speech-to-Text Integration", "Document AI / OCR Specialist",
    "Senior React Developer", "Django Backend Developer",
]

PLATFORMS = ["Upwork", "LinkedIn", "Indeed", "Freelancer"]


def build_url(platform: str, seed: int) -> str:
    if platform == "Upwork":
        return f"https://www.upwork.com/jobs/~01{seed:016x}"
    if platform == "LinkedIn":
        return f"https://www.linkedin.com/jobs/view/{3900000000 + seed}"
    if platform == "Indeed":
        return f"https://pk.indeed.com/viewjob?jk={seed:016x}&from=serp"
    return f"https://www.freelancer.com/projects/php/site-build-{7000000 + seed}"


def seed_accounts() -> None:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    created = []

    if not db.scalar(select(User).where(User.role == "admin")):
        db.add(User(email="admin@example.com", name="Manager",
                    password_hash=hash_password("admin12345"), role="admin"))
        created.append("admin@example.com / admin12345   manager")
    for email, name in TEAM:
        if not db.scalar(select(User).where(User.email == email)):
            db.add(User(email=email, name=name,
                        password_hash=hash_password("bdpass12345"), role="bd"))
            created.append(f"{email} / bdpass12345   {name}")
    db.commit()

    owners = {u.email: u.id for u in db.scalars(select(User)).all()}
    for name, headline, platform, email in PROFILES:
        if not db.scalar(select(Profile).where(Profile.name == name)):
            db.add(Profile(name=name, headline=headline, platform=platform,
                           user_id=owners.get(email)))
            created.append(f"profile {name} ({headline}) run by {email}")
    db.commit()
    db.close()

    print("Accounts and profiles ready.")
    for line in created:
        print("  ", line)
    if not created:
        print("   (everything already existed)")


def make_samples(folder: str = "sample_sheets") -> None:
    """Sheets with a known, checkable overlap.

    Khuram logs jobs 0-29. Zahid logs jobs 20-69 — so the two share exactly ten
    postings (20-29). The union is 70. Khuram has never seen 40 of them, Zahid
    has never seen 20, and those are the numbers the cycle should hand back.

    Nadia's sheet uses different column names, blank links on some rows and
    shouty titles, to exercise the auto-mapper and the fuzzy tier.
    """
    random.seed(7)
    Path(folder).mkdir(exist_ok=True)

    def catalogue(n: int) -> dict:
        platform = PLATFORMS[n % len(PLATFORMS)]
        return {"title": ROLES[n % len(ROLES)], "company": CLIENTS[n % len(CLIENTS)],
                "platform": platform, "url": build_url(platform, 1000 + n),
                "date": f"2026-08-{(n % 28) + 1:02d}"}

    plan = [
        ("Khuram", range(0, 30), False),
        ("Zahid", range(20, 70), True),      # 20-29 overlap with Khuram
        ("Nadia", range(70, 110), False),
    ]

    for name, job_ids, tracking in plan:
        rows = []
        for n in job_ids:
            job = catalogue(n)
            url = job["url"]
            if tracking:
                # Same posting, different referral link — must still match.
                url += "?utm_source=email&referrer=digest"
            rows.append({**job, "url": url})

        path = os.path.join(folder, f"{name.lower()}-applied.csv")
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            if name == "Nadia":
                writer.writerow(["Sr", "Position Applied", "Client Name",
                                 "Job Portal", "Post Link", "Apply Date"])
                for i, row in enumerate(rows, 1):
                    link = "" if i % 3 == 0 else row["url"]
                    title = row["title"].upper() if i % 4 == 0 else row["title"]
                    writer.writerow([i, title, row["company"], row["platform"],
                                     link, row["date"]])
            else:
                writer.writerow(["Job Title", "Company", "Platform", "Job URL", "Applied On"])
                for row in rows:
                    writer.writerow([row["title"], row["company"], row["platform"],
                                     row["url"], row["date"]])
        print(f"  wrote {path}  ({len(rows)} rows for profile {name})")

    print(f"\nSample sheets are in ./{folder}/")
    print("Khuram logged 30, Zahid logged 50, sharing 10 — a pool of 70.")
    print("A coverage cycle should hand Khuram 40 back and Zahid 20.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", action="store_true", help="also write sample CSVs")
    args = parser.parse_args()
    seed_accounts()
    if args.samples:
        print("\nGenerating sample sheets…")
        make_samples()
