import React, { useCallback, useEffect, useState } from "react";
import { api, getToken, setToken } from "./api.js";
import Login from "./views/Login.jsx";
import BdHome from "./views/BdHome.jsx";
import AdminHome from "./views/AdminHome.jsx";
import People from "./views/People.jsx";

export default function App() {
  const [user, setUser] = useState(null);
  const [view, setView] = useState("work");
  const [booting, setBooting] = useState(true);

  const signOut = useCallback(() => {
    setToken("");
    setUser(null);
    setView("work");
  }, []);

  useEffect(() => {
    window.addEventListener("dispatch:signed-out", signOut);
    return () => window.removeEventListener("dispatch:signed-out", signOut);
  }, [signOut]);

  useEffect(() => {
    if (!getToken()) {
      setBooting(false);
      return;
    }
    api.me().then(setUser).catch(() => setToken("")).finally(() => setBooting(false));
  }, []);

  if (booting) {
    return <div className="wrap muted">Loading…</div>;
  }

  if (!user) {
    return <Login onSignedIn={setUser} />;
  }

  const isAdmin = user.role === "admin";

  return (
    <>
      <header className="top">
        <span className="brand">Dispatch</span>
        {isAdmin && (
          <nav className="tabs">
            <button className="tab" aria-current={view === "work"} onClick={() => setView("work")}>BATCHES</button>
            <button className="tab" aria-current={view === "people"} onClick={() => setView("people")}>PEOPLE</button>
          </nav>
        )}
        <span className="spacer" />
        <span className="muted">
          {user.name} · {isAdmin ? "manager" : "business development"}
        </span>
        <button className="link" onClick={signOut}>Sign out</button>
      </header>

      <main className="wrap">
        {isAdmin
          ? view === "people" ? <People /> : <AdminHome />
          : <BdHome />}
      </main>
    </>
  );
}
