import React, { useCallback, useEffect, useState } from "react";
import { api, getToken, setToken } from "./api.js";
import Login from "./views/Login.jsx";
import BdHome from "./views/BdHome.jsx";
import AdminHome from "./views/AdminHome.jsx";
import Dashboard from "./views/Dashboard.jsx";
import DevHome from "./views/DevHome.jsx";
import DevProfiles from "./views/DevProfiles.jsx";
import ManagerDashboard from "./views/ManagerDashboard.jsx";
import People from "./views/People.jsx";

export default function App() {
  const [user, setUser] = useState(null);
  // Both roles land on their dashboard, when they have one — it is the screen
  // that says what is waiting, and every route out of it is one button away.
  // A BD whose manager has not opened theirs lands on their work instead.
  const [view, setView] = useState("dashboard");
  const [booting, setBooting] = useState(true);

  const signOut = useCallback(() => {
    setToken("");
    setUser(null);
    setView("dashboard");
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
    api.me()
      .then((me) => {
        setUser(me);
        if (me.role === "bd" && !me.dashboard_visible) setView("work");
      })
      .catch(() => setToken(""))
      .finally(() => setBooting(false));
  }, []);

  if (booting) {
    return <div className="wrap muted">Loading…</div>;
  }

  if (!user) {
    // A developer always lands on their desk: their dashboard is a calendar,
    // not a set of figures somebody has to decide to show them.
    return <Login onSignedIn={(me) => {
      setUser(me);
      setView(me.role === "bd" && !me.dashboard_visible ? "work" : "dashboard");
    }} />;
  }

  const isAdmin = user.role === "admin";
  const isDev = user.role === "dev";

  return (
    <>
      <header className="top">
        <span className="brand">Dispatch</span>
        <nav className="tabs">
          {/* No tab for a dashboard this person has not been given. The server
              refuses the request too — this only saves them the dead end. */}
          {(isDev || user.dashboard_visible) && (
            <button className="tab" aria-current={view === "dashboard"}
                    onClick={() => setView("dashboard")}>{isDev ? "MY DESK" : "DASHBOARD"}</button>
          )}
          {isDev ? (
            <button className="tab" aria-current={view === "details"}
                    onClick={() => setView("details")}>MY DETAILS</button>
          ) : (
            <button className="tab" aria-current={view === "work"}
                    onClick={() => setView("work")}>{isAdmin ? "BATCHES" : "MY WORK"}</button>
          )}
          {isAdmin && (
            <button className="tab" aria-current={view === "people"}
                    onClick={() => setView("people")}>PEOPLE</button>
          )}
        </nav>
        <span className="spacer" />
        <span className="muted">
          {user.name} · {isAdmin ? "manager" : isDev ? "developer" : "business development"}
        </span>
        <button className="link" onClick={signOut}>Sign out</button>
      </header>

      <main className="wrap">
        {isAdmin ? (
          view === "people" ? <People />
            : view === "work" ? <AdminHome />
              : <ManagerDashboard onOpenBatches={() => setView("work")} />
        ) : isDev ? (
          view === "details"
            ? <DevProfiles />
            : <DevHome onOpenProfiles={() => setView("details")} />
        ) : (
          view === "dashboard" && user.dashboard_visible
            ? <Dashboard onOpenWork={() => setView("work")} />
            : <BdHome />
        )}
      </main>
    </>
  );
}
