const KEY = "dispatch.token";

export function getToken() {
  return sessionStorage.getItem(KEY) || "";
}

export function setToken(value) {
  if (value) sessionStorage.setItem(KEY, value);
  else sessionStorage.removeItem(KEY);
}

async function request(path, { method = "GET", body, form } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body) headers["Content-Type"] = "application/json";

  const response = await fetch(`/api${path}`, {
    method,
    headers,
    body: form ? form : body ? JSON.stringify(body) : undefined,
  });

  if (response.status === 401) {
    setToken("");
    window.dispatchEvent(new Event("dispatch:signed-out"));
    throw new Error("Your session ended. Sign in again.");
  }
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const data = await response.json();
      if (data.detail) message = typeof data.detail === "string" ? data.detail : message;
    } catch {
      /* response had no JSON body */
    }
    throw new Error(message);
  }
  if (response.status === 204) return null;
  return response.json();
}

/** Only ever put an http(s) link in an href.
 *
 * Job links come out of spreadsheets other people typed, and the backend is
 * not the last line of defence — a `javascript:` href would run in this app's
 * own origin, with the signed-in token sitting in sessionStorage.
 */
export function safeUrl(value) {
  return /^https?:\/\//i.test(value || "") ? value : "";
}

/** Trigger a browser download for an authenticated endpoint. */
export async function download(path, fallbackName) {
  const response = await fetch(`/api${path}`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!response.ok) {
    let message = "That file is not ready yet.";
    try {
      const data = await response.json();
      if (data.detail) message = data.detail;
    } catch { /* not JSON */ }
    throw new Error(message);
  }
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = match ? match[1] : fallbackName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export const api = {
  login: (email, password) => request("/auth/login", { method: "POST", body: { email, password } }),
  me: () => request("/auth/me"),

  listUsers: () => request("/users"),
  createUser: (payload) => request("/users", { method: "POST", body: payload }),
  deactivateUser: (id) => request(`/users/${id}`, { method: "DELETE" }),

  listProfiles: () => request("/profiles"),
  createProfile: (payload) => request("/profiles", { method: "POST", body: payload }),
  updateProfile: (id, payload) => request(`/profiles/${id}`, { method: "PATCH", body: payload }),
  retireProfile: (id) => request(`/profiles/${id}`, { method: "DELETE" }),

  listBatches: () => request("/batches"),
  createBatch: (payload) => request("/batches", { method: "POST", body: payload }),
  getBatch: (id) => request(`/batches/${id}`),
  compute: (id) => request(`/batches/${id}/compute`, { method: "POST" }),
  closeBatch: (id) => request(`/batches/${id}/close`, { method: "POST" }),
  reopenBatch: (id) => request(`/batches/${id}/reopen`, { method: "POST" }),
  report: (id) => request(`/batches/${id}/report`),

  upload: (batchId, profileId, file) => {
    const form = new FormData();
    form.append("profile_id", profileId);
    form.append("file", file);
    return request(`/batches/${batchId}/uploads`, { method: "POST", form });
  },
  setMapping: (uploadId, mapping) =>
    request(`/uploads/${uploadId}/mapping`, { method: "PATCH", body: { mapping } }),
  deleteUpload: (uploadId) => request(`/uploads/${uploadId}`, { method: "DELETE" }),

  listEntries: (batchId, profileId) =>
    request(`/batches/${batchId}/profiles/${profileId}/entries`),
  saveEntries: (batchId, profileId, rows) =>
    request(`/batches/${batchId}/profiles/${profileId}/entries`, { method: "PUT", body: { rows } }),

  mySheets: (batchId) => request(`/batches/${batchId}/my-sheets`),
  setStatus: (assignmentId, status) =>
    request(`/assignments/${assignmentId}`, { method: "PATCH", body: { status } }),
};
