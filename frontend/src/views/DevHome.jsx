import React, { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import Assessments from "./Assessments.jsx";
import Interviews from "./Interviews.jsx";
import {
  Availability, CopyButton, CyclePicker, Funnel, InterviewRows, NextInterview,
  Skills, Sparkline, Tiles,
} from "./widgets.jsx";

/** A developer's own screen.
 *
 * The mirror of the BD dashboard, pointed the other way. A BD asks how much
 * went out; a developer asks what is coming back and where they have to be at
 * two o'clock. Same figures underneath — they are entitled to know how hard
 * their identities are being worked — but the thing at the top is the next
 * interview, not the row count.
 *
 * A developer books here too. A client that found them directly emails them
 * directly, and making them ask somebody else to type it in is how a reply sits
 * unanswered for a day. What stops one reply becoming two rows is not a
 * permission but the clash check, which fires on any booking against the same
 * developer whichever identity it was made under.
 *
 * The half only they can answer is still the half the screen leads them to:
 * whether the call happened, what came of it, and how it actually went.
 *
 * A developer may be sold under several identities, and the question they ask
 * is usually about one of them — what has Khuram got today. So the diary
 * narrows to one profile at a time, and the figures narrow with it rather than
 * staying whole and quietly disagreeing with the list underneath them.
 *
 * Not behind the dashboard switch a BD's figures sit behind. That switch
 * exists so nobody is measured without somebody deciding to measure them; this
 * is a calendar and a resume, and withholding it only means nobody turns up.
 */
export default function DevHome({ onOpenProfiles }) {
  const [data, setData] = useState(null);
  const [batchId, setBatchId] = useState(null);
  const [profiles, setProfiles] = useState([]);
  const [error, setError] = useState("");
  // null is every identity at once. Anything else is one profile's id, and the
  // diary, the counts and the funnel are all re-fetched narrowed to it — the
  // server already answers that question, so nothing here has to filter a list
  // and then disagree with a tile that was worked out from the whole one.
  const [only, setOnly] = useState(null);
  const [scoped, setScoped] = useState(null);
  const [tests, setTests] = useState(null);
  // desk | diary | assessments — the diary and the assessments are full
  // screens rather than a strip on the desk once there is anything in them.
  const [pane, setPane] = useState("desk");

  const load = useCallback(async (id) => {
    try {
      const next = await api.devDashboard(id);
      setData(next);
      if (!id && next.batch) setBatchId(next.batch.id);
      setError("");
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => { load(batchId); }, [batchId, load]);
  useEffect(() => { api.listProfiles().then(setProfiles).catch(() => setProfiles([])); }, []);

  // A BD may book something into this diary at any moment, and the person
  // reading it is the one who has to be there. Stale is worse here than
  // anywhere else in the app.
  useEffect(() => {
    const tick = setInterval(() => load(batchId), 60000);
    return () => clearInterval(tick);
  }, [batchId, load]);

  useEffect(() => {
    if (!only) {
      setScoped(null);
      return undefined;
    }
    let live = true;
    const pull = () => api.interviews(only)
      .then((next) => { if (live) setScoped(next); })
      .catch((err) => { if (live) setError(err.message); });
    pull();
    const tick = setInterval(pull, 60000);
    return () => { live = false; clearInterval(tick); };
  }, [only]);

  // A BD can set a take-home at any moment, and the deadline on it is usually
  // days rather than weeks.
  useEffect(() => {
    const pull = () => api.assessments(only)
      .then((next) => setTests(next.counts))
      .catch(() => {});
    pull();
    const tick = setInterval(pull, 60000);
    return () => clearInterval(tick);
  }, [only]);

  if (error && !data) return <div className="notice">{error}</div>;
  if (!data) return <p className="muted">Loading your day…</p>;

  // Until the narrowed diary lands, the whole one stands in. It is a fraction
  // of a second, and a blank calendar is a worse thing to show somebody than a
  // slightly wider one.
  const diary = (only && scoped) || data;
  const { counts, today, upcoming, recent, funnel } = diary;
  const { totals } = data;
  const chosen = only ? data.profiles.find((row) => row.profile_id === only) : null;
  const next = today.find((row) => !row.is_past && row.status === "scheduled")
    || upcoming.find((row) => row.status === "scheduled");

  // Every write from this screen goes through here so the person-wide figures
  // and the narrowed ones cannot drift apart after an edit.
  const report = (id, patch) => api.updateInterview(id, patch)
    .then(async (saved) => {
      await load(batchId);
      if (only) setScoped(await api.interviews(only));
      return saved;
    })
    .catch((e) => { setError(e.message); return null; });

  if (!data.profiles.length) {
    return (
      <div className="stack">
        <h1>Your desk</h1>
        <div className="notice">
          No profile is attached to you yet, so there is nothing here. A profile is the
          identity your team applies under — your name and resume as the client sees them.
          Ask your manager to put you behind one under <b>People and profiles</b>, and this
          screen fills in on its own.
        </div>
      </div>
    );
  }

  return (
    <div className="stack">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1>Your desk</h1>
          <p className="muted" style={{ marginTop: 3 }}>
            {chosen && <>As <b>{chosen.name}</b>. </>}
            {counts.today
              ? <>You have <b>{counts.today} interview{counts.today === 1 ? "" : "s"} today</b>. All times Eastern.</>
              : counts.scheduled
                ? <>Nothing today. {counts.scheduled} still ahead of you, Eastern time.</>
                : "Nothing in the diary. Your team is applying under your name; replies land here."}
          </p>
        </div>
        <CyclePicker batches={data.batches} value={batchId || data.batch?.id} onChange={setBatchId} />
      </div>

      {error && <div className="notice">{error}</div>}

      {data.profiles.length > 1 && (
        <section className="card pad">
          <h3>Which identity are you looking at?</h3>
          <div className="row" style={{ marginTop: 10 }}>
            <button className={only ? "ghost" : ""} onClick={() => setOnly(null)}>
              All of them
            </button>
            {data.profiles.map((row) => (
              <button key={row.profile_id}
                      className={only === row.profile_id ? "" : "ghost"}
                      onClick={() => setOnly(row.profile_id)}>
                {row.name}
                <span style={{ opacity: 0.7, fontWeight: 400 }}>
                  {row.headline ? ` · ${row.headline}` : ""}
                </span>
              </button>
            ))}
          </div>
          <p className="muted" style={{ marginTop: 9 }}>
            Each of these is a different candidate as far as a client is concerned, with its own
            BD, its own resume and its own diary. Everything below — today, what is coming, and
            what it all turned into — narrows to whichever you pick.
          </p>
        </section>
      )}

      {tests?.overdue > 0 && (
        <div className="notice">
          <b>{tests.overdue} assessment{tests.overdue === 1 ? " is" : "s are"} past the
          deadline.</b>{" "}
          A missed take-home costs the interview that earned it.{" "}
          <button className="link" onClick={() => setPane("assessments")}>Open them</button>
        </div>
      )}

      <div className="row" style={{ gap: 8 }}>
        <button className={pane === "desk" ? "" : "ghost"} onClick={() => setPane("desk")}>
          Today
        </button>
        <button className={pane === "diary" ? "" : "ghost"} onClick={() => setPane("diary")}>
          Every interview{counts.total ? ` (${counts.total})` : ""}
        </button>
        <button className={pane === "assessments" ? "" : "ghost"}
                onClick={() => setPane("assessments")}>
          Assessments{tests?.open ? ` (${tests.open})` : ""}
        </button>
      </div>

      {pane === "assessments" ? (
        <Assessments
          profiles={only ? profiles.filter((p) => p.id === only) : profiles}
          profileId={only}
          heading={chosen ? `${chosen.name}'s assessments` : "Your assessments"}
          intro="Take-homes and tests set against the identities you are sold under. Your BD
                 usually sets them, because the client sends them the brief — doing them, and
                 saying how far along you are, is yours. Set one yourself if a client sent it
                 straight to you."
        />
      ) : pane === "diary" ? (
        <Interviews
          profiles={only ? profiles.filter((p) => p.id === only) : profiles}
          profileId={only}
          heading={chosen ? `${chosen.name}'s interviews` : "Every interview"}
          intro="Everything against the identities you are applied under — what is coming, what
                 has been, and how each of them went. Book one yourself if a client emailed you
                 directly."
          showProfile
          showFunnel
        />
      ) : (
        <>
      {next
        ? <NextInterview row={next} onOpen={() => setPane("diary")}
                         openLabel="Open the diary" />
        : (
          <section className="card pad row headline" style={{ justifyContent: "space-between" }}>
            <div>
              <div className="mono headline-figure" style={{ color: "var(--pine)" }}>0</div>
              <div>
                <b style={{ fontFamily: "var(--display)", fontSize: 15 }}>Nothing booked</b>
                <p className="muted" style={{ marginTop: 2 }}>
                  {totals.assigned || totals.logged
                    ? "Applications are still going out under your name. A reply turns into a row here the moment somebody logs it."
                    : "Nothing has gone out under your profiles yet."}
                </p>
              </div>
            </div>
            <button className="ghost" onClick={() => setPane("diary")}>Open the diary</button>
          </section>
        )}

      <Tiles items={[
        { label: "interviews today", value: counts.today,
          tone: counts.today ? "petrol" : undefined },
        { label: "in the next seven days", value: counts.week },
        { label: "you have not reported on", value: counts.awaiting_outcome,
          tone: counts.awaiting_outcome ? "brick" : undefined,
          hint: "They have been and gone with nobody saying how they went." },
        { label: "offers", value: funnel.offers, tone: funnel.offers ? "pine" : undefined },
        { label: "applications under your name", value: funnel.applications,
          foot: "all time" },
        { label: "of them reached an interview", value: `${funnel.interview_rate}%` },
      ]} />

      {counts.awaiting_outcome > 0 && (
        <div className="notice">
          <b>{counts.awaiting_outcome} interview
          {counts.awaiting_outcome === 1 ? "" : "s"} happened and nobody has said how it went.</b>{" "}
          You were the one in the room, so this one is yours — nobody else can answer it
          first-hand. Set the outcome below, and open <b>notes</b> on the row to say how it
          actually went. Your BD reads both on their own screen within the minute.
        </div>
      )}

      {today.length > 0 && (
        <section className="stack" style={{ gap: 8 }}>
          <div>
            <h2>Today</h2>
            <p className="muted" style={{ marginTop: 3 }}>
              Everything today, including what has already been — Eastern time.
            </p>
          </div>
          <InterviewRows rows={today} showProfile onChange={report} />
        </section>
      )}

      {upcoming.length > 0 && (
        <section className="stack" style={{ gap: 8 }}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <div>
              <h2>Coming up</h2>
              <p className="muted" style={{ marginTop: 3 }}>The next fortnight.</p>
            </div>
            <button className="ghost" onClick={() => setPane("diary")}>Open the diary</button>
          </div>
          <InterviewRows rows={upcoming} showProfile onChange={report} />
        </section>
      )}

      <section className="stack" style={{ gap: 8 }}>
        <div>
          <h2>What your applications turned into</h2>
          <p className="muted" style={{ marginTop: 3, maxWidth: 720 }}>
            Every other figure your team looks at counts effort — rows typed, jobs dispatched.
            This one counts what came of it, and it is the only one that cannot be improved by
            typing faster.
          </p>
        </div>
        <Funnel data={funnel} awaiting={counts.awaiting_outcome} />
      </section>

      <section className="stack" style={{ gap: 10 }}>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <div>
            <h2>The identities you are applied under</h2>
            <p className="muted" style={{ marginTop: 3 }}>
              What a client sees when your team applies for you. Keep the resume and the address
              right — these are what goes out.
            </p>
          </div>
          {onOpenProfiles && <button className="ghost" onClick={onOpenProfiles}>Edit your details</button>}
        </div>
        <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(300px,1fr))" }}>
          {data.profiles.map((row) => (
            <div className="card pad stack" key={row.profile_id} style={{ gap: 9 }}>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <div style={{ fontFamily: "var(--display)", fontWeight: 600, fontSize: 15 }}>
                    {row.name}
                  </div>
                  <div className="muted">
                    {row.headline || "—"}{row.person ? ` · run by ${row.person}` : ""}
                  </div>
                </div>
                <Availability value={row.availability} />
              </div>

              <div className="figures">
                <div><b className="mono">{row.logged}</b><span>logged this cycle</span></div>
                <div><b className="mono">{row.applied}</b><span>applied</span></div>
                <div><b className="mono">{row.all_time}</b><span>all time</span></div>
                <div><b className="mono">{row.rate || "—"}</b><span>rate</span></div>
              </div>

              <Skills value={row.skills} limit={6} />

              <div className="stack" style={{ gap: 4 }}>
                <div className="row" style={{ gap: 8 }}>
                  <span className="muted" style={{ minWidth: 54 }}>email</span>
                  <span className="mono" style={{ fontSize: 12 }}>{row.email || "—"}</span>
                  <CopyButton value={row.email} />
                </div>
                <div className="row" style={{ gap: 8 }}>
                  <span className="muted" style={{ minWidth: 54 }}>resume</span>
                  {/^https?:\/\//i.test(row.resume_url) ? (
                    <>
                      <a href={row.resume_url} target="_blank" rel="noreferrer noopener">open it</a>
                      <CopyButton value={row.resume_url} label="copy link" />
                    </>
                  ) : <span className="muted">not set — your team has nothing to send</span>}
                </div>
                {row.timezone && (
                  <div className="row" style={{ gap: 8 }}>
                    <span className="muted" style={{ minWidth: 54 }}>hours</span>
                    <span style={{ fontSize: 12 }}>{row.timezone}</span>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h3>Applications logged under your name</h3>
        <p className="muted" style={{ margin: "3px 0 9px" }}>
          The last thirty days, in Eastern time. This is your team working; you are seeing it,
          not being measured on it.
        </p>
        <div className="card pad"><Sparkline series={data.activity} /></div>
      </section>

      {recent.length > 0 && (
        <section className="stack" style={{ gap: 8 }}>
          <div>
            <h2>Your record</h2>
            <p className="muted" style={{ marginTop: 3 }}>
              Interviews that have been and gone. Setting the outcome, and writing the note
              under <b>notes</b>, is what tells your team whether the applications going out in
              your name are working — and it is the only part of this row they cannot fill in
              themselves.
            </p>
          </div>
          <InterviewRows rows={recent} showProfile onChange={report} />
        </section>
      )}
        </>
      )}
    </div>
  );
}
