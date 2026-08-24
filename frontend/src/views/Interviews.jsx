import React, { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import { Funnel, InterviewRows, StageLadder, WaitingOnTime } from "./widgets.jsx";

/** Scheduling, and the list of what is scheduled.
 *
 * One component for three screens. A BD opens it for the profiles they run, a
 * developer for the identities they are sold under, a manager for everything —
 * and the server decides which of those it is from the token, so the only
 * difference here is which profiles the picker offers.
 *
 * Who may do what is one prop. `canSchedule` is the BD and the manager: the
 * client replied to the account the applications went out from, so booking it,
 * moving it and briefing the developer are all theirs. A developer opens the
 * same screen read-only over the booking and writes the one part nobody else
 * can answer — what happened on the call. The server holds both halves of that
 * whatever this file passes down; the prop only saves somebody a dead end.
 *
 * `profileId` narrows the whole screen to one identity. A developer sold under
 * three profiles usually wants "what has Khuram got today", not the union.
 *
 * Every time on this screen is Eastern, said out loud in the form and again on
 * every row, because the one thing worse than a missed interview is two people
 * confidently reading the same row as two different hours.
 */

const BLANK = {
  profile_id: "",
  scheduled_at: "",
  client: "",
  role: "",
  mode: "video",
  duration_minutes: 30,
  link: "",
  notes: "",
  stage: "screening",
};

/* The picker starts on `suggested_time` from the server — an hour from now on
   the team's clock. It is not worked out here on purpose: the field means
   Eastern, and a machine in Karachi prefilling its own clock would suggest a
   time nine hours away from the one it appears to say. Nothing in this file
   does date arithmetic. */

export default function Interviews({
  profiles = [],
  heading = "Interviews",
  intro = "",
  canSchedule = true,
  showProfile = true,
  showFunnel = false,
  profileId = null,
}) {
  const [data, setData] = useState(null);
  const [form, setForm] = useState(BLANK);
  const [note, setNote] = useState(null);
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    try {
      const next = await api.interviews(profileId);
      setData(next);
      // Only ever fills an empty field, so a refresh in the background cannot
      // move a time somebody is halfway through typing.
      setForm((current) => (current.scheduled_at
        ? current
        : { ...current, scheduled_at: next.suggested_time }));
    } catch (err) {
      setNote({ bad: true, text: err.message });
    }
  }, [profileId]);

  useEffect(() => { load(); }, [load]);

  // Somebody else may be booking into the same calendar, so this screen does
  // not get to assume it is the only writer.
  useEffect(() => {
    const tick = setInterval(load, 60000);
    return () => clearInterval(tick);
  }, [load]);

  // One profile is the overwhelmingly common case; picking it for them saves a
  // click on every single interview.
  useEffect(() => {
    if (profiles.length && !form.profile_id) {
      setForm((current) => ({ ...current, profile_id: String(profiles[0].id) }));
    }
  }, [profiles, form.profile_id]);

  const byId = useMemo(
    () => Object.fromEntries(profiles.map((p) => [String(p.id), p])),
    [profiles]
  );

  const schedule = async () => {
    setBusy(true);
    setNote(null);
    try {
      const made = await api.createInterview({
        ...form,
        profile_id: Number(form.profile_id),
        duration_minutes: Number(form.duration_minutes) || 30,
      });
      setForm({ ...BLANK, scheduled_at: data?.suggested_time || "",
                profile_id: form.profile_id });
      setAdding(false);
      await load();
      setNote(made.clash
        ? {
          bad: true,
          text: `Booked — but ${made.clash.profile} already has ${made.clash.client || "an interview"} `
            + `at ${made.clash.when.label}. That is the same person twice over. Move one of them.`,
        }
        : { text: `${made.client || "The interview"} is in the diary for ${made.when.label}, Eastern.` });
    } catch (err) {
      setNote({ bad: true, text: err.message });
    } finally {
      setBusy(false);
    }
  };

  const change = async (id, patch) => {
    try {
      const saved = await api.updateInterview(id, patch);
      await load();
      if (saved.clash) {
        setNote({ bad: true, text: `Moved — but that now overlaps ${saved.clash.client || "another interview"} `
          + `at ${saved.clash.when.label}.` });
      }
      return saved;
    } catch (err) {
      // Shown rather than thrown: the notes panel awaits this to decide whether
      // to close, and a rejection there would close on a save that never landed.
      setNote({ bad: true, text: err.message });
      return null;
    }
  };

  const remove = async (row) => {
    if (!window.confirm(
      `Remove the ${row.client || "interview"} on ${row.when.label}? `
      + "If it was real and fell through, mark it cancelled instead — a client who "
      + "pulled out is worth knowing about.")) return;
    try {
      await api.deleteInterview(row.id);
      await load();
    } catch (err) {
      setNote({ bad: true, text: err.message });
    }
  };

  if (!data) return <p className="muted">Loading the diary…</p>;

  const ready = form.profile_id && form.scheduled_at;
  const chosen = byId[form.profile_id];

  return (
    <section className="stack" style={{ gap: 12 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h2>{heading}</h2>
          {intro && <p className="muted" style={{ marginTop: 3 }}>{intro}</p>}
        </div>
        {canSchedule && profiles.length > 0 && (
          <button className={adding ? "ghost" : ""} onClick={() => setAdding((on) => !on)}>
            {adding ? "Never mind" : "Log an interview"}
          </button>
        )}
      </div>

      {note && <div className={note.bad ? "notice" : "notice ok"}>{note.text}</div>}

      {!canSchedule && (
        <p className="muted" style={{ maxWidth: 760 }}>
          Your BD books these — the client replied to the account they run, and one side
          holding the diary is what stops one reply being logged twice at two different
          times. Forward anything that reaches you directly and it turns up here. Saying
          how a call went, and writing the note under <b>notes</b>, is yours.
        </p>
      )}

      {canSchedule && adding && (
        <div className="card pad stack" style={{ gap: 12 }}>
          <div>
            <h3>A client wants to talk</h3>
            <p className="muted" style={{ marginTop: 3, maxWidth: 700 }}>
              The time is <b>Eastern</b>, whatever clock you are reading. Everyone who opens
              this sees the same hour, so type what you agreed with the client.
            </p>
          </div>

          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(190px,1fr))" }}>
            <div>
              <label htmlFor="iv-profile">Applying as</label>
              <select id="iv-profile" style={{ width: "100%", marginTop: 4 }}
                      value={form.profile_id}
                      onChange={(e) => setForm({ ...form, profile_id: e.target.value })}>
                {profiles.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}{p.headline ? ` · ${p.headline}` : ""}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="iv-when">Date and time · ET</label>
              <input id="iv-when" type="datetime-local" style={{ width: "100%", marginTop: 4 }}
                     value={form.scheduled_at}
                     onChange={(e) => setForm({ ...form, scheduled_at: e.target.value })} />
            </div>
            <div>
              <label htmlFor="iv-client">Client</label>
              <input id="iv-client" style={{ width: "100%", marginTop: 4 }}
                     placeholder="Northwind Digital" value={form.client}
                     onChange={(e) => setForm({ ...form, client: e.target.value })} />
            </div>
            <div>
              <label htmlFor="iv-role">Role</label>
              <input id="iv-role" style={{ width: "100%", marginTop: 4 }}
                     placeholder="RAG Pipeline Developer" value={form.role}
                     onChange={(e) => setForm({ ...form, role: e.target.value })} />
            </div>
            <div>
              <label htmlFor="iv-stage">Which round</label>
              <select id="iv-stage" style={{ width: "100%", marginTop: 4 }} value={form.stage}
                      onChange={(e) => setForm({ ...form, stage: e.target.value })}>
                <option value="screening">screening call</option>
                <option value="technical">technical round</option>
                <option value="assessment">take-home</option>
                <option value="final">final round</option>
                <option value="offer">offer talks</option>
              </select>
            </div>
            <div>
              <label htmlFor="iv-mode">How</label>
              <select id="iv-mode" style={{ width: "100%", marginTop: 4 }} value={form.mode}
                      onChange={(e) => setForm({ ...form, mode: e.target.value })}>
                <option value="video">video call</option>
                <option value="call">phone call</option>
                <option value="onsite">on site</option>
                <option value="async">written / take-home</option>
              </select>
            </div>
            <div>
              <label htmlFor="iv-mins">Minutes</label>
              <input id="iv-mins" type="number" min="5" max="600" step="5"
                     style={{ width: "100%", marginTop: 4 }} value={form.duration_minutes}
                     onChange={(e) => setForm({ ...form, duration_minutes: e.target.value })} />
            </div>
            <div style={{ gridColumn: "span 2" }}>
              <label htmlFor="iv-link">Meeting link</label>
              <input id="iv-link" style={{ width: "100%", marginTop: 4 }}
                     placeholder="https://meet.example.com/…" value={form.link}
                     onChange={(e) => setForm({ ...form, link: e.target.value })} />
            </div>
            <div style={{ gridColumn: "span 2" }}>
              <label htmlFor="iv-notes">Anything they should know</label>
              <input id="iv-notes" style={{ width: "100%", marginTop: 4 }}
                     placeholder="Wants to see the RAG project" value={form.notes}
                     onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            </div>
          </div>

          {chosen?.developer && (
            <p className="muted">
              This lands in <b>{chosen.developer}</b>&apos;s diary. They will see it on their own
              screen without anybody telling them.
            </p>
          )}
          {chosen && !chosen.developer && (
            <div className="notice">
              No developer is attached to {chosen.name}, so this interview reaches nobody
              automatically. Ask your manager to say who is behind that profile.
            </div>
          )}

          <div className="row">
            <button onClick={schedule} disabled={busy || !ready}>
              {busy ? "Saving…" : "Put it in the diary"}
            </button>
            <span className="muted">
              Nothing is emailed. It appears on their screen the next time it refreshes.
            </span>
          </div>
        </div>
      )}

      {showFunnel && (
        <>
          <Funnel data={data.funnel} awaiting={data.counts.awaiting_outcome}
                  note="Applications are all-time. Interviews are never filtered to a cycle — a reply
                        that arrives three weeks late belongs to the work that earned it." />
          <StageLadder rows={data.funnel.by_stage} />
        </>
      )}

      {data.awaiting_time?.length > 0 && (
        <div className="stack" style={{ gap: 8 }}>
          <div>
            <h3>Waiting on a time</h3>
            <p className="muted" style={{ margin: "3px 0 0", maxWidth: 760 }}>
              Replies somebody started from the job record. Each one is a client who has
              answered and is waiting to hear back, and none of them counts towards any figure
              on this screen until a time is agreed. Put one in and it becomes a real booking
              — there is no second button.
            </p>
          </div>
          <WaitingOnTime rows={data.awaiting_time} onChange={change}
                         onRemove={canSchedule ? remove : undefined}
                         suggested={data.suggested_time} />
        </div>
      )}

      {data.counts.awaiting_outcome > 0 && (
        <div className="notice">
          <b>{data.counts.awaiting_outcome} interview
          {data.counts.awaiting_outcome === 1 ? " has" : "s have"} happened without an outcome.</b>{" "}
          Say how they went below. Until somebody does, every rate on every screen here reads
          lower than the truth.
        </div>
      )}

      <div>
        <h3>Today</h3>
        <p className="muted" style={{ margin: "3px 0 8px" }}>
          {data.today.length
            ? `${data.today.length} today, Eastern time.`
            : "Nothing today."}
        </p>
        {data.today.length > 0 && (
          <InterviewRows rows={data.today} showProfile={showProfile} canBook={canSchedule}
                         onChange={change} onRemove={canSchedule ? remove : undefined} />
        )}
      </div>

      <div>
        <h3>Coming up</h3>
        <p className="muted" style={{ margin: "3px 0 8px" }}>The next fortnight.</p>
        <InterviewRows rows={data.upcoming} showProfile={showProfile} canBook={canSchedule}
                       onChange={change} onRemove={canSchedule ? remove : undefined}
                       empty="Nothing booked in the next fortnight." />
      </div>

      <div>
        <h3>What happened</h3>
        <p className="muted" style={{ margin: "3px 0 8px" }}>
          The last {Math.max(data.recent.length, 1)} that have been and gone. Recording the
          outcome is what turns a pile of applications into a number worth steering by.
        </p>
        <InterviewRows rows={data.recent} showProfile={showProfile} canBook={canSchedule}
                       onChange={change} onRemove={canSchedule ? remove : undefined}
                       empty="Nothing has happened yet." />
      </div>
    </section>
  );
}
