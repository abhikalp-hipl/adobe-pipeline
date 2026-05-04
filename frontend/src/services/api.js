import axios from "axios";

const api = axios.create({
  baseURL: "http://localhost:8000",
});

export const uploadDocument = async (file) => {
  const formData = new FormData();
  formData.append("file", file);
  const response = await api.post("/documents/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
};

export const getDocuments = async () => {
  const response = await api.get("/documents");
  return response.data;
};

export const processDocument = async (id) => {
  const response = await api.post(`/documents/${id}/process`);
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
  const response = await api.post("/run-now");
  return response.data;
};

export const processOneDriveIntake = async () => {
  const response = await api.post("/documents/onedrive/process-intake");
  return response.data;
};

export const getAuthStatus = async () => {
  const response = await api.get("/auth/status");
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

export const getFileUrl = (id) => `${api.defaults.baseURL}/file-content?id=${encodeURIComponent(id)}`;
export const getFilePreviewPdfUrl = (id) =>
  `${api.defaults.baseURL}/file-preview-pdf?id=${encodeURIComponent(id)}`;

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
