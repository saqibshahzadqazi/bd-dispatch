import React, { useState } from "react";
import { api, setToken } from "../api.js";

export default function Login({ onSignedIn }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setError("");
    setBusy(true);
    try {
      const data = await api.login(email.trim(), password);
      setToken(data.token);
      onSignedIn(data.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="wrap" style={{ maxWidth: 380, paddingTop: 90 }}>
      <h1>Dispatch</h1>
      <p className="muted" style={{ marginTop: 6, marginBottom: 22 }}>
        Upload your applied-jobs sheet, collect a list nobody else is working.
      </p>

      <div className="card pad stack" style={{ gap: 13 }}>
        <div>
          <label htmlFor="email">Email</label>
          <input id="email" type="email" value={email} autoComplete="username"
                 style={{ width: "100%", marginTop: 5 }}
                 onChange={(e) => setEmail(e.target.value)}
                 onKeyDown={(e) => e.key === "Enter" && submit()} />
        </div>
        <div>
          <label htmlFor="password">Password</label>
          <input id="password" type="password" value={password} autoComplete="current-password"
                 style={{ width: "100%", marginTop: 5 }}
                 onChange={(e) => setPassword(e.target.value)}
                 onKeyDown={(e) => e.key === "Enter" && submit()} />
        </div>
        {error && <div className="notice">{error}</div>}
        <button onClick={submit} disabled={busy || !email || !password}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </div>
    </div>
  );
}
