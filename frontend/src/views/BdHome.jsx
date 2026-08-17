import React, { useEffect, useMemo, useRef, useState } from "react";
import { api, download, safeUrl } from "../api.js";

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

  // Reload uploads and lists whenever the cycle or the chosen profile changes.
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

  useEffect(() => {
    if (!batchId) return;
    api.mySheets(batchId)
      .then((data) => {
        const next = {};
        for (const p of data.profiles) next[p.id] = p.jobs;
        setSheets(next);
      })
      .catch(() => setSheets({}));
  }, [batchId]);

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
            Hand in what each profile applied to, then pick up the jobs it has not tried yet.
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

      {profiles.length > 1 ? (
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
      ) : (
        <p className="muted">
          Working as <b>{profile?.name}</b>{profile?.headline ? ` · ${profile.headline}` : ""}.
        </p>
      )}

      {note && <div className={note.bad ? "notice" : "notice ok"}>{note.text}</div>}
      {!batches.length && <div className="notice">No cycle is open yet. Your manager needs to start one.</div>}

      {batch && (
        <section className="stack" style={{ gap: 10 }}>
          <h2>1 · Hand in what {profile?.name} applied to</h2>
          {batch.status !== "open" ? (
            <div className="muted">This cycle is closed. Uploads are only accepted while a cycle is open.</div>
          ) : (
            <>
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

              {upload && headers.length > 0 && (
                <div className="card pad stack" style={{ gap: 12 }}>
                  <div>
                    <h3>Columns we found</h3>
                    <p className="muted" style={{ marginTop: 3 }}>
                      The job link matters most — it is how the same posting is recognised across
                      everyone's sheets. If the sheet has no links, make sure the title and client
                      are both set.
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

      {batch && (
        <section className="stack" style={{ gap: 10 }}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <div>
              <h2>2 · New jobs for {profile?.name}</h2>
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

          {sheet.length > 0 && (
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
          )}
          {sheet.length > 0 && (
            <p className="muted">
              Anything left as <b>to do</b> comes back next cycle. Marking a job
              <b> applied</b> or <b> skipped</b> retires it from this profile for good.
            </p>
          )}
        </section>
      )}
    </div>
  );
}
