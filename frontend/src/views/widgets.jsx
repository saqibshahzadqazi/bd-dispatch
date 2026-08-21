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
