import React, { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
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
 * Not behind the dashboard switch a BD's figures sit behind. That switch
 * exists so nobody is measured without somebody deciding to measure them; this
 * is a calendar and a resume, and withholding it only means nobody turns up.
 */
export default function DevHome({ onOpenProfiles }) {
  const [data, setData] = useState(null);
  const [batchId, setBatchId] = useState(null);
  const [profiles, setProfiles] = useState([]);
  const [error, setError] = useState("");
  const [all, setAll] = useState(false);

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

  if (error && !data) return <div className="notice">{error}</div>;
  if (!data) return <p className="muted">Loading your day…</p>;

  const { counts, today, upcoming, recent, funnel, totals } = data;
  const next = today.find((row) => !row.is_past && row.status === "scheduled")
    || upcoming.find((row) => row.status === "scheduled");

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

      {next
        ? <NextInterview row={next} onOpen={() => setAll((on) => !on)}
                         openLabel={all ? "Hide the diary" : "Open the diary"} />
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
            <button className="ghost" onClick={() => setAll((on) => !on)}>
              {all ? "Hide the diary" : "Open the diary"}
            </button>
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
          You were the one in the room. Setting the outcome below is the only thing that tells
          your team whether the applications going out in your name are working.
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
          <InterviewRows rows={today} showProfile onChange={(id, patch) =>
            api.updateInterview(id, patch).then(() => load(batchId)).catch((e) => setError(e.message))} />
        </section>
      )}

      {all ? (
        <Interviews
          profiles={profiles}
          heading="Your diary"
          intro="Every interview against the identities you are applied under. Log one yourself if a
                 client emailed you directly."
          showProfile
          showFunnel={false}
        />
      ) : (
        upcoming.length > 0 && (
          <section className="stack" style={{ gap: 8 }}>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <div>
                <h2>Coming up</h2>
                <p className="muted" style={{ marginTop: 3 }}>The next fortnight.</p>
              </div>
              <button className="ghost" onClick={() => setAll(true)}>Open the diary</button>
            </div>
            <InterviewRows rows={upcoming} showProfile onChange={(id, patch) =>
              api.updateInterview(id, patch).then(() => load(batchId)).catch((e) => setError(e.message))} />
          </section>
        )
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
              Interviews that have been and gone. Setting the outcome is what tells your team
              whether the applications going out in your name are working.
            </p>
          </div>
          <InterviewRows rows={recent} showProfile onChange={(id, patch) =>
            api.updateInterview(id, patch).then(() => load(batchId)).catch((e) => setError(e.message))} />
        </section>
      )}
    </div>
  );
}
