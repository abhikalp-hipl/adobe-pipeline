import axios from "axios";

const TOKEN_KEY = "app_jwt";

export const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

const api = axios.create({
  baseURL: API_BASE,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export const setAppJwt = (token) => {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
};

export const getAppJwt = () => localStorage.getItem(TOKEN_KEY);

export const parseJwtPayload = (token) => {
  if (!token || typeof token !== "string") return null;
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  try {
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    return JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    return null;
  }
};

export const DASHBOARD_SESSION_CACHE_PREFIXES = [
  "dashboard_runs_cache_v1",
  "dashboard_files_cache_v1",
  "dashboard_updated_at_cache_v1",
  "dashboard_run_files_by_id_cache_v1",
  "dashboard_folder_files_cache_v1",
];

export const getDeptCacheScope = () => {
  const payload = parseJwtPayload(getAppJwt());
  if (!payload) return "anonymous";
  if (payload.department_id != null) return String(payload.department_id);
  if (payload.role) return String(payload.role);
  return "anonymous";
};

export const dashboardScopedCacheKey = (baseKey) => `${baseKey}_${getDeptCacheScope()}`;

export const clearDashboardSessionCache = () => {
  if (typeof window === "undefined") return;
  const keysToRemove = [];
  for (let i = 0; i < window.sessionStorage.length; i += 1) {
    const key = window.sessionStorage.key(i);
    if (!key) continue;
    if (
      DASHBOARD_SESSION_CACHE_PREFIXES.some(
        (prefix) => key === prefix || key.startsWith(`${prefix}_`)
      )
    ) {
      keysToRemove.push(key);
    }
  }
  keysToRemove.forEach((key) => window.sessionStorage.removeItem(key));
};

export const loginApp = async (username, password) => {
  const response = await api.post("/auth/login", { username, password });
  return response.data;
};

export const getScheduler = async () => {
  const response = await api.get("/scheduler");
  return response.data;
};

export const updateScheduler = async (interval) => {
  const response = await api.post("/scheduler/interval", { interval });
  return response.data;
};

export const runNow = async () => {
  const response = await api.post("/scheduler/run-now");
  return response.data;
};

export const getFiles = async (folder) => {
  const response = await api.get("/files", { params: { folder } });
  return response.data || [];
};

export const getFileContent = async (id) => {
  const response = await api.get("/file-content", { params: { id } });
  return response.data;
};

export const getFileContentArrayBuffer = async (id) => {
  const response = await api.get("/file-content", {
    params: { id },
    responseType: "arraybuffer",
  });
  return response.data;
};

/** Direct URL (no JWT) — do not use in iframes; use fetchAuthenticatedFileBlobUrl instead. */
export const getFileUrl = (id) => `${api.defaults.baseURL}/file-content?id=${encodeURIComponent(id)}`;

export const revokeObjectUrl = (url) => {
  if (url && String(url).startsWith("blob:")) {
    URL.revokeObjectURL(url);
  }
};

export const fetchAuthenticatedFileBlobUrl = async (id) => {
  const response = await api.get("/file-content", {
    params: { id },
    responseType: "blob",
  });
  const contentType = response.headers["content-type"] || "application/octet-stream";
  const blob =
    response.data instanceof Blob ? response.data : new Blob([response.data], { type: contentType });
  return URL.createObjectURL(blob);
};

export const downloadAuthenticatedFile = async (id, filename = "download") => {
  const blobUrl = await fetchAuthenticatedFileBlobUrl(id);
  const anchor = document.createElement("a");
  anchor.href = blobUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  revokeObjectUrl(blobUrl);
};

export const openAuthenticatedFileInNewTab = async (id) => {
  const blobUrl = await fetchAuthenticatedFileBlobUrl(id);
  const opened = window.open(blobUrl, "_blank", "noopener,noreferrer");
  if (!opened) {
    revokeObjectUrl(blobUrl);
    throw new Error("Popup blocked. Allow popups for this site to open the file.");
  }
  window.setTimeout(() => revokeObjectUrl(blobUrl), 60_000);
};

export const fetchAuthenticatedPreviewPdfBlobUrl = async (id) => {
  const response = await api.get("/file-preview-pdf", {
    params: { id },
    responseType: "blob",
  });
  const blob =
    response.data instanceof Blob ? response.data : new Blob([response.data], { type: "application/pdf" });
  return URL.createObjectURL(blob);
};

export const getEmailGroup = async () => {
  const response = await api.get("/email-group");
  return response.data || [];
};

export const addEmailGroup = async (email) => {
  const response = await api.post("/email-group", { email });
  return response.data;
};

export const deleteEmailGroup = async (id) => {
  await api.delete(`/email-group/${encodeURIComponent(id)}`);
};

export const getRuns = async () => {
  const response = await api.get("/runs");
  return response.data || [];
};

export const getRunFiles = async (runId) => {
  const response = await api.get(`/runs/${encodeURIComponent(runId)}/files`);
  return response.data || [];
};

export const getRunDetails = async (runId) => {
  const response = await api.get(`/runs/${encodeURIComponent(runId)}`);
  return response.data;
};

export const getAccessibilityDetail = async (pdfId, jsonId) => {
  const response = await api.get("/accessibility-detail", {
    params: { pdf_id: pdfId, json_id: jsonId },
  });
  return response.data;
};

export const downloadAccessibilityReportXlsx = async (pdfId, jsonId) => {
  const response = await api.get("/accessibility-detail/export", {
    params: { pdf_id: pdfId, json_id: jsonId },
    responseType: "blob",
  });
  return response.data;
};

export const normalizeRunFiles = (files) =>
  (Array.isArray(files) ? files : []).map((file) => ({
    name: file?.name || file?.file_name || "",
    status: file?.status || "FAILED",
    error: file?.error || file?.error_message || "",
    outputs: {
      pdf_url: file?.outputs?.pdf_url || null,
      json_url: file?.outputs?.json_url || null,
      xlsx_url: file?.outputs?.xlsx_url || null,
    },
    accessibility: {
      passed: Number(file?.accessibility?.passed || 0),
      failed: Number(file?.accessibility?.failed || 0),
      manual: Number(file?.accessibility?.manual || 0),
    },
    created_at: file?.created_at || "",
  }));

export const getSettings = async () => {
  const response = await api.get("/settings");
  return response.data;
};

export const saveSettings = async ({ eod_time, enabled }) => {
  const response = await api.post("/settings", { eod_time, enabled });
  return response.data;
};

export const getAdminDepartments = async () => {
  const response = await api.get("/admin/departments");
  return response.data || [];
};

export const createAdminDepartment = async (body) => {
  const response = await api.post("/admin/departments", body);
  return response.data;
};

export const deleteAdminDepartment = async (id) => {
  await api.delete(`/admin/departments/${encodeURIComponent(id)}`);
};

export const getAdminDepartment = async (id) => {
  const response = await api.get(`/admin/departments/${encodeURIComponent(id)}`);
  return response.data;
};

export const updateAdminDepartment = async (id, body) => {
  const response = await api.put(`/admin/departments/${encodeURIComponent(id)}`, body);
  return response.data;
};

export const getDepartmentMe = async () => {
  const response = await api.get("/departments/me");
  return response.data;
};

export const getDepartmentMicrosoftStatus = async () => {
  const response = await api.get("/departments/me/microsoft-status");
  return response.data;
};

export const updateDepartmentMe = async (body) => {
  const response = await api.put("/departments/me", body);
  return response.data;
};

export const getMicrosoftDeptLoginUrl = (departmentId) =>
  `${API_BASE}/auth/dept/${encodeURIComponent(departmentId)}/login`;
