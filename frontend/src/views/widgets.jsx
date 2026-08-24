import React from "react";

/** "just now", "4 minutes ago", "2 hours ago" — enough to trust the numbers.
 *
 * Stored timestamps are UTC. SQLite hands them back with no marker at all, so
 * the Z goes on here or the browser reads them as local time and everything
 * looks hours old.
 */
export function sinceText(iso) {
  if (!iso) return "never";
  const then = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  const seconds = Math.max(0, Math.round((Date.now() - then.getTime()) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} day${days === 1 ? "" : "s"} ago`;
  return then.toLocaleDateString();
}

/** A row of headline numbers. `tone` tints the figure, not the label. */
export function Tiles({ items }) {
  return (
    <div className="stats">
      {items.filter(Boolean).map((item) => (
        <div className="stat" key={item.label} title={item.hint || undefined}>
          <b style={item.tone ? { color: `var(--${item.tone})` } : undefined}>{item.value}</b>
          <span>{item.label}</span>
          {item.foot && <span className="foot">{item.foot}</span>}
        </div>
      ))}
    </div>
  );
}

/** Jobs logged per day, as bars.
 *
 * Bars rather than a line: these are counts of discrete days, and a line
 * between two of them implies a value at half past Tuesday that does not exist.
 * The server always sends a fixed number of days, zeros included, so a quiet
 * week keeps the shape instead of stretching two bars across the whole strip.
 */
export function Sparkline({ series, height = 46, label = "jobs logged" }) {
  if (!series?.length) return null;
  const peak = Math.max(1, ...series.map((d) => d.count));
  const step = 8;
  const width = series.length * step;
  const total = series.reduce((sum, d) => sum + d.count, 0);

  return (
    <div className="spark-wrap">
      <svg className="spark" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none"
           role="img" aria-label={`${total} ${label} over the last ${series.length} days`}>
        {series.map((day, i) => {
          const tall = day.count ? Math.max(2, (day.count / peak) * (height - 2)) : 1;
          return (
            <rect key={day.day} x={i * step + 1} y={height - tall}
                  width={step - 2} height={tall}
                  fill={day.count ? "var(--petrol)" : "var(--rule)"}>
              <title>{`${day.count} on ${day.day}`}</title>
            </rect>
          );
        })}
      </svg>
      <div className="spark-axis muted">
        <span>{series[0].day.slice(5)}</span>
        <span>peak {peak}/day</span>
        <span>today</span>
      </div>
    </div>
  );
}

/** How a list was worked: applied, skipped, still to do. */
export function Progress({ applied = 0, skipped = 0, pending = 0 }) {
  const total = applied + skipped + pending;
  if (!total) {
    return <div className="bar" title="Nothing on this list yet"><i style={{ width: "100%" }} /></div>;
  }
  const share = (n) => `${(n / total) * 100}%`;
  return (
    <div className="bar" title={`${applied} applied · ${skipped} skipped · ${pending} to do`}>
      <i style={{ width: share(applied), background: "var(--pine)" }} />
      <i style={{ width: share(skipped), background: "var(--slate)" }} />
      <i style={{ width: share(pending), background: "var(--rule)" }} />
    </div>
  );
}

export function CyclePicker({ batches, value, onChange, label = "Cycle" }) {
  if (!batches?.length) return null;
  return (
    <label>
      {label}&nbsp;
      <select value={value || ""} onChange={(e) => onChange(Number(e.target.value))}>
        {batches.map((b) => (
          <option key={b.id} value={b.id}>
            {b.name} · {b.status === "open" ? "open" : "closed"}
          </option>
        ))}
      </select>
    </label>
  );
}

/** Every profile side by side.
 *
 * `onOpen` is only ever passed for a manager: a BD may see the totals on this
 * board but not click through into a colleague's record, and the server refuses
 * that request too.
 */
export function TeamBoard({ rows, onOpen, highlight = [] }) {
  const mine = new Set(highlight);
  return (
    <div className="card scroll">
      <table className="board">
        <thead>
          <tr>
            <th style={{ width: 34 }}>#</th>
            <th>Profile</th>
            <th>Run by</th>
            <th className="num">Logged</th>
            <th className="num" title="Jobs this profile logged that a colleague had already found">
              Also found
            </th>
            <th className="num">List</th>
            <th className="num">Applied</th>
            <th style={{ width: 150 }}>Worked through</th>
            <th>Last logged</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.profile_id}
                className={mine.has(row.profile_id) ? "is-mine" : undefined}
                style={onOpen ? { cursor: "pointer" } : undefined}
                onClick={onOpen ? () => onOpen(row.profile_id) : undefined}>
              <td className="mono muted num">{row.rank ?? "—"}</td>
              <td>
                <b>{row.name}</b>
                {row.headline && <span className="muted"> · {row.headline}</span>}
                {row.shared === false && <span className="pill off" style={{ marginLeft: 6 }}>off the board</span>}
              </td>
              <td className="muted">{row.person || "nobody"}</td>
              <td className="mono num">{row.logged}</td>
              <td className="mono num" style={{ color: row.duplicates ? "var(--brick)" : undefined }}>
                {row.duplicates}
              </td>
              <td className="mono num">{row.assigned}</td>
              <td className="mono num"><b>{row.applied}</b></td>
              <td>
                <Progress applied={row.applied} skipped={row.skipped} pending={row.pending} />
                <span className="muted mono" style={{ fontSize: 11 }}>{row.done_pct}%</span>
              </td>
              <td className="muted">{sinceText(row.last_logged)}</td>
            </tr>
          ))}
          {!rows.length && (
            <tr><td colSpan={9} className="muted">No profiles to show yet.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

/** The strip of numbers behind one profile, used on both dashboards. */
export function ProfileCard({ row, children, onOpen }) {
  const left = row.pending;
  return (
    <div className="card pad stack" style={{ gap: 10 }}>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <div style={{ fontFamily: "var(--display)", fontWeight: 600, fontSize: 15 }}>{row.name}</div>
          <div className="muted">{row.headline || "—"}{row.person ? ` · ${row.person}` : ""}</div>
        </div>
        {onOpen && <button className="ghost" onClick={onOpen}>Open</button>}
      </div>

      <div className="figures">
        <div><b className="mono">{row.logged}</b><span>logged</span></div>
        <div><b className="mono">{row.assigned}</b><span>on the list</span></div>
        <div><b className="mono">{row.applied}</b><span>applied</span></div>
        <div><b className="mono" style={{ color: left ? "var(--brick)" : "var(--pine)" }}>{left}</b>
             <span>left to do</span></div>
      </div>

      <Progress applied={row.applied} skipped={row.skipped} pending={row.pending} />
      <div className="row muted" style={{ justifyContent: "space-between", fontSize: 12 }}>
        <span>{row.done_pct}% worked through</span>
        <span>{row.all_time} applications all time</span>
      </div>
      {children}
    </div>
  );
}

/* --------------------------------------------------------------------------
   Developers, and what the applications turned into.

   Everything above this line counts effort. Everything below it counts what
   the effort produced, which is a different question and needs its own shapes.
   -------------------------------------------------------------------------- */

export const MODE_LABELS = {
  video: "video call",
  call: "phone call",
  onsite: "on site",
  async: "written",
};

export const AVAILABILITY_LABELS = {
  open: "taking work",
  limited: "limited",
  booked: "booked up",
};

/** Only ever put an http(s) link in an href.
 *
 * The same rule as api.safeUrl, kept here so a widget has no reason to reach
 * into the api module. Meeting links and resume links are typed by people and
 * land in an href on somebody else's screen.
 */
function safeLink(value) {
  return /^https?:\/\//i.test(value || "") ? value : "";
}

/** Whether the developer behind a profile could actually start.
 *
 * A BD reads this before applying under a profile. Winning an interview for
 * somebody who cannot take the work costs the client goodwill as well as the
 * developer an afternoon.
 */
export function Availability({ value, small = false }) {
  const state = value || "open";
  const tone = state === "open" ? "on" : state === "booked" ? "off" : "";
  return (
    <span className={`pill ${tone}`} style={small ? { fontSize: 10 } : undefined}>
      {AVAILABILITY_LABELS[state] || state}
    </span>
  );
}

/** A comma-separated skills field, as something readable. */
export function Skills({ value, limit = 8 }) {
  const parts = (value || "").split(",").map((s) => s.trim()).filter(Boolean);
  if (!parts.length) return <span className="muted">no skills listed</span>;
  return (
    <span className="row" style={{ gap: 5 }}>
      {parts.slice(0, limit).map((skill) => (
        <span className="pill" key={skill}>{skill}</span>
      ))}
      {parts.length > limit && <span className="muted">+{parts.length - limit} more</span>}
    </span>
  );
}

/** Put a value on the clipboard.
 *
 * The clipboard API does not exist on plain http, so a failure is swallowed:
 * the value is on the screen either way, and an error about copying an email
 * address helps nobody.
 */
export function CopyButton({ value, label = "copy" }) {
  const [done, setDone] = React.useState(false);
  if (!value) return null;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setDone(true);
      setTimeout(() => setDone(false), 1400);
    } catch {
      /* clipboard blocked — nothing useful to say about it */
    }
  };
  return <button className="link" onClick={copy}>{done ? "copied" : label}</button>;
}

/** Applications in, interviews out, offers at the end of it.
 *
 * Drawn as steps rather than a funnel shape on purpose. A real funnel encodes
 * each ratio twice — once in the number, once in the width — and the width is
 * always the less accurate of the two. The rates are said in words underneath
 * instead, where they can be qualified.
 */
export function Funnel({ data, note = "", awaiting = 0 }) {
  if (!data) return null;
  const steps = [
    { label: "applications sent", value: data.applications,
      foot: data.scoped_to_cycle ? "this cycle" : "all time" },
    { label: "interviews", value: data.interviews,
      foot: data.applications ? `${data.interview_rate}% of applications` : "—" },
    { label: "offers", value: data.offers,
      foot: data.interviews ? `${data.offer_rate}% of interviews` : "—" },
    { label: "hired", value: data.hired, foot: data.hired ? "work won" : "—" },
  ];
  return (
    <div className="card pad stack" style={{ gap: 10 }}>
      <div className="funnel">
        {steps.map((step, i) => (
          <React.Fragment key={step.label}>
            {i > 0 && <span className="funnel-arrow" aria-hidden="true">→</span>}
            <div className="funnel-step">
              <b className="mono">{step.value}</b>
              <span>{step.label}</span>
              <span className="foot">{step.foot}</span>
            </div>
          </React.Fragment>
        ))}
      </div>
      {note && <p className="muted">{note}</p>}
      {awaiting > 0 && (
        <p className="muted">
          {awaiting} interview{awaiting === 1 ? " has" : "s have"} been and gone without
          anybody saying how it went, so these rates are understated until they do.
        </p>
      )}
    </div>
  );
}

/** The next interview still ahead, sized to be read before anything else. */
export function NextInterview({ row, onOpen, openLabel = "All interviews" }) {
  if (!row) return null;
  return (
    <section className="card pad row headline" style={{ justifyContent: "space-between" }}>
      <div>
        <div className="mono headline-figure" style={{ fontSize: 32 }}>{row.when.time}</div>
        <div>
          <b style={{ fontFamily: "var(--display)", fontSize: 15 }}>
            {row.is_today ? "Today" : row.when.label} · {row.client || "a client"}
          </b>
          <p className="muted" style={{ marginTop: 2 }}>
            {row.role || "role not recorded"} · applying as <b>{row.profile}</b> ·{" "}
            {MODE_LABELS[row.mode] || row.mode} · {row.duration_minutes} min · Eastern time
          </p>
        </div>
      </div>
      <div className="row">
        {safeLink(row.link) && (
          <a className="btn go" href={safeLink(row.link)} target="_blank" rel="noreferrer noopener">
            Join
          </a>
        )}
        {onOpen && <button className="ghost" onClick={onOpen}>{openLabel}</button>}
      </div>
    </section>
  );
}

/** The rungs, in order, as a person would say them.
 *
 * Ordered because the order is the product: a screening call and a final round
 * are not the same event, and a team that cannot tell them apart cannot see
 * where its conversations die. Kept here rather than in each screen so the
 * words are the same wherever a stage is shown.
 */
export const STAGE_LABELS = {
  screening: "screening call",
  technical: "technical round",
  assessment: "take-home",
  final: "final round",
  offer: "offer talks",
};


/** Interviews as a table.
 *
 * Two people read this and they can do different things to it. `canBook` is
 * the BD or the manager: they agreed the time with the client, so the status,
 * the outcome and the row itself are theirs to change. Without it — a
 * developer — the booking is read-only and the only thing they can write is
 * the half nobody else can answer: what happened on the call.
 *
 * Leave `onChange` off entirely for a screen that only reads.
 */
export function InterviewRows({ rows, showProfile = true, onChange, onRemove,
                               canBook = true, empty = "Nothing scheduled." }) {
  const [open, setOpen] = React.useState(null);
  if (!rows?.length) return <div className="card pad muted">{empty}</div>;
  const columns = showProfile ? 8 : 7;
  return (
    <div className="card scroll">
      <table className="board">
        <thead>
          <tr>
            <th style={{ width: 128 }}>When · ET</th>
            {showProfile && <th>Applied as</th>}
            <th>Client</th>
            <th>Role</th>
            <th>How</th>
            <th style={{ width: 130 }}>Round</th>
            <th style={{ width: 200 }}>How it went</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <React.Fragment key={row.id}>
              <tr style={{ opacity: row.status === "cancelled" ? 0.5 : 1 }}>
                <td>
                  <b className="mono">{row.when.time}</b>
                  <div className="muted" style={{ fontSize: 11 }}>
                    {row.when.label.split(" · ")[0]}
                  </div>
                </td>
                {showProfile && (
                  <td>
                    <b>{row.profile}</b>
                    {row.developer && (
                      <div className="muted" style={{ fontSize: 11 }}>{row.developer}</div>
                    )}
                  </td>
                )}
                <td>{row.client || <span className="muted">—</span>}</td>
                <td className="truncate">{row.role || <span className="muted">—</span>}</td>
                <td className="muted">
                  {MODE_LABELS[row.mode] || row.mode}
                  <div style={{ fontSize: 11 }}>{row.duration_minutes} min</div>
                </td>
                <td>
                  {onChange ? (
                    <select value={row.stage || "screening"}
                            onChange={(e) => onChange(row.id, { stage: e.target.value })}>
                      {Object.entries(STAGE_LABELS).map(([key, label]) => (
                        <option key={key} value={key}>{label}</option>
                      ))}
                    </select>
                  ) : (
                    <span className="muted">
                      {STAGE_LABELS[row.stage] || row.stage || "—"}
                    </span>
                  )}
                </td>
                <td>
                  {onChange ? (
                    <div className="row" style={{ gap: 6, flexWrap: "nowrap" }}>
                      <select value={row.status}
                              onChange={(e) => onChange(row.id, { status: e.target.value })}>
                        <option value="scheduled">scheduled</option>
                        <option value="done">happened</option>
                        <option value="no_show">no show</option>
                        <option value="cancelled">cancelled</option>
                      </select>
                      {(row.is_past || row.status === "done") && row.status !== "cancelled" && (
                        <select value={row.outcome}
                                onChange={(e) => onChange(row.id, { outcome: e.target.value })}>
                          <option value="pending">not said yet</option>
                          <option value="passed">next round</option>
                          <option value="offer">offer</option>
                          <option value="hired">hired</option>
                          <option value="rejected">no</option>
                        </select>
                      )}
                    </div>
                  ) : (
                    <span className={row.outcome === "rejected" ? "pill off"
                      : ["offer", "hired", "passed"].includes(row.outcome) ? "pill on" : "pill"}>
                      {row.status === "scheduled" ? "scheduled" : row.outcome}
                    </span>
                  )}
                  {row.awaiting_outcome && (
                    <div style={{ fontSize: 11, color: "var(--brick)" }}>
                      it happened — nobody has said how it went
                    </div>
                  )}
                  {row.reported_by && (
                    <div className="muted" style={{ fontSize: 11 }}>
                      {row.reported_by} reported it{row.reported_at ? ` · ${row.reported_at}` : ""}
                    </div>
                  )}
                </td>
                <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                  {safeLink(row.link) && (
                    <a href={safeLink(row.link)} target="_blank" rel="noreferrer noopener">open</a>
                  )}
                  <button className="link"
                          onClick={() => setOpen(open === row.id ? null : row.id)}>
                    {open === row.id ? "close" : row.debrief ? "notes ✓" : "notes"}
                  </button>
                  {onRemove && <button className="link" onClick={() => onRemove(row)}>remove</button>}
                </td>
              </tr>
              {open === row.id && (
                <tr>
                  <td colSpan={columns}>
                    <InterviewNotes row={row} canBook={canBook} onChange={onChange}
                                    onClose={() => setOpen(null)} />
                  </td>
                </tr>
              )}
            </React.Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** The two halves of an interview that are prose rather than a dropdown.
 *
 * The brief is the BD's, written when they booked it. The debrief is the
 * developer's, written after the call. Separate fields on purpose: one typed
 * over the other loses what the client actually asked for, and there is no
 * second copy of that anywhere.
 *
 * Both sides may write the debrief — a BD who took it over the phone should
 * not have to wait for the developer to sign in — but only the BD may touch
 * the brief, because only they were on the thread with the client.
 */
function InterviewNotes({ row, canBook, onChange, onClose }) {
  const [draft, setDraft] = React.useState(row.debrief || "");
  const [saving, setSaving] = React.useState(false);
  const dirty = draft.trim() !== (row.debrief || "").trim();

  const save = async () => {
    setSaving(true);
    try {
      await onChange(row.id, { debrief: draft.trim() });
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="stack" style={{ gap: 10, padding: "10px 2px" }}>
      <div>
        <label>What the BD wrote when they booked it</label>
        <p className="muted" style={{ marginTop: 3, maxWidth: 720 }}>
          {row.notes || "Nothing was written down."}
        </p>
      </div>

      <div>
        <label htmlFor={`debrief-${row.id}`}>How the call went</label>
        <p className="muted" style={{ margin: "3px 0 5px", maxWidth: 720 }}>
          {canBook
            ? "Whoever was in the room usually writes this. It shows on their screen and yours."
            : "You were on the call, so this is the part only you can answer. It reaches your BD the moment you save it — nothing is emailed."}
        </p>
        {onChange ? (
          <textarea id={`debrief-${row.id}`} rows={3} style={{ width: "100%" }}
                    placeholder="Went well. They are sending a take-home by Friday."
                    value={draft} onChange={(e) => setDraft(e.target.value)} />
        ) : (
          <p className="muted">{row.debrief || "Nothing recorded yet."}</p>
        )}
      </div>

      {onChange && (
        <div className="row" style={{ gap: 10 }}>
          <button onClick={save} disabled={saving || !dirty}>
            {saving ? "Saving…" : "Save the note"}
          </button>
          <button className="ghost" onClick={onClose}>Close</button>
          <span className="muted">
            {row.reported_by
              ? `Last reported by ${row.reported_by}${row.reported_at ? ` · ${row.reported_at}` : ""}.`
              : "Nobody has reported on this one yet."}
          </span>
        </div>
      )}
    </div>
  );
}

/** Replies with no time on them yet.
 *
 * Its own table rather than a row in the diary, because these have no time to
 * be sorted by and nothing to turn up to. What they need is one field — the
 * time — and putting it in is what turns the row into a real booking. There is
 * deliberately no confirm step after it: agreeing the time *is* the
 * confirmation, and a second button is one somebody forgets, leaving a real
 * interview counted nowhere.
 */
export function WaitingOnTime({ rows, onChange, onRemove, suggested }) {
  const [draft, setDraft] = React.useState({});
  if (!rows?.length) return null;

  const put = async (row) => {
    const when = draft[row.id] || suggested;
    if (!when) return;
    await onChange(row.id, { scheduled_at: when });
    setDraft((all) => {
      const next = { ...all };
      delete next[row.id];
      return next;
    });
  };

  return (
    <div className="card scroll">
      <table className="board">
        <thead>
          <tr>
            <th>Client</th>
            <th>Role</th>
            <th>Applied as</th>
            <th style={{ width: 130 }}>Round</th>
            <th style={{ width: 230 }}>Time · ET</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>{row.client || <span className="muted">—</span>}</td>
              <td className="truncate" style={{ maxWidth: 260 }}>
                {row.role || <span className="muted">—</span>}
                {row.job && safeLink(row.job.description_url) && (
                  <div style={{ fontSize: 11 }}>
                    <a href={safeLink(row.job.description_url)} target="_blank"
                       rel="noreferrer noopener">the posting</a>
                  </div>
                )}
              </td>
              <td>
                <b>{row.profile}</b>
                {row.developer && (
                  <div className="muted" style={{ fontSize: 11 }}>{row.developer}</div>
                )}
              </td>
              <td>
                <select value={row.stage || "screening"}
                        onChange={(e) => onChange(row.id, { stage: e.target.value })}>
                  {Object.entries(STAGE_LABELS).map(([key, label]) => (
                    <option key={key} value={key}>{label}</option>
                  ))}
                </select>
              </td>
              <td>
                <input type="datetime-local" style={{ width: "100%" }}
                       value={draft[row.id] ?? suggested ?? ""}
                       onChange={(e) => setDraft((all) => ({ ...all, [row.id]: e.target.value }))} />
              </td>
              <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                <button onClick={() => put(row)}>Book it</button>
                {onRemove && <button className="link" onClick={() => onRemove(row)}>remove</button>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


/** How many conversations reached each rung, and how many died there.
 *
 * The thing a single interviews-to-offers percentage cannot show. A team losing
 * everybody at the technical round has a tooling problem; one losing them at
 * the final round has a rate or an availability problem. Both look identical in
 * one number, and they call for opposite fixes.
 */
export function StageLadder({ rows }) {
  if (!rows?.length) return null;
  const widest = Math.max(...rows.map((row) => row.reached), 1);
  if (!rows.some((row) => row.reached)) return null;

  return (
    <section className="card pad stack" style={{ gap: 10 }}>
      <div>
        <h3>Where the conversations get to</h3>
        <p className="muted" style={{ marginTop: 3, maxWidth: 760 }}>
          Reached each round, and what happened there. Cleared went on to the next one; lost
          ended there. The two do not add up to the total, because the rest are still open.
        </p>
      </div>
      <div className="stack" style={{ gap: 7 }}>
        {rows.map((row) => (
          <div key={row.stage} className="row" style={{ gap: 10, alignItems: "center" }}>
            <span style={{ minWidth: 110, fontSize: 12 }}>
              {STAGE_LABELS[row.stage] || row.stage}
            </span>
            <span className="mono" style={{ minWidth: 28, textAlign: "right" }}>
              {row.reached}
            </span>
            <span style={{ flex: 1, display: "flex", height: 12, gap: 2 }}>
              <span style={{
                width: `${(row.cleared / widest) * 100}%`,
                background: "var(--pine)", borderRadius: 2,
              }} title={`${row.cleared} went on`} />
              <span style={{
                width: `${(row.lost / widest) * 100}%`,
                background: "var(--brick)", borderRadius: 2,
              }} title={`${row.lost} ended here`} />
              <span style={{
                width: `${((row.reached - row.cleared - row.lost) / widest) * 100}%`,
                background: "var(--line, #d8d3c8)", borderRadius: 2,
              }} title={`${row.reached - row.cleared - row.lost} still open`} />
            </span>
            <span className="muted" style={{ minWidth: 96, fontSize: 11, textAlign: "right" }}>
              {row.reached ? `${row.rate}% went on` : "—"}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}


/** Every developer, and whether they are free. The manager's version. */
export function DeveloperBoard({ rows, onOpen }) {
  return (
    <div className="card scroll">
      <table className="board">
        <thead>
          <tr>
            <th>Developer</th>
            <th>Applied as</th>
            <th>Availability</th>
            <th className="num">Today</th>
            <th className="num">This week</th>
            <th className="num" title="Interviews that have happened with no outcome recorded">
              Unreported
            </th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.user_id}>
              <td>
                <b>{row.name}</b>
                <div className="muted mono" style={{ fontSize: 11 }}>{row.email}</div>
              </td>
              <td>
                {row.profiles.length
                  ? (
                    <span className="row" style={{ gap: 5 }}>
                      {row.profiles.map((p) => <span className="pill on" key={p.id}>{p.name}</span>)}
                    </span>
                  )
                  : <span className="muted">no profile attached — they see an empty screen</span>}
              </td>
              <td>{row.runs ? <Availability value={row.availability} /> : <span className="muted">—</span>}</td>
              <td className="mono num" style={{ color: row.today ? "var(--petrol)" : undefined }}>
                {row.today}
              </td>
              <td className="mono num">{row.week}</td>
              <td className="mono num" style={{ color: row.awaiting_outcome ? "var(--brick)" : undefined }}>
                {row.awaiting_outcome}
              </td>
              <td style={{ textAlign: "right" }}>
                {onOpen && (
                  <button className="ghost" style={{ padding: "5px 9px", fontSize: 12 }}
                          onClick={() => onOpen(row)}>Open</button>
                )}
              </td>
            </tr>
          ))}
          {!rows.length && (
            <tr><td colSpan={7} className="muted">
              No developers yet. Add one under People and profiles, then attach it to the
              profile it is sold under.
            </td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
