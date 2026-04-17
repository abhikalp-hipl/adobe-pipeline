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

export const getPipelineStatus = async () => {
  const response = await api.get("/pipeline/status");
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
  // eslint-disable-next-line no-console
  console.log("GET /files response", folder, response.data);
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
