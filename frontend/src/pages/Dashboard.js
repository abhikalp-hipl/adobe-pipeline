import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Calendar,
  CheckCircle,
  Code,
  Download,
  FileText,
  Folder,
  Play,
  Table,
  User,
  XCircle,
} from "lucide-react";

import ExcelViewer from "../components/ExcelViewer";
import FileTable from "../components/FileTable";
import DailyReportModal from "../components/DailyReportModal";
import EmailModal from "../components/EmailModal";
import DepartmentSettingsPanel from "../components/DepartmentSettingsPanel";
import Modal from "../components/Modal";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import SuccessToast from "../components/SuccessToast";
import {
  addEmailGroup,
  deleteEmailGroup,
  getFileContent,
  getFileContentArrayBuffer,
  downloadAuthenticatedFile,
  fetchAuthenticatedFileBlobUrl,
  openAuthenticatedFileInNewTab,
  fetchAuthenticatedPreviewPdfBlobUrl,
  revokeObjectUrl,
  getEmailGroup,
  getFiles,
  getRunFiles,
  getRuns,
  getSettings,
  getAccessibilityDetail,
  downloadAccessibilityReportXlsx,
  getScheduler,
  runNow,
  saveSettings,
  normalizeRunFiles,
  updateScheduler,
  setAppJwt,
  getAppJwt,
  parseJwtPayload,
  dashboardScopedCacheKey,
  clearDashboardSessionCache,
  getDepartmentMe,
  getDepartmentMicrosoftStatus,
} from "../services/api";

const FOLDERS = [
  { key: "intake", label: "Intake" },
  { key: "processed", label: "Processed Originals" },
  { key: "output/success", label: "Output Success" },
  { key: "output/failure", label: "Output Failure" },
];

const STATUS_CLASS = {
  passed: "text-green-600",
  failed: "text-red-600",
  "needs manual check": "text-yellow-600",
};

const EMPTY_SUMMARY = {
  passed: 0,
  failed: 0,
  needsManual: 0,
  passedManually: 0,
  failedManually: 0,
  skipped: 0,
  description: "",
};

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const DASHBOARD_CACHE_TTL_MS = 60 * 1000;
const RUN_FILES_CACHE_TTL_MS = 5 * 60 * 1000;
const FOLDER_FILES_CACHE_TTL_MS = 30 * 1000;
const FOLDER_FILES_STORAGE_MAX_AGE_MS = 24 * 60 * 60 * 1000;
const DASHBOARD_CACHE_KEYS = {
  runs: "dashboard_runs_cache_v1",
  dashboardFiles: "dashboard_files_cache_v1",
  dashboardUpdatedAt: "dashboard_updated_at_cache_v1",
  runFilesByRunId: "dashboard_run_files_by_id_cache_v1",
  folderFilesByFolder: "dashboard_folder_files_cache_v1",
};

const scopedCacheKey = (baseKey) => dashboardScopedCacheKey(baseKey);

function fileFetchErrorMessage(err) {
  const status = err?.response?.status;
  const detail = err?.response?.data?.detail;
  if (status === 401) {
    return (
      detail ||
      "Microsoft OneDrive is not connected for this department. Ask your administrator to connect Microsoft in the Admin panel, then refresh."
    );
  }
  return detail || "Failed to fetch files from OneDrive.";
}

function readSessionCache(key, maxAgeMs, fallback) {
  if (typeof window === "undefined") {
    return fallback;
  }
  try {
    const raw = window.sessionStorage.getItem(key);
    if (!raw) {
      return fallback;
    }
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") {
      return fallback;
    }
    const ts = Number(parsed.ts || 0);
    if (!ts || Date.now() - ts > maxAgeMs) {
      return fallback;
    }
    return parsed.value ?? fallback;
  } catch {
    return fallback;
  }
}

function writeSessionCache(key, value) {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.sessionStorage.setItem(
      key,
      JSON.stringify({
        ts: Date.now(),
        value,
      })
    );
  } catch {
    // ignore cache write errors
  }
}

function tryParseJson(value) {
  if (typeof value !== "string") {
    return null;
  }
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function normalizeReportEntry(entry) {
  const parsed = tryParseJson(entry);
  const obj = parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : entry;
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) {
    return { rule: "", status: "", description: "" };
  }

  const rule = obj.rule ?? obj.Rule ?? obj.name ?? obj.Name ?? "";
  const status = obj.status ?? obj.Status ?? obj.result ?? obj.Result ?? obj.outcome ?? obj.Outcome ?? "";
  const description = obj.description ?? obj.Description ?? obj.message ?? obj.Message ?? "";
  return {
    rule: typeof rule === "string" ? rule : String(rule ?? ""),
    status: typeof status === "string" ? status : String(status ?? ""),
    description: typeof description === "string" ? description : String(description ?? ""),
  };
}

function AccessibilityExcelDownloadButton({ busy, onClick }) {
  return (
    <button
      type="button"
      disabled={busy}
      onClick={onClick}
      className="inline-flex items-center gap-1.5 shrink-0 px-3 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium"
    >
      <Download size={16} />
      {busy ? "Preparing…" : "Download"}
    </button>
  );
}

/** Stem before *_accessibility_report.json / .json (same rules as companion PDF lookup). */
function stemFromAccessibilityJsonFileName(jsonFileName) {
  if (!jsonFileName || typeof jsonFileName !== "string") {
    return "";
  }
  const lower = jsonFileName.toLowerCase();
  if (lower.endsWith("_accessibility_report.json")) {
    return jsonFileName.slice(0, -"_accessibility_report.json".length);
  }
  if (lower.endsWith("_report.json")) {
    return jsonFileName.slice(0, -"_report.json".length);
  }
  if (lower.endsWith(".accessibility-report.json")) {
    return jsonFileName.slice(0, -".accessibility-report.json".length);
  }
  if (lower.endsWith(".json")) {
    return jsonFileName.slice(0, -".json".length);
  }
  return "";
}

/** OneDrive file id for tagged PDF in the same folder listing, or "". */
function findCompanionTaggedPdfId(jsonFileName, fileList) {
  if (!jsonFileName || typeof jsonFileName !== "string" || !Array.isArray(fileList)) {
    return "";
  }
  const stem = stemFromAccessibilityJsonFileName(jsonFileName);
  if (!stem) {
    return "";
  }
  const candidates = [`${stem}_tagged_pdf.pdf`, `${stem}_tagged.pdf`, `${stem}.tagged.pdf`];
  for (const cand of candidates) {
    const hit = fileList.find((f) => (f?.name || "").toLowerCase() === cand.toLowerCase());
    if (hit?.id) {
      return String(hit.id);
    }
  }
  return "";
}

function buildAccessibilityLocationHints(data) {
  if (!data || typeof data !== "object") {
    return { pagesByKey: new Map(), unlocatable: new Set() };
  }
  const pageBuckets = new Map();
  for (const [pageStr, failures] of Object.entries(data.failures_by_page || {})) {
    const pageNum = Number(pageStr);
    if (!Number.isFinite(pageNum)) {
      continue;
    }
    if (!Array.isArray(failures)) {
      continue;
    }
    for (const f of failures) {
      const cat = f?.category ?? f?.Category ?? "";
      const rule = f?.rule ?? f?.Rule ?? "";
      const key = `${cat}|${rule}`;
      if (!pageBuckets.has(key)) {
        pageBuckets.set(key, new Set());
      }
      pageBuckets.get(key).add(pageNum);
    }
  }
  const pagesByKey = new Map();
  for (const [key, set] of pageBuckets.entries()) {
    pagesByKey.set(key, [...set].sort((a, b) => a - b));
  }
  const unlocatable = new Set(
    (Array.isArray(data.unlocatable_failures) ? data.unlocatable_failures : []).map((f) => {
      const cat = f?.category ?? f?.Category ?? "";
      const rule = f?.rule ?? f?.Rule ?? "";
      return `${cat}|${rule}`;
    })
  );
  return { pagesByKey, unlocatable };
}

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (!Number.isFinite(value) || value <= 0) {
    return "-";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  const idx = Math.min(units.length - 1, Math.floor(Math.log(value) / Math.log(1024)));
  const scaled = value / 1024 ** idx;
  const digits = idx === 0 ? 0 : scaled >= 10 ? 1 : 2;
  return `${scaled.toFixed(digits)} ${units[idx]}`;
}

function formatRelativeTime(iso) {
  if (!iso) {
    return "-";
  }
  const date = parseApiDate(iso);
  if (Number.isNaN(date.getTime())) {
    return "-";
  }
  const diffMs = Date.now() - date.getTime();
  const diffSeconds = Math.floor(diffMs / 1000);
  if (diffSeconds < 60) return "just now";
  const diffMinutes = Math.floor(diffSeconds / 60);
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

function parseApiDate(value) {
  if (!value) {
    return new Date("");
  }
  if (value instanceof Date) {
    return value;
  }
  const raw = String(value).trim();
  // If backend sends naive ISO datetime, treat it as UTC to avoid local-time misinterpretation.
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$/.test(raw)) {
    return new Date(`${raw}Z`);
  }
  return new Date(raw);
}

function formatLocalDateTime(value) {
  const date = parseApiDate(value);
  if (Number.isNaN(date.getTime())) {
    return "-";
  }
  return date.toLocaleString();
}

function fileTypeIcon(file) {
  const name = (file?.name || "").toLowerCase();
  const mime = (file?.mime_type || "").toLowerCase();
  if (name.endsWith(".pdf") || mime === "application/pdf") return <FileText size={18} className="text-red-500" />;
  if (name.endsWith(".doc") || name.endsWith(".docx") || mime.includes("wordprocessingml") || mime === "application/msword")
    return <FileText size={18} className="text-blue-500" />;
  if (name.endsWith(".xlsx") || mime.includes("spreadsheetml")) return <FileText size={18} className="text-emerald-500" />;
  if (name.endsWith(".json") || mime === "application/json") return <FileText size={18} className="text-amber-500" />;
  return <Folder size={18} className="text-gray-500" />;
}

function Dashboard({ initialActivePage = "dashboard" }) {
  const jwtPayload = useMemo(() => parseJwtPayload(getAppJwt()), []);
  const [activePage, setActivePage] = useState(initialActivePage);
  const [selectedFolder, setSelectedFolder] = useState("intake");
  const [files, setFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileContent, setFileContent] = useState(null);
  const [xlsxContent, setXlsxContent] = useState(null);
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);
  const [isLoadingContent, setIsLoadingContent] = useState(false);
  const [isOpeningFile, setIsOpeningFile] = useState(false);
  const [error, setError] = useState("");
  const [departmentName, setDepartmentName] = useState("");
  const [microsoftStatus, setMicrosoftStatus] = useState(null);
  const [isViewerOpen, setIsViewerOpen] = useState(false);
  const [docPreviewUrl, setDocPreviewUrl] = useState("");
  const [pdfBlobUrl, setPdfBlobUrl] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [showReportModal, setShowReportModal] = useState(false);
  const [value, setValue] = useState(5);
  const [unit, setUnit] = useState("minutes");
  const [isCustom, setIsCustom] = useState(false);
  const [isSavingSchedule, setIsSavingSchedule] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [lastUpdatedAt, setLastUpdatedAt] = useState(null);
  const [lastDashboardUpdatedAt, setLastDashboardUpdatedAt] = useState(
    () => readSessionCache(scopedCacheKey(DASHBOARD_CACHE_KEYS.dashboardUpdatedAt), DASHBOARD_CACHE_TTL_MS, null)
  );
  const [folderCounts, setFolderCounts] = useState({
    intake: 0,
    processed: 0,
    "output/success": 0,
    "output/failure": 0,
  });
  const [showProfileMenu, setShowProfileMenu] = useState(false);
  const [success, setSuccess] = useState(null);
  const [emails, setEmails] = useState([]);
  const [emailInput, setEmailInput] = useState("");
  const [isSavingEmail, setIsSavingEmail] = useState(false);
  const [deletingEmailId, setDeletingEmailId] = useState("");
  const [emailToast, setEmailToast] = useState("");
  const [showEmailModal, setShowEmailModal] = useState(false);
  const [runs, setRuns] = useState(
    () => readSessionCache(scopedCacheKey(DASHBOARD_CACHE_KEYS.runs), DASHBOARD_CACHE_TTL_MS, [])
  );
  const [expandedRunId, setExpandedRunId] = useState("");
  const [runFilesByRunId, setRunFilesByRunId] = useState(
    () => readSessionCache(scopedCacheKey(DASHBOARD_CACHE_KEYS.runFilesByRunId), RUN_FILES_CACHE_TTL_MS, {})
  );
  const [dashboardFiles, setDashboardFiles] = useState(
    () => readSessionCache(scopedCacheKey(DASHBOARD_CACHE_KEYS.dashboardFiles), DASHBOARD_CACHE_TTL_MS, [])
  );
  const [isLoadingDashboardFiles, setIsLoadingDashboardFiles] = useState(false);
  const [isLoadingRuns, setIsLoadingRuns] = useState(false);
  const [isLoadingRunFiles, setIsLoadingRunFiles] = useState(false);
  const [runsPage, setRunsPage] = useState(1);
  const [isRunNowPending, setIsRunNowPending] = useState(false);
  const [isPipelineRunning, setIsPipelineRunning] = useState(false);
  const [settings, setSettings] = useState({ eod_time: "14:00", enabled: false });
  const [eodTime, setEodTime] = useState("14:00");
  const [isSavingSettings, setIsSavingSettings] = useState(false);
  const [isLoadingReportSettings, setIsLoadingReportSettings] = useState(false);
  const [viewer, setViewer] = useState(null);
  const [viewerJson, setViewerJson] = useState(null);
  const [viewerXlsx, setViewerXlsx] = useState(null);
  const [isViewerLoading, setIsViewerLoading] = useState(false);
  const [accessibilityDetail, setAccessibilityDetail] = useState(null);
  const [isLoadingAccessibilityDetail, setIsLoadingAccessibilityDetail] = useState(false);
  const [isExportingAccessibilityReport, setIsExportingAccessibilityReport] = useState(false);
  const [downloadingFileId, setDownloadingFileId] = useState(null);
  const [folderAccessibilityDetail, setFolderAccessibilityDetail] = useState(null);
  const [isLoadingFolderAccessibilityDetail, setIsLoadingFolderAccessibilityDetail] = useState(false);
  const activePageRef = useRef(activePage);
  const selectedFolderRef = useRef(selectedFolder);
  const runFilesByRunIdRef = useRef(runFilesByRunId);
  const folderFetchRequestIdRef = useRef(0);
  const folderFilesCacheRef = useRef(
    readSessionCache(scopedCacheKey(DASHBOARD_CACHE_KEYS.folderFilesByFolder), FOLDER_FILES_STORAGE_MAX_AGE_MS, {})
  );
  const isRunNowPendingRef = useRef(false);
  const hasSeenPipelineRunningRef = useRef(false);

  const intervalOptions = [1, 2, 5, 10, 15, 30, 60];
  const showRunningState = isRunNowPending || isPipelineRunning;

  const refreshFolderCounts = useCallback(async () => {
    try {
      const [intake, processed, outputSuccess, outputFailure] = await Promise.all([
        getFiles("intake"),
        getFiles("processed"),
        getFiles("output/success"),
        getFiles("output/failure"),
      ]);
      setFolderCounts({
        intake: Array.isArray(intake) ? intake.length : 0,
        processed: Array.isArray(processed) ? processed.length : 0,
        "output/success": Array.isArray(outputSuccess) ? outputSuccess.length : 0,
        "output/failure": Array.isArray(outputFailure) ? outputFailure.length : 0,
      });
    } catch (requestError) {
      setError(fileFetchErrorMessage(requestError));
    }
  }, []);

  const prefetchAllFolderFiles = useCallback(async () => {
    try {
      const entries = await Promise.all(
        FOLDERS.map(async ({ key }) => {
          const files = await getFiles(key);
          const normalizedFiles = Array.isArray(files) ? files : [];
          return [key, { files: normalizedFiles, ts: Date.now() }];
        })
      );
      const nextCache = Object.fromEntries(entries);
      folderFilesCacheRef.current = {
        ...folderFilesCacheRef.current,
        ...nextCache,
      };
      writeSessionCache(scopedCacheKey(DASHBOARD_CACHE_KEYS.folderFilesByFolder), folderFilesCacheRef.current);
      setFolderCounts((prev) => {
        const next = { ...prev };
        Object.entries(nextCache).forEach(([key, payload]) => {
          next[key] = payload.files.length;
        });
        return next;
      });
      const selectedCached = folderFilesCacheRef.current[selectedFolderRef.current];
      if (selectedCached && Array.isArray(selectedCached.files)) {
        setFiles(selectedCached.files);
        setLastUpdatedAt(new Date(selectedCached.ts).toISOString());
      }
    } catch (requestError) {
      setError(fileFetchErrorMessage(requestError));
    }
  }, []);

  const refreshSelectedFolderFiles = useCallback(async (folderKey = selectedFolderRef.current, { force = false, background = false } = {}) => {
    const requestId = ++folderFetchRequestIdRef.current;
    setError("");
    if (!background) {
      setSelectedFile(null);
      setFileContent(null);
      setXlsxContent(null);
    }
    const now = Date.now();
    const cached = folderFilesCacheRef.current[folderKey];
    const hasCachedFiles = cached && Array.isArray(cached.files);
    const isFreshCache = hasCachedFiles && now - cached.ts < FOLDER_FILES_CACHE_TTL_MS;
    if (!force && hasCachedFiles) {
      setFiles(cached.files);
      setFolderCounts((prev) => ({
        ...prev,
        [folderKey]: cached.files.length,
      }));
      setLastUpdatedAt(new Date(cached.ts).toISOString());
      setIsLoadingFiles(false);
      // stale-while-revalidate: render cache immediately and revalidate in background.
      if (!isFreshCache) {
        refreshSelectedFolderFiles(folderKey, { force: true, background: true });
      }
      return;
    }

    if (!background) {
      setIsLoadingFiles(true);
      setFiles([]);
    }
    try {
      const response = await getFiles(folderKey);
      if (requestId !== folderFetchRequestIdRef.current || folderKey !== selectedFolderRef.current) {
        return;
      }
      const normalizedFiles = Array.isArray(response) ? response : [];
      folderFilesCacheRef.current[folderKey] = {
        files: normalizedFiles,
        ts: Date.now(),
      };
      writeSessionCache(scopedCacheKey(DASHBOARD_CACHE_KEYS.folderFilesByFolder), folderFilesCacheRef.current);
      setFiles(normalizedFiles);
      setFolderCounts((prev) => ({
        ...prev,
        [folderKey]: normalizedFiles.length,
      }));
      setLastUpdatedAt(new Date().toISOString());
    } catch (requestError) {
      if (requestId !== folderFetchRequestIdRef.current || folderKey !== selectedFolderRef.current) {
        return;
      }
      setError(fileFetchErrorMessage(requestError));
    } finally {
      if (requestId === folderFetchRequestIdRef.current && folderKey === selectedFolderRef.current) {
        setIsLoadingFiles(false);
      }
    }
  }, []);

  const handleFolderSelect = useCallback(
    (folderKey) => {
      const isSameFolder = selectedFolderRef.current === folderKey;
      selectedFolderRef.current = folderKey;
      setSelectedFolder(folderKey);
      setActivePage("folder");
      if (isSameFolder) {
        refreshSelectedFolderFiles(folderKey, { force: true });
      }
    },
    [refreshSelectedFolderFiles]
  );

  useEffect(() => {
    selectedFolderRef.current = selectedFolder;
    refreshSelectedFolderFiles(selectedFolder);
  }, [selectedFolder, refreshSelectedFolderFiles]);

  useEffect(() => {
    activePageRef.current = activePage;
  }, [activePage]);

  useEffect(() => {
    runFilesByRunIdRef.current = runFilesByRunId;
  }, [runFilesByRunId]);

  useEffect(() => {
    prefetchAllFolderFiles();
  }, [prefetchAllFolderFiles]);

  useEffect(() => {
    let cancelled = false;
    const syncPipelineRunning = async () => {
      try {
        const scheduler = await getScheduler();
        if (!cancelled) {
          setIsPipelineRunning(Boolean(scheduler?.pipeline_status?.is_running));
        }
      } catch {
        if (!cancelled) {
          setIsPipelineRunning(false);
        }
      }
    };
    syncPipelineRunning();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const loadDepartmentContext = async () => {
      try {
        const [dept, status] = await Promise.all([getDepartmentMe(), getDepartmentMicrosoftStatus()]);
        if (!cancelled) {
          setDepartmentName(dept?.name || "");
          setMicrosoftStatus(status);
        }
      } catch {
        if (!cancelled) {
          setDepartmentName("");
          setMicrosoftStatus({ connected: false, connected_email: null });
        }
      }
    };
    loadDepartmentContext();
    return () => {
      cancelled = true;
    };
  }, []);

  const refreshDashboard = useCallback(async ({ full = false } = {}) => {
    setIsLoadingDashboardFiles((dashboardFiles || []).length === 0);
    try {
      const data = await getRuns();
      const nextRuns = Array.isArray(data) ? data : [];
      setRuns(nextRuns);
      writeSessionCache(scopedCacheKey(DASHBOARD_CACHE_KEYS.runs), nextRuns);
      if (nextRuns.length === 0) {
        setDashboardFiles([]);
        writeSessionCache(scopedCacheKey(DASHBOARD_CACHE_KEYS.dashboardFiles), []);
        const updatedAt = new Date().toISOString();
        setLastDashboardUpdatedAt(updatedAt);
        writeSessionCache(scopedCacheKey(DASHBOARD_CACHE_KEYS.dashboardUpdatedAt), updatedAt);
        return;
      }
      // Fast path for live refresh: only fetch missing recent runs.
      const candidateRuns = nextRuns.slice(0, full ? 100 : 20);
      const existingRunFiles = runFilesByRunIdRef.current || {};
      const idsToFetch = candidateRuns
        .map((item) => item.run_id)
        .filter((runId) => full || !existingRunFiles[runId]);
      const settledRows = await Promise.allSettled(idsToFetch.map((runId) => getRunFiles(runId)));
      const fetchedRunFilesById = {};
      settledRows.forEach((entry, idx) => {
        if (entry.status === "fulfilled") {
          fetchedRunFilesById[idsToFetch[idx]] = normalizeRunFiles(entry.value);
        }
      });
      const mergedRunFilesById = { ...existingRunFiles, ...fetchedRunFilesById };
      setRunFilesByRunId(mergedRunFilesById);
      writeSessionCache(scopedCacheKey(DASHBOARD_CACHE_KEYS.runFilesByRunId), mergedRunFilesById);

      const normalized = candidateRuns
        .flatMap((run) => mergedRunFilesById[run.run_id] || [])
        .filter((item) => Boolean(item?.name));
      normalized.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
      const nextDashboardFiles = normalized;
      setDashboardFiles(nextDashboardFiles);
      writeSessionCache(scopedCacheKey(DASHBOARD_CACHE_KEYS.dashboardFiles), nextDashboardFiles);
      const updatedAt = new Date().toISOString();
      setLastDashboardUpdatedAt(updatedAt);
      writeSessionCache(scopedCacheKey(DASHBOARD_CACHE_KEYS.dashboardUpdatedAt), updatedAt);
    } catch {
      setError("Failed to refresh dashboard.");
    } finally {
      setIsLoadingDashboardFiles(false);
    }
  }, [dashboardFiles]);

  useEffect(() => {
    let cancelled = false;
    const fetchRuns = async () => {
      setIsLoadingRuns((runs || []).length === 0);
      try {
        const data = await getRuns();
        if (!cancelled) {
          const nextRuns = Array.isArray(data) ? data : [];
          setRuns(nextRuns);
          writeSessionCache(scopedCacheKey(DASHBOARD_CACHE_KEYS.runs), nextRuns);
        }
      } catch {
        if (!cancelled) {
          setError("Failed to fetch runs.");
        }
      } finally {
        if (!cancelled) {
          setIsLoadingRuns(false);
        }
      }
    };
    fetchRuns();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    refreshDashboard({ full: true });
  }, []);

  useEffect(() => {
    if (!isRunNowPending) {
      return undefined;
    }
    let cancelled = false;
    const pollPipelineStatus = async () => {
      if (document.visibilityState === "hidden") {
        return;
      }
      try {
        const scheduler = await getScheduler();
        if (cancelled) {
          return;
        }
        const running = Boolean(scheduler?.pipeline_status?.is_running);
        setIsPipelineRunning(running);
        if (running) {
          hasSeenPipelineRunningRef.current = true;
        }
        if (
          !running &&
          isRunNowPendingRef.current &&
          hasSeenPipelineRunningRef.current
        ) {
          isRunNowPendingRef.current = false;
          hasSeenPipelineRunningRef.current = false;
          setIsRunNowPending(false);
          setIsPipelineRunning(false);
          setSuccess({ file: "" });
          refreshDashboard();
          refreshFolderCounts();
          if (activePageRef.current === "folder") {
            refreshSelectedFolderFiles(selectedFolderRef.current, { force: true });
          }
        }
      } catch {
        if (!cancelled && isRunNowPendingRef.current) {
          setError("Failed to fetch pipeline status.");
          isRunNowPendingRef.current = false;
          hasSeenPipelineRunningRef.current = false;
          setIsRunNowPending(false);
          setIsPipelineRunning(false);
        }
      }
    };
    pollPipelineStatus();
    const timer = window.setInterval(pollPipelineStatus, 3000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [isRunNowPending, refreshDashboard, refreshFolderCounts, refreshSelectedFolderFiles]);

  useEffect(() => {
    let cancelled = false;
    const fetchSettings = async () => {
      try {
        const data = await getSettings();
        if (!cancelled && data) {
          setSettings({
            eod_time: data.eod_time || "14:00",
            enabled: Boolean(data.enabled),
          });
          setEodTime(data.eod_time || "14:00");
        }
      } catch {
        if (!cancelled) {
          setError("Failed to fetch notification settings.");
        }
      }
    };
    fetchSettings();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (!showReportModal) {
      return () => {
        cancelled = true;
      };
    }
    const syncReportSettings = async () => {
      setIsLoadingReportSettings(true);
      try {
        const data = await getSettings();
        if (!cancelled && data) {
          setSettings({
            eod_time: data.eod_time || "14:00",
            enabled: Boolean(data.enabled),
          });
          setEodTime(data.eod_time || "14:00");
        }
      } catch {
        if (!cancelled) {
          setError("Failed to fetch notification settings.");
        }
      } finally {
        if (!cancelled) {
          setIsLoadingReportSettings(false);
        }
      }
    };
    syncReportSettings();
    return () => {
      cancelled = true;
    };
  }, [showReportModal]);

  useEffect(() => {
    let cancelled = false;
    const fetchEmails = async () => {
      try {
        const data = await getEmailGroup();
        if (!cancelled) {
          setEmails(Array.isArray(data) ? data : []);
        }
      } catch {
        if (!cancelled) {
          setError("Failed to fetch notification emails.");
        }
      }
    };
    fetchEmails();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!emailToast) {
      return undefined;
    }
    const timer = window.setTimeout(() => setEmailToast(""), 2500);
    return () => window.clearTimeout(timer);
  }, [emailToast]);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (!e.target.closest("#profile-menu")) {
        setShowProfileMenu(false);
      }
    };
    document.addEventListener("click", handleClickOutside);
    return () => document.removeEventListener("click", handleClickOutside);
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (!showModal) {
      return () => {
        cancelled = true;
      };
    }

    const syncScheduleFromBackend = async () => {
      try {
        const scheduler = await getScheduler();
        const intervalSeconds = Number(scheduler?.interval);
        if (cancelled || Number.isNaN(intervalSeconds) || !Number.isFinite(intervalSeconds) || intervalSeconds <= 0) {
          return;
        }

        // Convert backend interval -> UI state
        if (intervalSeconds % 60 === 0) {
          const minutes = intervalSeconds / 60;
          if (intervalSeconds % 3600 === 0 && minutes / 60 >= 1 && Number.isInteger(minutes / 60)) {
            const hours = minutes / 60;
            if (intervalOptions.includes(hours)) {
              setValue(hours);
              setUnit("hours");
              setIsCustom(false);
              return;
            }
          }
          if (intervalOptions.includes(minutes)) {
            setValue(minutes);
            setUnit("minutes");
            setIsCustom(false);
            return;
          }
          setValue(minutes);
          setUnit("minutes");
          setIsCustom(true);
          return;
        }

        setValue(intervalSeconds);
        setUnit("seconds");
        setIsCustom(true);
      } catch {
        // ignore scheduler fetch errors
      }
    };

    syncScheduleFromBackend();
    return () => {
      cancelled = true;
    };
  }, [showModal]);

  const handleFileSelect = async (file) => {
    setSelectedFile(file);
    setFileContent(null);
    setXlsxContent(null);
    revokeObjectUrl(docPreviewUrl);
    revokeObjectUrl(pdfBlobUrl);
    setDocPreviewUrl("");
    setPdfBlobUrl("");
    setIsViewerOpen(true);
    setIsOpeningFile(true);
    const isJsonFile =
      file?.name?.toLowerCase().endsWith(".json") || file?.mime_type === "application/json";
    const isXlsxFile =
      file?.name?.toLowerCase().endsWith(".xlsx") ||
      file?.mime_type === "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
    const isDocFile =
      file?.name?.toLowerCase().endsWith(".docx") ||
      file?.name?.toLowerCase().endsWith(".doc") ||
      file?.mime_type === "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ||
      file?.mime_type === "application/msword";
    const isPdfFile =
      file?.name?.toLowerCase().endsWith(".pdf") || file?.mime_type === "application/pdf";
    if (!isJsonFile) {
      if (isXlsxFile) {
        setIsLoadingContent(true);
        setError("");
        try {
          const buffer = await getFileContentArrayBuffer(file.id);
          setXlsxContent(buffer);
        } catch (requestError) {
          setError(requestError?.response?.data?.detail || "Failed to load XLSX file.");
        } finally {
          setIsLoadingContent(false);
          setIsOpeningFile(false);
        }
        return;
      }
      if (isDocFile) {
        setError("");
        setIsLoadingContent(true);
        try {
          const blobUrl = await fetchAuthenticatedPreviewPdfBlobUrl(file.id);
          setDocPreviewUrl(blobUrl);
        } catch (requestError) {
          setError(requestError?.response?.data?.detail || "Failed to load document preview.");
        } finally {
          setIsLoadingContent(false);
          setIsOpeningFile(false);
        }
        return;
      }
      if (isPdfFile) {
        setError("");
        setIsLoadingContent(true);
        try {
          const blobUrl = await fetchAuthenticatedFileBlobUrl(file.id);
          setPdfBlobUrl(blobUrl);
        } catch (requestError) {
          setError(requestError?.response?.data?.detail || "Failed to load PDF file.");
        } finally {
          setIsLoadingContent(false);
          setIsOpeningFile(false);
        }
        return;
      }
      setIsOpeningFile(false);
      return;
    }
    setIsLoadingContent(true);
    setError("");
    setFolderAccessibilityDetail(null);
    setIsLoadingFolderAccessibilityDetail(false);
    try {
      const content = await getFileContent(file.id);
      setFileContent(content);
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Failed to load file content.");
    } finally {
      setIsLoadingContent(false);
      setIsOpeningFile(false);
    }
  };

  const closeViewer = () => {
    revokeObjectUrl(docPreviewUrl);
    revokeObjectUrl(pdfBlobUrl);
    setIsViewerOpen(false);
    setSelectedFile(null);
    setFileContent(null);
    setXlsxContent(null);
    setIsOpeningFile(false);
    setDocPreviewUrl("");
    setPdfBlobUrl("");
    setFolderAccessibilityDetail(null);
    setIsLoadingFolderAccessibilityDetail(false);
  };

  const intervalSeconds =
    unit === "hours" ? value * 3600 : unit === "minutes" ? value * 60 : value;
  const isSaveDisabled =
    isSavingSchedule ||
    showRunningState ||
    value < 1 ||
    Number.isNaN(intervalSeconds) ||
    !Number.isFinite(intervalSeconds) ||
    intervalSeconds < 60;

  const handleRunNow = async () => {
    setError("");
    isRunNowPendingRef.current = true;
    hasSeenPipelineRunningRef.current = false;
    setIsRunNowPending(true);
    setIsPipelineRunning(false);
    try {
      await runNow();
      hasSeenPipelineRunningRef.current = true;
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Failed to start processing.");
      isRunNowPendingRef.current = false;
      hasSeenPipelineRunningRef.current = false;
      setIsRunNowPending(false);
      setIsPipelineRunning(false);
    }
  };

  const handleScheduleSave = async () => {
    if (isSaveDisabled) {
      return;
    }
    setIsSavingSchedule(true);
    try {
      await updateScheduler(intervalSeconds);
      // Re-sync from backend after save to ensure persistence.
      try {
        const scheduler = await getScheduler();
        const savedSeconds = Number(scheduler?.interval);
        if (Number.isFinite(savedSeconds) && savedSeconds > 0) {
          if (savedSeconds % 60 === 0) {
            const minutes = savedSeconds / 60;
            if (savedSeconds % 3600 === 0 && minutes / 60 >= 1 && Number.isInteger(minutes / 60)) {
              const hours = minutes / 60;
              setValue(hours);
              setUnit("hours");
              setIsCustom(!intervalOptions.includes(hours));
            } else {
              setValue(minutes);
              setUnit("minutes");
              setIsCustom(!intervalOptions.includes(minutes));
            }
          } else {
            setValue(savedSeconds);
            setUnit("seconds");
            setIsCustom(true);
          }
        }
      } catch {
        // ignore refetch errors
      }
      setShowModal(false);
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Failed to update schedule.");
    } finally {
      setIsSavingSchedule(false);
    }
  };

  const handleLogout = () => {
    clearDashboardSessionCache();
    setAppJwt(null);
    window.location.href = "/login";
  };

  const parsedEmailCandidates = useMemo(
    () =>
      emailInput
        .split(",")
        .map((item) => item.trim().toLowerCase())
        .filter(Boolean),
    [emailInput]
  );

  const invalidEmailCandidates = useMemo(
    () => parsedEmailCandidates.filter((candidate) => !EMAIL_PATTERN.test(candidate)),
    [parsedEmailCandidates]
  );

  const canAddEmails =
    parsedEmailCandidates.length > 0 && invalidEmailCandidates.length === 0 && !isSavingEmail;

  const handleAddEmails = async () => {
    if (!canAddEmails) {
      return;
    }
    setIsSavingEmail(true);
    try {
      const existingEmails = new Set((emails || []).map((item) => (item?.email || "").toLowerCase()));
      const toCreate = parsedEmailCandidates.filter((email) => !existingEmails.has(email));
      if (toCreate.length === 0) {
        setEmailToast("All entered emails already exist.");
        setEmailInput("");
        return;
      }
      const createdRows = await Promise.all(toCreate.map((email) => addEmailGroup(email)));
      setEmails((prev) => [...prev, ...createdRows]);
      setEmailInput("");
      setEmailToast(`Added ${createdRows.length} recipient${createdRows.length > 1 ? "s" : ""}.`);
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Failed to add email.");
    } finally {
      setIsSavingEmail(false);
    }
  };

  const handleDeleteEmail = async (id) => {
    setDeletingEmailId(id);
    try {
      await deleteEmailGroup(id);
      setEmails((prev) => prev.filter((item) => item.id !== id));
      setEmailToast("Recipient removed.");
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Failed to remove email.");
    } finally {
      setDeletingEmailId("");
    }
  };

  const handleDownloadFile = useCallback(async (fileId, fileName) => {
    if (!fileId) {
      return;
    }
    setDownloadingFileId(fileId);
    setError("");
    try {
      await downloadAuthenticatedFile(fileId, fileName || "download");
    } catch (requestError) {
      const detail = requestError?.response?.data?.detail;
      setError(
        typeof detail === "string" ? detail : requestError?.message || "Failed to download file."
      );
    } finally {
      setDownloadingFileId(null);
    }
  }, []);

  const handleOpenFileInNewTab = useCallback(async (fileId) => {
    if (!fileId) {
      return;
    }
    setError("");
    try {
      await openAuthenticatedFileInNewTab(fileId);
    } catch (requestError) {
      const detail = requestError?.response?.data?.detail;
      setError(
        typeof detail === "string" ? detail : requestError?.message || "Failed to open file."
      );
    }
  }, []);

  const handleDownloadAccessibilityXlsx = useCallback(async (pdfId, jsonId, jsonFileName) => {
    if (!pdfId || !jsonId) {
      return;
    }
    setIsExportingAccessibilityReport(true);
    setError("");
    try {
      const blob = await downloadAccessibilityReportXlsx(pdfId, jsonId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const raw = jsonFileName && String(jsonFileName).trim() ? String(jsonFileName).trim() : "";
      const base =
        stemFromAccessibilityJsonFileName(raw) || (raw ? raw.replace(/\.json$/i, "") : "") || "document";
      const baseForName = base.replace(/\.pdf$/i, "") || base;
      const safe = baseForName.replace(/[^\w.-]+/g, "_").replace(/^\.+$/, "") || "document";
      a.download = `${safe}_accessibility_report.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      setError("Failed to download accessibility Excel report.");
    } finally {
      setIsExportingAccessibilityReport(false);
    }
  }, []);

  const openFile = async (type, url, title, options = {}) => {
    const { companionPdfUrl, jsonFileName } = options;
    const resolvedUrl = url && url.startsWith("http") ? url : `http://localhost:8000${url || ""}`;
    let companionPdfId = "";
    if (companionPdfUrl) {
      try {
        const companionResolved =
          companionPdfUrl && companionPdfUrl.startsWith("http")
            ? companionPdfUrl
            : `http://localhost:8000${companionPdfUrl || ""}`;
        const companionParsed = new URL(companionResolved, window.location.origin);
        companionPdfId = companionParsed.searchParams.get("id") || "";
      } catch {
        companionPdfId = "";
      }
    }
    setAccessibilityDetail(null);
    setIsLoadingAccessibilityDetail(false);
    setViewerJson(null);
    setViewerXlsx(null);
    if (!url) {
      setViewer(null);
      setIsViewerLoading(false);
      return;
    }
    let fileId = "";
    try {
      const parsed = new URL(resolvedUrl, window.location.origin);
      fileId = parsed.searchParams.get("id") || "";
    } catch {
      setError("Failed to open output file.");
      setIsViewerLoading(false);
      return;
    }
    if (!fileId) {
      setError("Failed to open output file.");
      setIsViewerLoading(false);
      return;
    }
    const pdfIdForViewer = type === "pdf" ? fileId : companionPdfId;
    const jsonIdForViewer = type === "json" ? fileId : "";
    setViewer({
      type,
      url: resolvedUrl,
      blobUrl: "",
      title: title || "",
      pdfId: pdfIdForViewer,
      jsonId: jsonIdForViewer,
      jsonFileName: type === "json" ? jsonFileName || "" : "",
    });
    setIsViewerLoading(true);
    if (type === "pdf") {
      try {
        const blobUrl = await fetchAuthenticatedFileBlobUrl(fileId);
        setViewer((prev) => (prev ? { ...prev, blobUrl } : prev));
      } catch {
        setError("Failed to open output file.");
        setViewer(null);
      } finally {
        setIsViewerLoading(false);
      }
      return;
    }
    try {
      if (type === "json") {
        const content = await getFileContent(fileId);
        setViewerJson(content);
      } else if (type === "xlsx") {
        const buffer = await getFileContentArrayBuffer(fileId);
        setViewerXlsx(buffer);
      }
    } catch {
      setError("Failed to open output file.");
    } finally {
      setIsViewerLoading(false);
    }
  };

  const closeRunOutputViewer = () => {
    if (viewer?.blobUrl) {
      revokeObjectUrl(viewer.blobUrl);
    }
    setViewer(null);
    setViewerJson(null);
    setViewerXlsx(null);
    setIsViewerLoading(false);
    setAccessibilityDetail(null);
    setIsLoadingAccessibilityDetail(false);
  };

  const handleRunRowClick = async (runId) => {
    if (expandedRunId === runId) {
      setExpandedRunId("");
      return;
    }
    setExpandedRunId(runId);
    if (runFilesByRunId[runId]) {
      return;
    }
    setIsLoadingRunFiles(true);
    try {
      const files = await getRunFiles(runId);
      const normalizedFiles = normalizeRunFiles(files);
      setRunFilesByRunId((prev) => {
        const next = { ...prev, [runId]: normalizedFiles };
        writeSessionCache(scopedCacheKey(DASHBOARD_CACHE_KEYS.runFilesByRunId), next);
        return next;
      });
    } catch {
      setError("Failed to fetch run file details.");
    } finally {
      setIsLoadingRunFiles(false);
    }
  };

  const handleSaveSettings = async () => {
    setIsSavingSettings(true);
    try {
      const payload = { ...settings, eod_time: eodTime };
      const data = await saveSettings(payload);
      setSettings({
        eod_time: data?.eod_time || settings.eod_time,
        enabled: Boolean(data?.enabled),
      });
      setEodTime(data?.eod_time || eodTime);
      setEmailToast("Notification settings saved.");
      return true;
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Failed to save settings.");
      return false;
    } finally {
      setIsSavingSettings(false);
    }
  };

  const isPdfSelected =
    selectedFile?.name?.toLowerCase().endsWith(".pdf") || selectedFile?.mime_type === "application/pdf";
  const isJsonSelected =
    selectedFile?.name?.toLowerCase().endsWith(".json") || selectedFile?.mime_type === "application/json";
  const isXlsxSelected =
    selectedFile?.name?.toLowerCase().endsWith(".xlsx") ||
    selectedFile?.mime_type === "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
  const isDocSelected =
    selectedFile?.name?.toLowerCase().endsWith(".docx") ||
    selectedFile?.name?.toLowerCase().endsWith(".doc") ||
    selectedFile?.mime_type ===
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ||
    selectedFile?.mime_type === "application/msword";

  const summary = useMemo(() => {
    if (!fileContent || typeof fileContent !== "object" || Array.isArray(fileContent)) {
      return EMPTY_SUMMARY;
    }
    const rawSummary = fileContent.Summary;
    if (!rawSummary || typeof rawSummary !== "object") {
      return EMPTY_SUMMARY;
    }
    return {
      passed: Number(rawSummary.Passed || 0),
      failed: Number(rawSummary.Failed || 0),
      needsManual: Number(rawSummary["Needs manual check"] || 0),
      passedManually: Number(rawSummary["Passed manually"] || 0),
      failedManually: Number(rawSummary["Failed manually"] || 0),
      skipped: Number(rawSummary.Skipped || 0),
      description: rawSummary.Description || "",
    };
  }, [fileContent]);

  const filteredFiles = useMemo(() => {
    const q = (searchQuery || "").trim().toLowerCase();
    if (!q) {
      return files;
    }
    return (files || []).filter((f) => (f?.name || "").toLowerCase().includes(q));
  }, [files, searchQuery]);

  const fileCount = (files || []).length;
  const filteredCount = (filteredFiles || []).length;
  const dashboardLastUpdatedLabel = lastDashboardUpdatedAt ? formatRelativeTime(lastDashboardUpdatedAt) : "-";
  const runsPageSize = 20;
  const runsTotalPages = Math.max(1, Math.ceil((runs?.length || 0) / runsPageSize));
  const paginatedRuns = useMemo(
    () => (runs || []).slice((runsPage - 1) * runsPageSize, runsPage * runsPageSize),
    [runs, runsPage]
  );

  const jsonSections = useMemo(() => {
    if (!fileContent || typeof fileContent !== "object" || Array.isArray(fileContent)) {
      return [];
    }
    const detailed = fileContent["Detailed Report"];
    if (!detailed || typeof detailed !== "object" || Array.isArray(detailed)) {
      return [];
    }
    return Object.entries(detailed).filter(([, value]) => Array.isArray(value));
  }, [fileContent]);

  const folderJsonCompanionPdfId = useMemo(() => {
    if (!isViewerOpen || !isJsonSelected || !selectedFile?.name) {
      return "";
    }
    return findCompanionTaggedPdfId(selectedFile.name, files);
  }, [isViewerOpen, isJsonSelected, selectedFile?.name, files]);

  const viewerSummary = useMemo(() => {
    if (!viewerJson || typeof viewerJson !== "object" || Array.isArray(viewerJson)) {
      return EMPTY_SUMMARY;
    }
    const rawSummary = viewerJson.Summary;
    if (!rawSummary || typeof rawSummary !== "object") {
      return EMPTY_SUMMARY;
    }
    return {
      passed: Number(rawSummary.Passed || 0),
      failed: Number(rawSummary.Failed || 0),
      needsManual: Number(rawSummary["Needs manual check"] || 0),
      passedManually: Number(rawSummary["Passed manually"] || 0),
      failedManually: Number(rawSummary["Failed manually"] || 0),
      skipped: Number(rawSummary.Skipped || 0),
      description: rawSummary.Description || "",
    };
  }, [viewerJson]);

  const viewerJsonSections = useMemo(() => {
    if (!viewerJson || typeof viewerJson !== "object" || Array.isArray(viewerJson)) {
      return [];
    }
    const detailed = viewerJson["Detailed Report"];
    if (!detailed || typeof detailed !== "object" || Array.isArray(detailed)) {
      return [];
    }
    return Object.entries(detailed).filter(([, value]) => Array.isArray(value));
  }, [viewerJson]);

  const accessibilityLocationHints = useMemo(
    () => buildAccessibilityLocationHints(accessibilityDetail),
    [accessibilityDetail]
  );

  const folderAccessibilityLocationHints = useMemo(
    () => buildAccessibilityLocationHints(folderAccessibilityDetail),
    [folderAccessibilityDetail]
  );

  useEffect(() => {
    if (!viewer || viewer.type !== "json" || !viewer.pdfId || !viewer.jsonId) {
      setAccessibilityDetail(null);
      setIsLoadingAccessibilityDetail(false);
      return undefined;
    }
    let cancelled = false;
    setIsLoadingAccessibilityDetail(true);
    getAccessibilityDetail(viewer.pdfId, viewer.jsonId)
      .then((data) => {
        if (!cancelled) {
          setAccessibilityDetail(data);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setAccessibilityDetail(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoadingAccessibilityDetail(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [viewer?.type, viewer?.pdfId, viewer?.jsonId]);

  useEffect(() => {
    if (!isViewerOpen || !isJsonSelected || !selectedFile?.id || !fileContent || typeof fileContent !== "object" || Array.isArray(fileContent)) {
      setFolderAccessibilityDetail(null);
      setIsLoadingFolderAccessibilityDetail(false);
      return undefined;
    }
    if (!folderJsonCompanionPdfId) {
      setFolderAccessibilityDetail(null);
      setIsLoadingFolderAccessibilityDetail(false);
      return undefined;
    }
    let cancelled = false;
    setIsLoadingFolderAccessibilityDetail(true);
    getAccessibilityDetail(folderJsonCompanionPdfId, selectedFile.id)
      .then((data) => {
        if (!cancelled) {
          setFolderAccessibilityDetail(data);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setFolderAccessibilityDetail(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoadingFolderAccessibilityDetail(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [
    isViewerOpen,
    isJsonSelected,
    selectedFile?.id,
    fileContent,
    folderJsonCompanionPdfId,
  ]);

  useEffect(() => {
    setRunsPage(1);
  }, [runs]);

  useEffect(() => {
    if (runsPage > runsTotalPages) {
      setRunsPage(runsTotalPages);
    }
  }, [runsPage, runsTotalPages]);

  return (
    <div className="flex h-screen">
      <Sidebar
        activePage={activePage}
        setActivePage={setActivePage}
        selectedFolder={selectedFolder}
        setSelectedFolder={setSelectedFolder}
        folderCounts={folderCounts}
        onFolderSelect={handleFolderSelect}
        userRole={jwtPayload?.role}
      />

      <main className="flex-1 min-w-0 bg-gray-100 overflow-y-auto">
        <Navbar
          departmentName={departmentName}
          isRunning={showRunningState}
          onRunNow={handleRunNow}
          onOpenSchedule={() => setShowModal(true)}
          onOpenEmailModal={() => setShowEmailModal(true)}
          emailCount={emails.length}
          showProfileMenu={showProfileMenu}
          setShowProfileMenu={setShowProfileMenu}
          onLogout={handleLogout}
        />

        <div className="px-6 pb-6 pt-4">
        {microsoftStatus?.connected === false && (
          <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            <p className="font-medium">OneDrive folders unavailable</p>
            <p className="mt-1 text-amber-800">
              Microsoft OneDrive is not connected for this department. Ask your administrator to open the Admin
              panel, use Connect on this department&apos;s row, then refresh this page.
            </p>
          </div>
        )}

        {activePage === "dashboard" && (
          <FileTable
            isLoadingDashboardFiles={isLoadingDashboardFiles}
            dashboardFiles={dashboardFiles}
            openFile={openFile}
            lastUpdatedLabel={dashboardLastUpdatedLabel}
          />
        )}

        {activePage === "folder" && (
          <section className="bg-white shadow rounded-xl p-4">
            <div className="flex items-start justify-between gap-4 mb-4">
              <div>
                <h2 className="text-lg font-semibold capitalize">
                  {selectedFolder} Files{" "}
                  <span className="text-sm font-normal text-gray-500">
                    ({filteredCount}{searchQuery ? ` of ${fileCount}` : ""})
                  </span>
                </h2>
                <p className="text-xs text-gray-500 mt-1">
                  Last updated: {lastUpdatedAt ? formatRelativeTime(lastUpdatedAt) : "-"}
                </p>
              </div>
              <div className="w-full max-w-sm">
                <input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search files..."
                  className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200"
                />
              </div>
            </div>
            {isLoadingFiles && (
              <div className="flex items-center gap-2 text-sm text-gray-500 mb-2">
                <span className="inline-block w-4 h-4 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
                Loading...
              </div>
            )}
            {!isLoadingFiles && filteredFiles.length === 0 && (
              <div className="border border-dashed rounded-xl p-8 text-center bg-gray-50">
                <div className="text-lg font-semibold text-gray-800">{error ? "Could not load folder files" : "No files found"}</div>
                <div className={`text-sm mt-1 ${error ? "text-red-600" : "text-gray-500"}`}>
                  {error
                    ? error
                    : searchQuery
                      ? "Try a different search term."
                      : "This folder is currently empty."}
                </div>
              </div>
            )}
            <div className="space-y-2">
              {filteredFiles.map((file) => (
                <div key={file.id} className="group flex items-center justify-between p-3 rounded-lg border bg-white hover:bg-gray-50 hover:border-gray-300 transition cursor-pointer" onClick={() => handleFileSelect(file)} role="button" tabIndex={0} onKeyDown={(event) => event.key === "Enter" && handleFileSelect(file)}>
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-9 h-9 rounded-lg bg-gray-100 flex items-center justify-center text-lg">{fileTypeIcon(file)}</div>
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-gray-900 break-all">{file.name}</div>
                      <div className="text-xs text-gray-500 flex items-center gap-3 mt-0.5">
                        <span className="uppercase">{(file?.mime_type || "file").split("/").pop() || "file"}</span>
                        <span>•</span>
                        <span>{formatRelativeTime(file?.last_modified)}</span>
                        <span>•</span>
                        <span>{formatBytes(file?.size_bytes)}</span>
                      </div>
                    </div>
                  </div>
                  <div className="hidden sm:flex gap-2 opacity-0 group-hover:opacity-100 transition">
                    <button type="button" onClick={(e) => { e.stopPropagation(); handleFileSelect(file); }} className="px-3 py-1.5 rounded bg-blue-600 hover:bg-blue-700 text-white text-sm">View</button>
                    <button
                      type="button"
                      disabled={downloadingFileId === file.id}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDownloadFile(file.id, file.name);
                      }}
                      className="px-3 py-1.5 rounded bg-gray-800 hover:bg-gray-900 disabled:opacity-60 text-white text-sm"
                    >
                      {downloadingFileId === file.id ? "Downloading…" : "Download"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {activePage === "dept-settings" && <DepartmentSettingsPanel />}

        {activePage === "runs" && (
          <>
            <section className="bg-white shadow rounded-xl p-4">
              <div className="flex justify-between items-center mb-4">
                <div>
                  <h2 className="text-lg font-semibold">Run History</h2>
                  <p className="text-xs text-gray-500">Report: {settings?.enabled ? `Daily at ${eodTime}` : "Disabled"}</p>
                </div>
                <button
                  type="button"
                  onClick={() => setShowReportModal(true)}
                  className="btn-secondary flex items-center gap-2"
                >
                  <FileText size={16} />
                  Daily Report
                </button>
              </div>
              {isLoadingRuns ? (
                <p className="text-sm text-gray-500">Loading runs...</p>
              ) : runs.length === 0 ? (
                <p className="text-sm text-gray-500">No runs available.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm border">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="text-left p-2 border">Run ID</th>
                        <th className="text-left p-2 border">Time</th>
                        <th className="text-left p-2 border">Duration</th>
                        <th className="text-left p-2 border">Files</th>
                        <th className="text-left p-2 border">Success</th>
                        <th className="text-left p-2 border">Failed</th>
                        <th className="text-left p-2 border">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {paginatedRuns.map((run) => {
                        const runFiles = runFilesByRunId[run.run_id] || [];
                        const isExpanded = expandedRunId === run.run_id;
                        return (
                          <React.Fragment key={run.run_id}>
                            <tr
                              className="cursor-pointer hover:bg-gray-50"
                              onClick={() => handleRunRowClick(run.run_id)}
                            >
                              <td className="p-2 border break-all">{run.run_id}</td>
                              <td className="p-2 border">{formatLocalDateTime(run.start_time)}</td>
                              <td className="p-2 border">{run.duration || "-"}</td>
                              <td className="p-2 border">{run.total_files ?? 0}</td>
                              <td className="p-2 border text-green-600 font-medium">{run.success_count ?? 0}</td>
                              <td className="p-2 border text-red-600 font-medium">{run.failure_count ?? 0}</td>
                              <td className="p-2 border">
                                <span
                                  className={`px-2 py-1 rounded text-xs inline-flex items-center gap-2 ${
                                    run.status === "COMPLETED"
                                      ? "bg-green-100 text-green-700"
                                      : "bg-red-100 text-red-700"
                                  }`}
                                >
                                  {run.status === "COMPLETED" ? <CheckCircle size={14} /> : <XCircle size={14} />}
                                  {run.status}
                                </span>
                              </td>
                            </tr>
                            {isExpanded && (
                              <tr>
                                <td colSpan={7} className="p-2 border bg-gray-50">
                                  {isLoadingRunFiles && !runFilesByRunId[run.run_id] ? (
                                    <p className="text-xs text-gray-500">Loading file details...</p>
                                  ) : runFiles.length === 0 ? (
                                    <p className="text-xs text-gray-500">No file details found.</p>
                                  ) : (
                                    <table className="w-full text-xs border bg-white">
                                      <thead className="bg-gray-50">
                                        <tr>
                                          <th className="text-left p-2 border">File Name</th>
                                          <th className="text-left p-2 border">Status</th>
                                          <th className="text-left p-2 border">Failure Reason</th>
                                          <th className="text-left p-2 border">Accessibility</th>
                                          <th className="text-left p-2 border">Outputs</th>
                                        </tr>
                                      </thead>
                                      <tbody>
                                        {runFiles.map((file, idx) => (
                                          <tr key={`${run.run_id}-${idx}`} className="border-t align-top">
                                            {(() => {
                                              const isFailed = file?.status === "FAILED";
                                              const canOpenPdf = Boolean(file?.outputs?.pdf_url) && !isFailed;
                                              const canOpenJson = Boolean(file?.outputs?.json_url) && !isFailed;
                                              const canOpenXlsx = Boolean(file?.outputs?.xlsx_url) && !isFailed;
                                              const unavailableTitle = isFailed ? "Not available for failed files" : "Output not available";
                                              return (
                                                <>
                                                  <td className="p-2 border break-all">{file.name}</td>
                                                  <td className="p-2 border">
                                                    <span className={`px-2 py-1 text-xs rounded inline-flex ${
                                                      file.status === "COMPLETED" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
                                                    }`}>
                                                      {file.status || "UNKNOWN"}
                                                    </span>
                                                  </td>
                                                  <td className="p-2 border text-xs text-red-600 max-w-[420px]">
                                                    {file.status === "FAILED" ? (
                                                      <span title={file?.error || "Unknown failure reason"} className="break-words">
                                                        {file?.error || "Unknown failure reason"}
                                                      </span>
                                                    ) : (
                                                      <span className="text-gray-400">-</span>
                                                    )}
                                                  </td>
                                                  <td className="p-2 border text-gray-500">
                                                    <div className="flex gap-2 text-xs">
                                                      <span className="text-green-600">{"\u2714"} {file.accessibility?.passed || 0}</span>
                                                      <span className="text-red-600">{"\u2716"} {file.accessibility?.failed || 0}</span>
                                                      <span className="text-yellow-600">{"\u26A0"} {file.accessibility?.manual || 0}</span>
                                                    </div>
                                                  </td>
                                                  <td className="p-2 border">
                                                    <div className="flex gap-2">
                                                      <button
                                                        type="button"
                                                        title={canOpenPdf ? "View Tagged PDF" : unavailableTitle}
                                                        disabled={!canOpenPdf}
                                                        onClick={(event) => {
                                                          event.stopPropagation();
                                                          openFile("pdf", file?.outputs?.pdf_url, "Tagged PDF");
                                                        }}
                                                        className="px-2 py-1 text-xs bg-gray-100 rounded hover:bg-gray-200 disabled:opacity-40 disabled:cursor-not-allowed inline-flex items-center gap-1"
                                                      >
                                                        <FileText size={14} />
                                                        Tagged PDF
                                                      </button>
                                                      <button
                                                        type="button"
                                                        title={canOpenJson ? "View Accessibility Report" : unavailableTitle}
                                                        disabled={!canOpenJson}
                                                        onClick={(event) => {
                                                          event.stopPropagation();
                                                          openFile("json", file?.outputs?.json_url, "Accessibility Report", {
                                                            companionPdfUrl: file?.outputs?.pdf_url,
                                                            jsonFileName: file?.name,
                                                          });
                                                        }}
                                                        className="px-2 py-1 text-xs bg-gray-100 rounded hover:bg-gray-200 disabled:opacity-40 disabled:cursor-not-allowed inline-flex items-center gap-1"
                                                      >
                                                        <Code size={14} />
                                                        Accessibility Report
                                                      </button>
                                                      <button
                                                        type="button"
                                                        title={canOpenXlsx ? "View Tagging Report" : unavailableTitle}
                                                        disabled={!canOpenXlsx}
                                                        onClick={(event) => {
                                                          event.stopPropagation();
                                                          openFile("xlsx", file?.outputs?.xlsx_url, "Tagging Report");
                                                        }}
                                                        className="px-2 py-1 text-xs bg-gray-100 rounded hover:bg-gray-200 disabled:opacity-40 disabled:cursor-not-allowed inline-flex items-center gap-1"
                                                      >
                                                        <Table size={14} />
                                                        Tagging Report
                                                      </button>
                                                    </div>
                                                    {!canOpenPdf &&
                                                      !canOpenJson &&
                                                      !canOpenXlsx && (
                                                        <span className="text-gray-400 text-xs mt-1 inline-block">No outputs available</span>
                                                      )}
                                                  </td>
                                                </>
                                              );
                                            })()}
                                          </tr>
                                        ))}
                                      </tbody>
                                    </table>
                                  )}
                                </td>
                              </tr>
                            )}
                          </React.Fragment>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
              {!isLoadingRuns && runs.length > 0 && (
                <div className="flex justify-between items-center mt-4">
                  <button
                    type="button"
                    disabled={runsPage === 1}
                    onClick={() => setRunsPage((prev) => prev - 1)}
                    className="px-3 py-1 text-sm rounded bg-gray-100 hover:bg-gray-200 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Prev
                  </button>
                  <span className="text-sm text-gray-600">
                    Page {runsPage} of {runsTotalPages}
                  </span>
                  <button
                    type="button"
                    disabled={runsPage >= runsTotalPages}
                    onClick={() => setRunsPage((prev) => prev + 1)}
                    className="px-3 py-1 text-sm rounded bg-gray-100 hover:bg-gray-200 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Next
                  </button>
                </div>
              )}
            </section>
          </>
        )}
        </div>
      </main>

      {showModal && (
        <div
          className="fixed inset-0 bg-black bg-opacity-40 flex items-center justify-center z-50"
          onClick={() => setShowModal(false)}
          role="presentation"
        >
          <div className="bg-white rounded-xl p-6 w-96 shadow-lg" onClick={(e) => e.stopPropagation()} role="presentation">
            <h3 className="text-lg font-semibold mb-4">Set Schedule Interval</h3>

            <p className="text-sm text-gray-500 mb-2">
              Current: runs every {value} {unit}
            </p>

            {!isCustom ? (
              <div className="flex items-center gap-2">
                <span className="text-sm text-slate-700">Every</span>
                <select
                  value={value}
                  onChange={(event) => {
                    setValue(Number(event.target.value));
                    setIsCustom(false);
                  }}
                  className="border p-2 rounded"
                >
                  {intervalOptions.map((v) => (
                    <option key={v} value={v}>
                      {v}
                    </option>
                  ))}
                </select>
                <select
                  value={unit}
                  onChange={(event) => setUnit(event.target.value)}
                  className="border p-2 rounded"
                >
                  <option value="minutes">minutes</option>
                  <option value="hours">hours</option>
                </select>
              </div>
            ) : (
              <>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-slate-700">Every</span>
                  <input
                    type="number"
                    value={value}
                    min={1}
                    onChange={(event) => setValue(Number(event.target.value))}
                    placeholder="Enter value"
                    className="border p-2 rounded w-full"
                  />
                  <select
                    value={unit}
                    onChange={(event) => setUnit(event.target.value)}
                    className="border p-2 rounded"
                  >
                    <option value="seconds">seconds</option>
                    <option value="minutes">minutes</option>
                    <option value="hours">hours</option>
                  </select>
                </div>
              </>
            )}

            {!isCustom && (
              <button type="button" onClick={() => setIsCustom(true)} className="text-sm text-blue-600 mt-2">
                Use custom value
              </button>
            )}

            <p className="text-sm text-gray-500 mt-2">
              Will run every {value} {unit}
            </p>

            <div className="flex justify-end gap-2 mt-4">
              <button
                type="button"
                onClick={() => setShowModal(false)}
                className="bg-gray-200 hover:bg-gray-300 text-gray-800 px-4 py-2 rounded"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleScheduleSave}
                disabled={isSaveDisabled}
                className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {isSavingSchedule ? "Saving..." : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}

      {isViewerOpen && selectedFile && (
        <div
          className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
          onClick={closeViewer}
          role="presentation"
        >
          <div
            className="bg-white rounded-xl shadow-xl w-full max-w-[96vw] max-h-[94vh] overflow-y-auto p-4"
            onClick={(e) => e.stopPropagation()}
            role="presentation"
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold break-all pr-4">{selectedFile.name}</h2>
              <button
                type="button"
                onClick={closeViewer}
                className="bg-gray-700 hover:bg-gray-800 text-white px-3 py-1 rounded"
              >
                Close
              </button>
            </div>

            {isPdfSelected && (
              <div className="relative">
                {isOpeningFile && (
                  <div className="absolute inset-0 bg-white/80 flex items-center justify-center z-10 rounded">
                    <div className="flex items-center gap-2 text-sm text-gray-600">
                      <span className="inline-block w-4 h-4 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
                      Opening file...
                    </div>
                  </div>
                )}
                {pdfBlobUrl ? (
                  <iframe
                    src={pdfBlobUrl}
                    title={selectedFile.name}
                    className="w-full h-[80vh] rounded"
                    onLoad={() => setIsOpeningFile(false)}
                    onError={() => setIsOpeningFile(false)}
                  />
                ) : (
                  <div className="w-full h-[80vh] rounded border bg-gray-50 flex items-center justify-center text-sm text-gray-500">
                    {isOpeningFile || isLoadingContent ? "Loading PDF…" : "PDF preview unavailable."}
                  </div>
                )}
              </div>
            )}

            {isDocSelected && (
              <div className="space-y-3">
                <p className="text-sm text-gray-600">
                  Converting Word to PDF for a reliable in-app preview.
                </p>
                <div className="relative">
                  {isOpeningFile && (
                    <div className="absolute inset-0 bg-white/80 flex items-center justify-center z-10 rounded">
                      <div className="flex items-center gap-2 text-sm text-gray-600">
                        <span className="inline-block w-4 h-4 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
                        Opening file...
                      </div>
                    </div>
                  )}
                  {docPreviewUrl ? (
                    <iframe
                      src={docPreviewUrl}
                      title={selectedFile.name}
                      className="w-full h-[70vh] rounded border"
                      onLoad={() => setIsOpeningFile(false)}
                      onError={() => setIsOpeningFile(false)}
                    />
                  ) : (
                    <div className="w-full h-[70vh] rounded border bg-gray-50 flex items-center justify-center text-sm text-gray-500">
                      PDF preview is unavailable for this file right now. Use open/download.
                    </div>
                  )}
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => handleOpenFileInNewTab(selectedFile.id)}
                    className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded text-sm"
                  >
                    Open in New Tab
                  </button>
                  <button
                    type="button"
                    disabled={downloadingFileId === selectedFile.id}
                    onClick={() => handleDownloadFile(selectedFile.id, selectedFile.name)}
                    className="bg-gray-700 hover:bg-gray-800 disabled:opacity-60 text-white px-3 py-1 rounded text-sm"
                  >
                    {downloadingFileId === selectedFile.id ? "Downloading…" : "Download"}
                  </button>
                </div>
              </div>
            )}

            {isJsonSelected && (
              <div>
                {(isLoadingContent || isOpeningFile) && (
                  <div className="min-h-[60vh] flex items-center justify-center">
                    <div className="flex items-center gap-2 text-sm text-gray-600">
                      <span className="inline-block w-4 h-4 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
                      Loading accessibility report...
                    </div>
                  </div>
                )}
                {!isLoadingContent && !isOpeningFile && (
                  <>
                    <div className="bg-white rounded-xl shadow p-4 mb-4 border">
                      <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
                        <div className="flex-1 min-w-[200px]">
                          {summary.description && (
                            <p className="text-sm text-slate-700 mb-3">{summary.description}</p>
                          )}
                          <div className="flex gap-3 flex-wrap">
                            <span className="px-2 py-1 rounded bg-green-100 text-green-700 text-sm">
                              Passed: {summary.passed}
                            </span>
                            <span className="px-2 py-1 rounded bg-red-100 text-red-700 text-sm">
                              Failed: {summary.failed}
                            </span>
                            <span className="px-2 py-1 rounded bg-yellow-100 text-yellow-700 text-sm">
                              Needs manual check: {summary.needsManual}
                            </span>
                            <span className="px-2 py-1 rounded bg-emerald-100 text-emerald-700 text-sm">
                              Passed manually: {summary.passedManually}
                            </span>
                            <span className="px-2 py-1 rounded bg-rose-100 text-rose-700 text-sm">
                              Failed manually: {summary.failedManually}
                            </span>
                            <span className="px-2 py-1 rounded bg-gray-200 text-gray-700 text-sm">
                              Skipped: {summary.skipped}
                            </span>
                          </div>
                        </div>
                        {folderJsonCompanionPdfId && selectedFile?.id ? (
                          <AccessibilityExcelDownloadButton
                            busy={isExportingAccessibilityReport}
                            onClick={() =>
                              handleDownloadAccessibilityXlsx(
                                folderJsonCompanionPdfId,
                                selectedFile.id,
                                selectedFile.name || ""
                              )
                            }
                          />
                        ) : null}
                      </div>
                      {folderJsonCompanionPdfId && isLoadingFolderAccessibilityDetail && (
                        <p className="text-xs text-slate-500 mt-3 flex items-center gap-2">
                          <span className="inline-block w-3 h-3 border border-slate-300 border-t-slate-600 rounded-full animate-spin" />
                          Resolving page locations…
                        </p>
                      )}
                    </div>

                    {jsonSections.length === 0 && (
                      <pre className="text-xs bg-gray-50 rounded p-3 overflow-auto">
                        {JSON.stringify(fileContent, null, 2)}
                      </pre>
                    )}

                    {jsonSections.map(([sectionTitle, sectionValue]) => {
                      const rows = Array.isArray(sectionValue) ? sectionValue : [sectionValue];
                      return (
                        <div key={sectionTitle} className="mb-6">
                          <h3 className="font-semibold text-lg mb-2 capitalize">{sectionTitle}</h3>
                          <div className="overflow-x-auto">
                            <table className="w-full text-sm border">
                              <thead className="bg-gray-50">
                                <tr>
                                  <th className="text-left p-2 border">Rule</th>
                                  <th className="text-left p-2 border">Status</th>
                                  <th className="text-left p-2 border">Description</th>
                                </tr>
                              </thead>
                              <tbody>
                                {rows.map((entry, index) => {
                                  const normalizedEntry = normalizeReportEntry(entry);
                                  const statusValue = (normalizedEntry.status || "unknown").toString();
                                  const normalizedStatus = statusValue.toLowerCase();
                                  const statusClass =
                                    STATUS_CLASS[normalizedStatus] ||
                                    (normalizedStatus.includes("manual")
                                      ? STATUS_CLASS["needs manual check"]
                                      : "text-gray-700");
                                  const locKey = `${sectionTitle}|${normalizedEntry.rule}`;
                                  const { pagesByKey, unlocatable } = folderAccessibilityLocationHints;
                                  const pages = pagesByKey.get(locKey);
                                  const isFailedLike = normalizedStatus.includes("failed");
                                  const isManualLike =
                                    normalizedStatus.includes("needs manual") ||
                                    normalizedStatus.includes("manual check");
                                  const showPages = Boolean(pages?.length);
                                  const showUnlocatable =
                                    Boolean(folderAccessibilityDetail) &&
                                    isFailedLike &&
                                    !showPages &&
                                    unlocatable.has(locKey);
                                  const showManualHint = isManualLike;
                                  return (
                                    <tr key={`${sectionTitle}-${index}`} className="border-t">
                                      <td className="p-2 border">
                                        <div>{normalizedEntry.rule || `Rule ${index + 1}`}</div>
                                        {showPages && (
                                          <div className="text-xs text-slate-600 mt-1">Pages: {pages.join(", ")}</div>
                                        )}
                                        {showUnlocatable && (
                                          <div className="text-xs text-slate-500 mt-1">Page location unknown</div>
                                        )}
                                        {showManualHint && (
                                          <div className="text-xs text-amber-700 mt-1">Review full document</div>
                                        )}
                                      </td>
                                      <td className={`p-2 border font-medium ${statusClass}`}>{statusValue}</td>
                                      <td className="p-2 border">
                                        {normalizedEntry.description ||
                                          (typeof entry === "string" ? entry : JSON.stringify(entry))}
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      );
                    })}
                  </>
                )}
              </div>
            )}

            {isXlsxSelected && (
              <div>
                {(isLoadingContent || isOpeningFile) && (
                  <div className="min-h-[60vh] flex items-center justify-center">
                    <div className="flex items-center gap-2 text-sm text-gray-600">
                      <span className="inline-block w-4 h-4 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
                      Loading tagging report...
                    </div>
                  </div>
                )}
                {!isLoadingContent && !isOpeningFile && <ExcelViewer data={xlsxContent} />}
              </div>
            )}

            {!isPdfSelected && !isJsonSelected && !isDocSelected && !isXlsxSelected && (
              <p className="text-sm text-gray-500">
                Preview is available for PDF, DOC/DOCX, XLSX, and JSON files.
              </p>
            )}
          </div>
        </div>
      )}

      <Modal open={Boolean(viewer)} onClose={closeRunOutputViewer} title={viewer?.title || `${viewer?.type || "Output"} Viewer`} sizeClass="w-[95vw] h-[92vh]">
        {isViewerLoading && viewer?.type !== "pdf" && (
          <div className="h-full min-h-[60vh] flex items-center justify-center">
            <div className="flex items-center gap-2 text-sm text-gray-600">
              <span className="inline-block w-4 h-4 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
              Loading {viewer?.title ? viewer.title.toLowerCase() : "output"}...
            </div>
          </div>
        )}
        {viewer?.type === "pdf" && (
          <div className="relative w-full h-full min-h-[60vh]">
            {viewer.blobUrl ? (
              <iframe
                src={viewer.blobUrl}
                title="Output PDF"
                className="w-full h-full rounded border"
                onLoad={() => setIsViewerLoading(false)}
                onError={() => setIsViewerLoading(false)}
              />
            ) : (
              <div className="w-full h-full min-h-[40vh] rounded border bg-gray-50 flex items-center justify-center text-sm text-gray-500">
                {isViewerLoading ? "Loading tagged PDF…" : "PDF preview unavailable."}
              </div>
            )}
            {isViewerLoading && (
              <div className="absolute inset-0 bg-white/80 flex items-center justify-center rounded">
                <div className="flex items-center gap-2 text-sm text-gray-600">
                  <span className="inline-block w-4 h-4 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
                  Loading tagged pdf...
                </div>
              </div>
            )}
          </div>
        )}
        {!isViewerLoading && viewer?.type === "json" && (
          <div>
            <div className="bg-white rounded-xl shadow p-4 mb-4 border">
              <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
                <div className="flex-1 min-w-[200px]">
                  {viewerSummary.description && (
                    <p className="text-sm text-slate-700 mb-3">{viewerSummary.description}</p>
                  )}
                  <div className="flex gap-3 flex-wrap">
                    <span className="px-2 py-1 rounded bg-green-100 text-green-700 text-sm">
                      Passed: {viewerSummary.passed}
                    </span>
                    <span className="px-2 py-1 rounded bg-red-100 text-red-700 text-sm">
                      Failed: {viewerSummary.failed}
                    </span>
                    <span className="px-2 py-1 rounded bg-yellow-100 text-yellow-700 text-sm">
                      Needs manual check: {viewerSummary.needsManual}
                    </span>
                    <span className="px-2 py-1 rounded bg-emerald-100 text-emerald-700 text-sm">
                      Passed manually: {viewerSummary.passedManually}
                    </span>
                    <span className="px-2 py-1 rounded bg-rose-100 text-rose-700 text-sm">
                      Failed manually: {viewerSummary.failedManually}
                    </span>
                    <span className="px-2 py-1 rounded bg-gray-200 text-gray-700 text-sm">
                      Skipped: {viewerSummary.skipped}
                    </span>
                  </div>
                </div>
                {viewer?.pdfId && viewer?.jsonId ? (
                  <AccessibilityExcelDownloadButton
                    busy={isExportingAccessibilityReport}
                    onClick={() =>
                      handleDownloadAccessibilityXlsx(viewer.pdfId, viewer.jsonId, viewer.jsonFileName || "")
                    }
                  />
                ) : null}
              </div>
              {viewer?.pdfId && viewer?.jsonId && isLoadingAccessibilityDetail && (
                <p className="text-xs text-slate-500 mt-3 flex items-center gap-2">
                  <span className="inline-block w-3 h-3 border border-slate-300 border-t-slate-600 rounded-full animate-spin" />
                  Resolving page locations…
                </p>
              )}
            </div>

            {viewerJsonSections.length === 0 && (
              <pre className="text-xs bg-gray-50 rounded p-3 overflow-auto h-full">
                {JSON.stringify(viewerJson || {}, null, 2)}
              </pre>
            )}

            {viewerJsonSections.map(([sectionTitle, sectionValue]) => {
              const rows = Array.isArray(sectionValue) ? sectionValue : [sectionValue];
              return (
                <div key={sectionTitle} className="mb-6">
                  <h3 className="font-semibold text-lg mb-2 capitalize">{sectionTitle}</h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm border">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="text-left p-2 border">Rule</th>
                          <th className="text-left p-2 border">Status</th>
                          <th className="text-left p-2 border">Description</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((entry, index) => {
                          const normalizedEntry = normalizeReportEntry(entry);
                          const statusValue = (normalizedEntry.status || "unknown").toString();
                          const normalizedStatus = statusValue.toLowerCase();
                          const statusClass =
                            STATUS_CLASS[normalizedStatus] ||
                            (normalizedStatus.includes("manual")
                              ? STATUS_CLASS["needs manual check"]
                              : "text-gray-700");
                          const locKey = `${sectionTitle}|${normalizedEntry.rule}`;
                          const { pagesByKey, unlocatable } = accessibilityLocationHints;
                          const pages = pagesByKey.get(locKey);
                          const isFailedLike = normalizedStatus.includes("failed");
                          const isManualLike =
                            normalizedStatus.includes("needs manual") || normalizedStatus.includes("manual check");
                          const showPages = Boolean(pages?.length);
                          const showUnlocatable =
                            Boolean(accessibilityDetail) &&
                            isFailedLike &&
                            !showPages &&
                            unlocatable.has(locKey);
                          const showManualHint = isManualLike;
                          return (
                            <tr key={`${sectionTitle}-${index}`} className="border-t">
                              <td className="p-2 border">
                                <div>{normalizedEntry.rule || `Rule ${index + 1}`}</div>
                                {showPages && (
                                  <div className="text-xs text-slate-600 mt-1">Pages: {pages.join(", ")}</div>
                                )}
                                {showUnlocatable && (
                                  <div className="text-xs text-slate-500 mt-1">Page location unknown</div>
                                )}
                                {showManualHint && (
                                  <div className="text-xs text-amber-700 mt-1">Review full document</div>
                                )}
                              </td>
                              <td className={`p-2 border font-medium ${statusClass}`}>{statusValue}</td>
                              <td className="p-2 border">
                                {normalizedEntry.description ||
                                  (typeof entry === "string" ? entry : JSON.stringify(entry))}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              );
            })}
          </div>
        )}
        {!isViewerLoading && viewer?.type === "xlsx" && <ExcelViewer data={viewerXlsx} />}
      </Modal>

      <EmailModal
        open={showEmailModal}
        onClose={() => setShowEmailModal(false)}
        emails={emails}
        emailInput={emailInput}
        setEmailInput={setEmailInput}
        canAddEmails={canAddEmails}
        isSavingEmail={isSavingEmail}
        invalidEmailCandidates={invalidEmailCandidates}
        handleAddEmails={handleAddEmails}
        handleDeleteEmail={handleDeleteEmail}
        deletingEmailId={deletingEmailId}
      />

      <DailyReportModal
        open={showReportModal}
        onClose={() => setShowReportModal(false)}
        enabled={Boolean(settings.enabled)}
        onToggleEnabled={(enabled) =>
          setSettings((prev) => ({
            ...prev,
            enabled,
          }))
        }
        time={eodTime}
        onTimeChange={(value) => setEodTime(value || "14:00")}
        onSave={async () => {
          const isSaved = await handleSaveSettings();
          if (isSaved) {
            setShowReportModal(false);
          }
        }}
        isSaving={isSavingSettings}
        isLoadingSettings={isLoadingReportSettings}
      />

      {success && <SuccessToast success={success} onDismiss={() => setSuccess(null)} />}
      {emailToast && (
        <div className="fixed bottom-5 right-5 bg-green-500 text-white px-4 py-3 rounded-lg shadow-lg z-50 text-sm">
          {emailToast}
        </div>
      )}
    </div>
  );
}

export default Dashboard;
