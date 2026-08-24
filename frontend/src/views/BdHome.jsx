import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, download, safeUrl } from "../api.js";
import EntryTable from "./EntryTable.jsx";
import Interviews from "./Interviews.jsx";
import { Availability, CopyButton, Skills } from "./widgets.jsx";

const FIELD_LABELS = {
  url: "Job link",
  title: "Job title",
  company: "Client or company",
  platform: "Platform",
  date: "Applied on",
};

export default function BdHome() {
  const [batches, setBatches] = useState([]);
  const [batchId, setBatchId] = useState(null);
  const [profiles, setProfiles] = useState([]);
  const [profileId, setProfileId] = useState(null);
  const [upload, setUpload] = useState(null);
  const [sheets, setSheets] = useState({});
  const [note, setNote] = useState(null);
  const [busy, setBusy] = useState(false);
  const [hot, setHot] = useState(false);
  const [tab, setTab] = useState("applied");   // applied | new | interviews
  const [diary, setDiary] = useState(null);   // interview counts, for the badge
  const [how, setHow] = useState("type");      // type | upload
  const fileInput = useRef(null);

  const batch = useMemo(
    () => batches.find((b) => b.id === batchId) || null,
    [batches, batchId]
  );
  const profile = useMemo(
    () => profiles.find((p) => p.id === profileId) || null,
    [profiles, profileId]
  );
  const sheet = sheets[profileId] || [];

  useEffect(() => {
    Promise.all([api.listBatches(), api.listProfiles()])
      .then(([rows, mine]) => {
        setBatches(rows);
        setProfiles(mine);
        if (rows.length) setBatchId(rows[0].id);
        if (mine.length) setProfileId(mine[0].id);
      })
      .catch((err) => setNote({ bad: true, text: err.message }));
  }, []);

  // Once a cycle is computed there is nothing left to hand in, so open on the
  // half of the screen that still has something to do.
  useEffect(() => {
    if (batch) setTab(batch.status === "computed" ? "new" : "applied");
  }, [batch?.id, batch?.status]);

  useEffect(() => {
    if (!batchId) return;
    setUpload(null);
    api.getBatch(batchId)
      .then((data) => {
        const mine = (data.uploads || []).find((u) => u.profile_id === profileId);
        if (mine) setUpload({ ...mine, fields: null });
      })
      .catch(() => {});
  }, [batchId, profileId]);

  const loadSheets = useCallback(() => {
    if (!batchId) return;
    api.mySheets(batchId)
      .then((data) => {
        const next = {};
        for (const p of data.profiles) next[p.id] = p.jobs;
        setSheets(next);
      })
      .catch(() => setSheets({}));
  }, [batchId]);

  useEffect(() => { loadSheets(); }, [loadSheets]);

  // Somebody else may put an interview in this diary at any moment — the
  // developer themselves, or a colleague who took the call. The badge is the
  // only thing on this screen that has to be right within the hour.
  useEffect(() => {
    const pull = () => api.interviews().then((d) => setDiary(d.counts)).catch(() => {});
    pull();
    const tick = setInterval(pull, 60000);
    return () => clearInterval(tick);
  }, []);

  // The server rebuilds these lists on a timer, so what is on screen goes stale
  // on its own. Pick up the new one rather than waiting for a reload.
  useEffect(() => {
    if (!batchId) return undefined;
    const tick = setInterval(() => {
      loadSheets();
      api.listBatches().then(setBatches).catch(() => {});
    }, 60000);
    return () => clearInterval(tick);
  }, [batchId, loadSheets]);

  const send = async (file) => {
    if (!file || !batchId || !profileId) return;
    setBusy(true);
    setNote(null);
    try {
      const data = await api.upload(batchId, profileId, file);
      setUpload(data);
      setNote({ text: `${data.row_count} rows read for ${data.profile}. Check the columns below.` });
    } catch (err) {
      setNote({ bad: true, text: err.message });
    } finally {
      setBusy(false);
    }
  };

  const remap = async (key, value) => {
    const mapping = { ...upload.mapping, [key]: value };
    setUpload({ ...upload, mapping });
    try {
      await api.setMapping(upload.id, mapping);
    } catch (err) {
      setNote({ bad: true, text: err.message });
    }
  };

  const mark = async (assignmentId, status) => {
    setSheets((all) => ({
      ...all,
      [profileId]: (all[profileId] || []).map((r) => (r.id === assignmentId ? { ...r, status } : r)),
    }));
    try {
      await api.setStatus(assignmentId, status);
    } catch (err) {
      setNote({ bad: true, text: err.message });
    }
  };

  const headers = upload?.headers || [];
  const done = sheet.filter((j) => j.status === "applied").length;
  const handedIn = upload?.row_count || 0;

  if (!profiles.length) {
    return (
      <div className="stack">
        <h1>Your work</h1>
        <div className="notice">
          No profile has been assigned to you yet. Your manager creates one under
          <b> People and profiles</b> — it is the name and resume your applications go out under.
        </div>
      </div>
    );
  }

  return (
    <div className="stack">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1>Your work</h1>
          <p className="muted" style={{ marginTop: 3 }}>
            Working as <b>{profile?.name}</b>{profile?.headline ? ` · ${profile.headline}` : ""}.
          </p>
        </div>
        <label>
          Cycle&nbsp;
          <select value={batchId || ""} onChange={(e) => setBatchId(Number(e.target.value))}>
            {batches.map((b) => (
              <option key={b.id} value={b.id}>{b.name} · {b.status}</option>
            ))}
          </select>
        </label>
      </div>

      {profiles.length > 1 && (
        <div className="card pad">
          <h3>Which profile are you working as?</h3>
          <div className="row" style={{ marginTop: 10 }}>
            {profiles.map((p) => (
              <button key={p.id} className={p.id === profileId ? "" : "ghost"}
                      onClick={() => setProfileId(p.id)}>
                {p.name}
                <span style={{ opacity: 0.7, fontWeight: 400 }}>
                  {p.headline ? ` · ${p.headline}` : ""}
                </span>
                {sheets[p.id]?.length ? ` (${sheets[p.id].length})` : ""}
              </button>
            ))}
          </div>
          <p className="muted" style={{ marginTop: 9 }}>
            Each profile keeps its own history. What {profile?.name} has applied to has no
            bearing on what your other profiles are offered.
          </p>
        </div>
      )}

      {/* What the client is actually being handed. The resume link is the thing
          a BD needs three seconds before they need anything else on this page. */}
      {profile && (
        <section className="card pad stack" style={{ gap: 10 }}>
          <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <h3>Who you are applying as</h3>
              <p className="muted" style={{ marginTop: 3, maxWidth: 680 }}>
                {profile.developer
                  ? <>Behind <b>{profile.name}</b> is <b>{profile.developer}</b>. They sit the
                      interview, so anything you book lands on their screen.</>
                  : <>Nobody is attached to <b>{profile.name}</b> yet, so an interview booked
                      against it reaches no one. Ask your manager to say who is behind it.</>}
              </p>
            </div>
            {profile.developer && <Availability value={profile.availability} />}
          </div>

          <div className="row" style={{ gap: 20 }}>
            <span className="row" style={{ gap: 7 }}>
              <span className="muted">email</span>
              <span className="mono" style={{ fontSize: 12 }}>{profile.email || "—"}</span>
              <CopyButton value={profile.email} />
            </span>
            <span className="row" style={{ gap: 7 }}>
              <span className="muted">resume</span>
              {safeUrl(profile.resume_url) ? (
                <>
                  <a href={safeUrl(profile.resume_url)} target="_blank" rel="noreferrer noopener">open</a>
                  <CopyButton value={profile.resume_url} label="copy link" />
                </>
              ) : (
                <span style={{ color: "var(--brick)", fontSize: 12 }}>
                  not set{profile.developer ? ` — ${profile.developer} adds it on their own screen` : ""}
                </span>
              )}
            </span>
            {profile.rate && (
              <span className="row" style={{ gap: 7 }}>
                <span className="muted">rate</span>
                <span style={{ fontSize: 12 }}>{profile.rate}</span>
              </span>
            )}
            {profile.timezone && (
              <span className="row" style={{ gap: 7 }}>
                <span className="muted">hours</span>
                <span style={{ fontSize: 12 }}>{profile.timezone}</span>
              </span>
            )}
          </div>

          {profile.skills && <Skills value={profile.skills} />}
          {profile.bio && <p className="muted" style={{ maxWidth: 760 }}>{profile.bio}</p>}

          {profile.availability === "booked" && (
            <div className="notice">
              <b>{profile.developer || profile.name} is booked up.</b> Applying under this
              profile now wins interviews nobody can sit. Worth checking before you send more.
            </div>
          )}
        </section>
      )}

      {diary?.today > 0 && (
        <div className="notice gate">
          <b>{diary.today} interview{diary.today === 1 ? "" : "s"} today</b> against the profiles
          you run.{" "}
          <button className="link" onClick={() => setTab("interviews")}>Open the diary</button>
        </div>
      )}

      {diary?.awaiting_outcome > 0 && (
        <div className="notice">
          <b>{diary.awaiting_outcome} interview
          {diary.awaiting_outcome === 1 ? " has" : "s have"} happened with no outcome recorded.</b>{" "}
          Until somebody says how they went, nothing here can tell you whether the applications
          are working.{" "}
          <button className="link" onClick={() => setTab("interviews")}>Record them</button>
        </div>
      )}

      {note && <div className={note.bad ? "notice" : "notice ok"}>{note.text}</div>}
      {!batches.length && <div className="notice">No cycle is open yet. Your manager needs to start one.</div>}

      {batch && (
        <>
          {/* The two things a BD ever does here: report what they worked, and
              pick up what is next. */}
          <div className="row" style={{ gap: 8 }}>
            <button className={tab === "applied" ? "" : "ghost"} onClick={() => setTab("applied")}>
              Jobs I applied to{handedIn ? ` (${handedIn})` : ""}
            </button>
            <button className={tab === "new" ? "" : "ghost"} onClick={() => setTab("new")}>
              New jobs for {profile?.name}{sheet.length ? ` (${sheet.length})` : ""}
            </button>
            <button className={tab === "interviews" ? "" : "ghost"} onClick={() => setTab("interviews")}>
              Interviews{diary?.today ? ` (${diary.today} today)`
                : diary?.scheduled ? ` (${diary.scheduled})` : ""}
            </button>
          </div>

          {tab === "interviews" && (
            <Interviews
              profiles={profiles}
              heading="Interviews"
              intro="Every reply that turned into a conversation, for the profiles you run. Logging
                     one puts it on the developer's screen — nothing is emailed, and nobody has to
                     be told."
              showFunnel
            />
          )}

          {tab === "applied" && (
            <section className="stack" style={{ gap: 10 }}>
              <div>
                <h2>Jobs {profile?.name} applied to</h2>
                <p className="muted" style={{ marginTop: 3 }}>
                  Hand these in so nobody is sent something this profile has already used.
                </p>
              </div>

              {batch.status !== "open" ? (
                <div className="notice">
                  This cycle is closed — your manager has already built the lists. Anything
                  new goes into the next one.
                </div>
              ) : (
                <>
                  <div className="row" style={{ gap: 8 }}>
                    <button className={how === "type" ? "" : "ghost"} onClick={() => setHow("type")}>
                      Add manually
                    </button>
                    <button className={how === "upload" ? "" : "ghost"} onClick={() => setHow("upload")}>
                      Upload a sheet
                    </button>
                    <span className="muted">
                      {how === "type"
                        ? "Add jobs one row at a time as you apply."
                        : "Already keep a spreadsheet? Drop the whole thing in."}
                    </span>
                  </div>

                  {how === "type" && (
                    <EntryTable
                      batchId={batchId}
                      profileId={profileId}
                      profileName={profile?.name}
                      onSaved={(result) => setUpload((current) => (
                        current
                          ? { ...current, row_count: result.row_count }
                          : { row_count: result.row_count, mapping: {}, headers: [] }
                      ))}
                    />
                  )}

                  {how === "upload" && (
                    <div
                      className={hot ? "drop hot" : "drop"}
                      onClick={() => fileInput.current?.click()}
                      onDragOver={(e) => { e.preventDefault(); setHot(true); }}
                      onDragLeave={() => setHot(false)}
                      onDrop={(e) => { e.preventDefault(); setHot(false); send(e.dataTransfer.files[0]); }}
                    >
                      <div style={{ fontFamily: "var(--display)", fontWeight: 500, fontSize: 15 }}>
                        {busy ? "Reading the sheet…" : `Drop ${profile?.name}'s sheet here, or click to choose`}
                      </div>
                      <div className="muted" style={{ marginTop: 5 }}>
                        .xlsx, .xls or .csv — re-uploading replaces what you sent for this profile.
                      </div>
                      <input ref={fileInput} type="file" accept=".xlsx,.xls,.csv,.tsv" hidden
                             onChange={(e) => send(e.target.files[0])} />
                    </div>
                  )}

                  {how === "upload" && upload && headers.length > 0 && (
                    <div className="card pad stack" style={{ gap: 12 }}>
                      <div>
                        <h3>Columns we found</h3>
                        <p className="muted" style={{ marginTop: 3 }}>
                          The job link matters most — it is how the same posting is recognised
                          across everyone's sheets. If the sheet has no links, make sure the
                          title and client are both set.
                        </p>
                      </div>
                      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(190px,1fr))" }}>
                        {Object.keys(FIELD_LABELS).map((key) => (
                          <div key={key}>
                            <label htmlFor={`map-${key}`}>{FIELD_LABELS[key]}</label>
                            <select id={`map-${key}`} value={upload.mapping?.[key] || ""}
                                    style={{ width: "100%", marginTop: 4,
                                             borderColor: key === "url" && !upload.mapping?.url ? "var(--brick)" : undefined }}
                                    onChange={(e) => remap(key, e.target.value)}>
                              <option value="">— not in my sheet —</option>
                              {headers.map((h) => <option key={h} value={h}>{h}</option>)}
                            </select>
                          </div>
                        ))}
                      </div>
                      {!upload.mapping?.url && (
                        <div className="notice">
                          No job link column is set. Matching will fall back to client plus title,
                          which is less exact.
                        </div>
                      )}
                      <div className="row">
                        <span className="pill on">{upload.row_count} rows handed in</span>
                        <button className="link" onClick={async () => {
                          await api.deleteUpload(upload.id);
                          setUpload(null);
                          setNote({ text: "That sheet was removed. Upload a different one when ready." });
                        }}>Remove this sheet</button>
                      </div>
                    </div>
                  )}
                </>
              )}
            </section>
          )}

          {tab === "new" && (
            <section className="stack" style={{ gap: 10 }}>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <div>
                  <h2>New jobs for {profile?.name}</h2>
                  <p className="muted" style={{ marginTop: 3 }}>
                    {sheet.length
                      ? `${sheet.length} jobs ${profile?.name} has never applied to, ${done} marked applied.`
                      : "Nothing yet — your manager builds the lists once everyone has handed in."}
                  </p>
                </div>
                {sheet.length > 0 && (
                  <button className="go" onClick={() =>
                    download(`/batches/${batchId}/profiles/${profileId}/sheet.xlsx`, "new-jobs.xlsx")
                      .catch((err) => setNote({ bad: true, text: err.message }))}>
                    Download as Excel
                  </button>
                )}
              </div>

              {sheet.length === 0 ? (
                <div className="notice">
                  {batch.status !== "open"
                    ? "Nothing was dispatched to this profile in this cycle."
                    : batch.auto_build_minutes
                      ? `This cycle is still open. The lists rebuild every ${batch.auto_build_minutes} minutes once at least two profiles have handed in — yours will appear here on its own.`
                      : "This cycle is still open. Your jobs appear here once your manager builds the lists."}
                </div>
              ) : (
                <>
                  <div className="card scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Job</th><th>Client</th><th>Platform</th><th>Link</th><th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sheet.map((job) => (
                          <tr key={job.id} style={{ opacity: job.status === "skipped" ? 0.5 : 1 }}>
                            <td className="truncate">{job.title || "—"}</td>
                            <td>{job.company || "—"}</td>
                            <td className="muted">{job.platform || "—"}</td>
                            <td className="truncate">
                              {safeUrl(job.url)
                                ? <a href={safeUrl(job.url)} target="_blank" rel="noreferrer noopener">open</a>
                                : <span className="muted">no link</span>}
                            </td>
                            <td>
                              <select value={job.status} onChange={(e) => mark(job.id, e.target.value)}>
                                <option value="pending">to do</option>
                                <option value="applied">applied</option>
                                <option value="skipped">skipped</option>
                              </select>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="muted">
                    Anything left as <b>to do</b> comes back next cycle. Marking a job
                    <b> applied</b> or <b> skipped</b> retires it from this profile for good.
                    {batch.status === "open" && batch.auto_build_minutes > 0 && (
                      <> This list refreshes every {batch.auto_build_minutes} minutes as
                      colleagues log their work, so jobs may drop off — anything you have already
                      marked stays put.</>
                    )}
                  </p>
                </>
              )}
            </section>
          )}
        </>
      )}
    </div>
  );
}
