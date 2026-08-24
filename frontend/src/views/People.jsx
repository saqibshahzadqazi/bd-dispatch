import React, { useEffect, useState } from "react";
import { api, safeUrl } from "../api.js";
import { Availability } from "./widgets.jsx";

const BLANK_PERSON = { name: "", email: "", password: "", role: "bd" };
const BLANK_PROFILE = { name: "", headline: "", platform: "", user_id: "", dev_user_id: "" };

const ROLE_LABELS = {
  admin: "manager",
  bd: "business development",
  dev: "developer",
};

export default function People() {
  const [people, setPeople] = useState([]);
  const [profiles, setProfiles] = useState([]);
  const [person, setPerson] = useState(BLANK_PERSON);
  const [profile, setProfile] = useState(BLANK_PROFILE);
  const [note, setNote] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const [users, identities] = await Promise.all([api.listUsers(), api.listProfiles()]);
      setPeople(users);
      setProfiles(identities);
    } catch (err) {
      setNote({ bad: true, text: err.message });
    }
  };
  useEffect(() => { load(); }, []);

  const addPerson = async () => {
    setBusy(true);
    setNote(null);
    try {
      await api.createUser({
        name: person.name.trim(),
        email: person.email.trim().toLowerCase(),
        password: person.password,
        role: person.role,
      });
      setPerson(BLANK_PERSON);
      await load();
      setNote({ text: `${person.name} can sign in now. Send them the password you just set.` });
    } catch (err) {
      setNote({ bad: true, text: err.message });
    } finally {
      setBusy(false);
    }
  };

  const addProfile = async () => {
    setBusy(true);
    setNote(null);
    try {
      const made = await api.createProfile({
        name: profile.name.trim(),
        headline: profile.headline.trim(),
        platform: profile.platform.trim(),
        user_id: profile.user_id ? Number(profile.user_id) : null,
        dev_user_id: profile.dev_user_id ? Number(profile.dev_user_id) : null,
      });
      setProfile(BLANK_PROFILE);
      await load();
      setNote({ text: `${made.name} is ready. Whoever runs it can hand in a sheet for it.` });
    } catch (err) {
      setNote({ bad: true, text: err.message });
    } finally {
      setBusy(false);
    }
  };

  const reassign = async (id, userId) => {
    try {
      await api.updateProfile(id, { user_id: Number(userId) });
      await load();
    } catch (err) {
      setNote({ bad: true, text: err.message });
    }
  };

  const setDeveloper = async (item, userId) => {
    try {
      await api.updateProfile(item.id, { dev_user_id: Number(userId) });
      await load();
      const dev = people.find((p) => p.id === Number(userId));
      setNote({
        text: dev
          ? `${dev.name} is now the developer behind ${item.name}. Interviews booked against `
            + `that profile land on their screen, and they can keep the resume and email current.`
          : `${item.name} has nobody behind it.`,
      });
    } catch (err) {
      setNote({ bad: true, text: err.message });
    }
  };

  const setDashboard = async (item, open) => {
    try {
      await api.updateUser(item.id, { dashboard_visible: open });
      await load();
      setNote({
        text: open
          ? `${item.name} can now see their own dashboard.`
          : `${item.name}'s dashboard is closed. Their work is unaffected.`,
      });
    } catch (err) {
      setNote({ bad: true, text: err.message });
    }
  };

  const setShared = async (id, share) => {
    try {
      await api.updateProfile(id, { share_progress: share });
      await load();
    } catch (err) {
      setNote({ bad: true, text: err.message });
    }
  };

  const retire = async (item) => {
    if (!window.confirm(
      `Retire ${item.name}? Its application history stays, so nothing it has already ` +
      `applied to will be offered to it again if you bring it back.`)) return;
    try {
      await api.retireProfile(item.id);
      await load();
    } catch (err) {
      setNote({ bad: true, text: err.message });
    }
  };

  const turnOff = async (item) => {
    if (!window.confirm(`Switch off ${item.name}? Their past sheets stay, but they cannot sign in.`)) return;
    try {
      await api.deactivateUser(item.id);
      await load();
    } catch (err) {
      setNote({ bad: true, text: err.message });
    }
  };

  const personReady = person.name && person.email && person.password.length >= 8;
  const profileReady = profile.name.trim() && profile.user_id;
  const bds = people.filter((p) => p.is_active);
  const devs = people.filter((p) => p.is_active && p.role === "dev");

  return (
    <div className="stack">
      <div>
        <h1>People and profiles</h1>
        <p className="muted" style={{ marginTop: 3, maxWidth: 780 }}>
          A <b>person</b> signs in. A <b>profile</b> is the identity a job is applied under —
          the name and resume the client sees. One person can run several.
        </p>
        <p className="muted" style={{ marginTop: 6, maxWidth: 780 }}>
          Two people stand behind every profile and they are not the same person. The
          <b> BD</b> runs the account and does the applying. The <b>developer</b> is who the
          profile actually sells — the one who sits the interview and writes the code. Attach
          them below and interviews reach them without anybody forwarding an email.
        </p>
      </div>

      {note && <div className={note.bad ? "notice" : "notice ok"}>{note.text}</div>}

      <section className="card pad">
        <h2>Add a profile</h2>
        <p className="muted" style={{ marginTop: 6 }}>
          Two profiles with the same skills are exactly the point: they are two different
          candidates, so both may go for the same job. The system only ever stops one
          profile applying to the same job twice.
        </p>
        <p className="muted" style={{ marginTop: 6 }}>
          <b>On the board</b> decides whether a profile appears on the shared team board.
          It only matters once you open that board from the dashboard — until then nobody
          but you sees anyone else's numbers.
        </p>
        <div className="row" style={{ marginTop: 12 }}>
          <input placeholder="Profile name, e.g. Khuram" value={profile.name}
                 onChange={(e) => setProfile({ ...profile, name: e.target.value })} />
          <input placeholder="Resume / headline, e.g. AI Engineer" value={profile.headline}
                 style={{ minWidth: 190 }}
                 onChange={(e) => setProfile({ ...profile, headline: e.target.value })} />
          <input placeholder="Platform (optional)" value={profile.platform} style={{ width: 150 }}
                 onChange={(e) => setProfile({ ...profile, platform: e.target.value })} />
          <select value={profile.user_id}
                  onChange={(e) => setProfile({ ...profile, user_id: e.target.value })}>
            <option value="">— which BD runs it? —</option>
            {bds.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <select value={profile.dev_user_id}
                  onChange={(e) => setProfile({ ...profile, dev_user_id: e.target.value })}>
            <option value="">— which developer is it? —</option>
            {people.filter((p) => p.is_active).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}{p.role === "dev" ? "" : ` · ${ROLE_LABELS[p.role] || p.role}`}
              </option>
            ))}
          </select>
          <button onClick={addProfile} disabled={busy || !profileReady}>Add profile</button>
        </div>
      </section>

      <div className="card scroll">
        <table>
          <thead>
            <tr><th>Profile</th><th>Headline</th><th>Run by</th>
                <th title="The person the client would actually be meeting">Developer</th>
                <th title="What a BD attaches when applying under this profile">Resume</th>
                <th title="Whether this profile appears on the shared team board">On the board</th>
                <th /></tr>
          </thead>
          <tbody>
            {profiles.map((item) => (
              <tr key={item.id}>
                <td style={{ fontWeight: 500 }}>
                  {item.name}
                  {item.platform && (
                    <div className="muted" style={{ fontSize: 11 }}>{item.platform}</div>
                  )}
                </td>
                <td>{item.headline || <span className="muted">—</span>}</td>
                <td>
                  <select value={item.user_id || ""} onChange={(e) => reassign(item.id, e.target.value)}>
                    {!item.user_id && <option value="">— nobody —</option>}
                    {bds.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                </td>
                <td>
                  <select value={item.dev_user_id || ""}
                          onChange={(e) => setDeveloper(item, e.target.value)}>
                    <option value="">— nobody —</option>
                    {people.filter((p) => p.is_active).map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}{p.role === "dev" ? "" : ` · ${ROLE_LABELS[p.role] || p.role}`}
                      </option>
                    ))}
                  </select>
                  {item.dev_user_id && (
                    <div style={{ marginTop: 4 }}><Availability value={item.availability} small /></div>
                  )}
                </td>
                <td>
                  {safeUrl(item.resume_url)
                    ? <a href={safeUrl(item.resume_url)} target="_blank" rel="noreferrer noopener">open</a>
                    : <span className="muted" title="The developer sets this on their own screen">
                        not set
                      </span>}
                </td>
                <td>
                  <label className="row" style={{ gap: 6 }}>
                    <input type="checkbox" checked={item.share_progress !== false}
                           onChange={(e) => setShared(item.id, e.target.checked)} />
                    {item.share_progress === false ? "hidden" : "shown"}
                  </label>
                </td>
                <td style={{ textAlign: "right" }}>
                  <button className="link" onClick={() => retire(item)}>Retire</button>
                </td>
              </tr>
            ))}
            {!profiles.length && (
              <tr><td colSpan={7} className="muted">
                No profiles yet. Nobody can hand in a sheet until there is at least one.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      <section className="card pad">
        <h2>Add a person</h2>
        <p className="muted" style={{ marginTop: 6, maxWidth: 680 }}>
          A new BD starts with <b>no dashboard</b>. They can log jobs and work their list
          straight away; the screen of figures — what they logged, how much a colleague also
          found, how much of their list they have worked through — appears only once you open
          it for them in the table below.
        </p>
        <p className="muted" style={{ marginTop: 6, maxWidth: 680 }}>
          A <b>developer</b> is different, and the switch does not apply to them. Their screen
          is their own diary and their own resume, not a set of figures somebody has to decide
          to show them — so it works from the moment the account exists. Attach them to a
          profile above or they sign in to an empty desk.
        </p>
        <div className="row" style={{ marginTop: 12 }}>
          <input placeholder="Full name" value={person.name}
                 onChange={(e) => setPerson({ ...person, name: e.target.value })} />
          <input placeholder="Email" type="email" value={person.email} style={{ minWidth: 200 }}
                 onChange={(e) => setPerson({ ...person, email: e.target.value })} />
          <input placeholder="Password (8+ characters)" type="text" value={person.password}
                 onChange={(e) => setPerson({ ...person, password: e.target.value })} />
          <select value={person.role} onChange={(e) => setPerson({ ...person, role: e.target.value })}>
            <option value="bd">Business development</option>
            <option value="dev">Developer</option>
            <option value="admin">Manager</option>
          </select>
          <button onClick={addPerson} disabled={busy || !personReady}>Add</button>
        </div>
        {person.password && person.password.length < 8 && (
          <p className="muted" style={{ marginTop: 8, color: "var(--brick)" }}>
            Use at least 8 characters.
          </p>
        )}
      </section>

      <div className="card scroll">
        <table>
          <thead>
            <tr><th>Name</th><th>Email</th><th>Role</th><th>Profiles</th><th>Status</th>
                <th title="Whether this person may open their own dashboard of figures">Dashboard</th>
                <th /></tr>
          </thead>
          <tbody>
            {people.map((p) => {
              // A BD is measured on the profiles they run; a developer on the
              // ones they are sold under. Same column, two different questions.
              const theirs = p.role === "dev"
                ? profiles.filter((item) => item.dev_user_id === p.id)
                : profiles.filter((item) => item.user_id === p.id);
              return (
                <tr key={p.id} style={{ opacity: p.is_active ? 1 : 0.5 }}>
                  <td style={{ fontWeight: 500 }}>{p.name}</td>
                  <td className="mono" style={{ fontSize: 12 }}>{p.email}</td>
                  <td className="muted">{ROLE_LABELS[p.role] || p.role}</td>
                  <td>
                    {theirs.length
                      ? <span className="row" style={{ gap: 5 }}>
                          {theirs.map((item) => <span className="pill on" key={item.id}>{item.name}</span>)}
                        </span>
                      : <span className="muted">
                          {p.role === "dev"
                            ? "not behind any profile — they see an empty desk"
                            : "none yet"}
                        </span>}
                  </td>
                  <td>
                    <span className={p.is_active ? "pill on" : "pill off"}>
                      {p.is_active ? "active" : "switched off"}
                    </span>
                  </td>
                  <td>
                    {p.role === "admin" ? (
                      <span className="muted">always</span>
                    ) : p.role === "dev" ? (
                      <span className="muted" title="A developer sees their own diary and resume, which is not a figure anybody has to decide to show them.">
                        not a figures screen
                      </span>
                    ) : (
                      <label className="row" style={{ gap: 6 }}>
                        <input type="checkbox" checked={!!p.dashboard_visible}
                               disabled={!p.is_active}
                               onChange={(e) => setDashboard(p, e.target.checked)} />
                        <span className={p.dashboard_visible ? "pill on" : "pill off"}>
                          {p.dashboard_visible ? "open" : "closed"}
                        </span>
                      </label>
                    )}
                  </td>
                  <td style={{ textAlign: "right" }}>
                    {p.is_active && <button className="link" onClick={() => turnOff(p)}>Switch off</button>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
