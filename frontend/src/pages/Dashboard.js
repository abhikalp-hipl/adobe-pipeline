import React, { useEffect, useMemo, useRef, useState } from "react";

import ExcelViewer from "../components/ExcelViewer";
import ErrorPopup from "../components/ErrorPopup";
import SuccessToast from "../components/SuccessToast";
import {
  getFileContent,
  getFileContentArrayBuffer,
  getFilePreviewPdfUrl,
  getFiles,
  getFileUrl,
  getScheduler,
  getPipelineStatus,
  runNow,
  updateScheduler,
} from "../services/api";

const FOLDERS = [
  { key: "intake", label: "📥 Intake" },
  { key: "processed", label: "📦 Processed Originals" },
  { key: "output/success", label: "✅ Output Success" },
  { key: "output/failure", label: "❌ Output Failure" },
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
  const date = new Date(iso);
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

function fileTypeIcon(file) {
  const name = (file?.name || "").toLowerCase();
  const mime = (file?.mime_type || "").toLowerCase();
  if (name.endsWith(".pdf") || mime === "application/pdf") return "📄";
  if (name.endsWith(".doc") || name.endsWith(".docx") || mime.includes("wordprocessingml") || mime === "application/msword")
    return "📝";
  if (name.endsWith(".xlsx") || mime.includes("spreadsheetml")) return "📊";
  if (name.endsWith(".json") || mime === "application/json") return "🧾";
  return "📁";
}

function Dashboard() {
  const [selectedFolder, setSelectedFolder] = useState("intake");
  const [files, setFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileContent, setFileContent] = useState(null);
  const [xlsxContent, setXlsxContent] = useState(null);
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);
  const [isLoadingContent, setIsLoadingContent] = useState(false);
  const [isOpeningFile, setIsOpeningFile] = useState(false);
  const [error, setError] = useState("");
  const [isViewerOpen, setIsViewerOpen] = useState(false);
  const [docPreviewUrl, setDocPreviewUrl] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [value, setValue] = useState(5);
  const [unit, setUnit] = useState("minutes");
  const [isCustom, setIsCustom] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isSavingSchedule, setIsSavingSchedule] = useState(false);
  const [pipelineStatus, setPipelineStatus] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [lastUpdatedAt, setLastUpdatedAt] = useState(null);
  const [folderCounts, setFolderCounts] = useState({
    intake: 0,
    processed: 0,
    "output/success": 0,
    "output/failure": 0,
  });
  const [showProfileMenu, setShowProfileMenu] = useState(false);
  const [pipelineError, setPipelineError] = useState(null);
  const lastPipelineErrorKeyRef = useRef("");
  const [success, setSuccess] = useState(null);
  const lastSuccessKeyRef = useRef("");
  const wasRunningRef = useRef(false);

  const intervalOptions = [1, 2, 5, 10, 15, 30, 60];
  const isRunning = Boolean(pipelineStatus?.is_running) || isProcessing;

  useEffect(() => {
    const fetchFiles = async () => {
      setIsLoadingFiles(true);
      setError("");
      setFiles([]);
      setSelectedFile(null);
      setFileContent(null);
      setXlsxContent(null);
      try {
        const response = await getFiles(selectedFolder);
        // eslint-disable-next-line no-console
        console.log("Mapped files", response);
        setFiles(response);
        setLastUpdatedAt(new Date().toISOString());
      } catch (requestError) {
        setError(requestError?.response?.data?.detail || "Failed to fetch files.");
      } finally {
        setIsLoadingFiles(false);
      }
    };
    fetchFiles();
  }, [selectedFolder]);

  useEffect(() => {
    let cancelled = false;
    const fetchCounts = async () => {
      try {
        const [intake, processed, outputSuccess, outputFailure] = await Promise.all([
          getFiles("intake"),
          getFiles("processed"),
          getFiles("output/success"),
          getFiles("output/failure"),
        ]);
        if (cancelled) return;
        setFolderCounts({
          intake: Array.isArray(intake) ? intake.length : 0,
          processed: Array.isArray(processed) ? processed.length : 0,
          "output/success": Array.isArray(outputSuccess) ? outputSuccess.length : 0,
          "output/failure": Array.isArray(outputFailure) ? outputFailure.length : 0,
        });
      } catch {
        // ignore count errors
      }
    };
    fetchCounts();
    return () => {
      cancelled = true;
    };
  }, []);

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
    let isMounted = true;

    const fetchStatus = async () => {
      try {
        const data = await getPipelineStatus();
        if (isMounted) {
          const prevWasRunning = wasRunningRef.current;
          const nextIsRunning = Boolean(data?.is_running);
          setPipelineStatus(data);
          setIsProcessing(Boolean(data?.is_running));
          wasRunningRef.current = nextIsRunning;
          if (data?.current_step === "FAILED") {
            const key = `${data?.current_file || ""}|${data?.failed_step || ""}|${data?.error || ""}`;
            if (key && key !== lastPipelineErrorKeyRef.current) {
              lastPipelineErrorKeyRef.current = key;
              setPipelineError({
                message: data?.error || "Pipeline failed.",
                file: data?.current_file || "",
                step: data?.failed_step || "",
              });
            }
          }
          if (prevWasRunning && !nextIsRunning && data?.current_step === "COMPLETED") {
            const key = `${data?.current_file || ""}|${data?.progress || 100}`;
            if (key && key !== lastSuccessKeyRef.current) {
              lastSuccessKeyRef.current = key;
              setSuccess({ file: data?.current_file || "" });
            }
          }
        }
      } catch {
        // ignore polling errors
      }
    };

    fetchStatus();
    const intervalId = setInterval(fetchStatus, 3000);
    return () => {
      isMounted = false;
      clearInterval(intervalId);
    };
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
    setDocPreviewUrl("");
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
      }
      if (isDocFile) {
        setError("");
        setDocPreviewUrl(getFilePreviewPdfUrl(file.id));
      }
      return;
    }
    setIsLoadingContent(true);
    setError("");
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
    setIsViewerOpen(false);
    setSelectedFile(null);
    setFileContent(null);
    setXlsxContent(null);
    setIsOpeningFile(false);
    setDocPreviewUrl("");
  };

  const intervalSeconds =
    unit === "hours" ? value * 3600 : unit === "minutes" ? value * 60 : value;
  const isSaveDisabled =
    isSavingSchedule ||
    isProcessing ||
    value < 1 ||
    Number.isNaN(intervalSeconds) ||
    !Number.isFinite(intervalSeconds) ||
    intervalSeconds < 60;

  const handleRunNow = async () => {
    setIsProcessing(true);
    setPipelineStatus((prev) => ({
      ...(prev || {}),
      is_running: true,
      current_step: prev?.current_step || "Starting…",
      progress: typeof prev?.progress === "number" ? prev.progress : 0,
    }));
    try {
      await runNow();
    } catch (requestError) {
      setPipelineStatus((prev) => ({
        ...(prev || {}),
        is_running: false,
      }));
      setError(requestError?.response?.data?.detail || "Failed to start processing.");
    } finally {
      setIsProcessing(false);
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
    fetch("http://localhost:8000/auth/logout", { method: "POST" }).catch(() => {});
    window.location.href = "/";
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

  return (
    <div className="flex h-screen">
      <aside className="w-72 bg-gray-900 text-white">
        <div className="p-4">
          <div className="font-semibold text-lg">Files</div>
          <div className="text-xs text-gray-300 mt-1">Browse intake, processed originals, and output folders</div>
        </div>
        <div className="px-2 space-y-1">
          {FOLDERS.map((folder) => (
            <div
              key={folder.key}
              className={`p-2 rounded cursor-pointer flex items-center justify-between hover:bg-gray-800 ${
                selectedFolder === folder.key ? "bg-blue-600 text-white" : "text-gray-200"
              }`}
              onClick={() => setSelectedFolder(folder.key)}
              role="button"
              tabIndex={0}
              onKeyDown={(event) => event.key === "Enter" && setSelectedFolder(folder.key)}
            >
              <span className="text-sm">{folder.label}</span>
              <span
                className={`text-xs px-2 py-0.5 rounded-full ${
                  selectedFolder === folder.key ? "bg-white/20" : "bg-white/10"
                }`}
              >
                {folderCounts?.[folder.key] ?? 0}
              </span>
            </div>
          ))}
        </div>
      </aside>

      <main className="flex-1 p-6 bg-gray-100 overflow-y-auto">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-2xl font-semibold text-gray-900">Dashboard</h1>
          <div className="flex items-center gap-3">
            <div className="hidden md:flex items-center gap-2 bg-white border rounded-lg px-3 py-2">
              <span
                className={`w-2.5 h-2.5 rounded-full ${
                  isRunning ? "bg-blue-500 animate-pulse" : "bg-emerald-500"
                }`}
              />
              <span className="text-sm text-gray-700">
                {isRunning ? "Running" : "Idle"}
              </span>
            </div>
            <button
              type="button"
              onClick={handleRunNow}
              disabled={isProcessing}
              className={`px-4 py-2 rounded text-white ${
                isProcessing ? "bg-blue-300 cursor-not-allowed" : "bg-blue-600 hover:bg-blue-700"
              }`}
            >
              {isProcessing ? (
                <span className="flex items-center gap-2">
                  <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Running...
                </span>
              ) : (
                "Run Now"
              )}
            </button>
            <button
              type="button"
              onClick={() => setShowModal(true)}
              disabled={isProcessing}
              className={`px-4 py-2 rounded text-white ml-2 ${
                isProcessing ? "bg-gray-400 cursor-not-allowed" : "bg-gray-800 hover:bg-gray-900"
              }`}
            >
              Schedule
            </button>

            {isRunning ? (
              <div className="hidden md:flex items-center gap-3 ml-2">
                <span className="w-3 h-3 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                <span className="text-sm text-gray-700 max-w-[240px] truncate">
                  Processing: {pipelineStatus?.current_file || "…"}
                </span>
                <div className="w-40 h-2 bg-gray-200 rounded">
                  <div
                    className="h-2 bg-blue-500 rounded"
                    style={{
                      width: `${Math.min(100, Math.max(0, pipelineStatus?.progress || 0))}%`,
                    }}
                  />
                </div>
                <span className="text-xs text-gray-500">{pipelineStatus?.current_step || ""}</span>
              </div>
            ) : null}

            <div className="relative" id="profile-menu">
              <button
                type="button"
                onClick={() => setShowProfileMenu((prev) => !prev)}
                className="ml-2 w-10 h-10 rounded-full bg-gray-200 flex items-center justify-center hover:bg-gray-300"
                aria-label="Profile menu"
              >
                👤
              </button>
              {showProfileMenu && (
                <div className="absolute right-0 mt-2 w-40 bg-white shadow-lg rounded-lg border z-50">
                  <button
                    type="button"
                    onClick={handleLogout}
                    className="w-full text-left px-4 py-2 hover:bg-gray-100 text-sm"
                  >
                    Logout
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

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
              <div className="text-lg font-semibold text-gray-800">No files found</div>
              <div className="text-sm text-gray-500 mt-1">
                {searchQuery ? "Try a different search term." : "This folder is currently empty."}
              </div>
            </div>
          )}
          {error && <p className="text-sm text-red-600 mb-2">{error}</p>}
          <div className="space-y-2">
            {filteredFiles.map((file) => (
              <div
                key={file.id}
                className="group flex items-center justify-between p-3 rounded-lg border bg-white hover:bg-gray-50 hover:border-gray-300 transition cursor-pointer"
                onClick={() => handleFileSelect(file)}
                role="button"
                tabIndex={0}
                onKeyDown={(event) => event.key === "Enter" && handleFileSelect(file)}
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-9 h-9 rounded-lg bg-gray-100 flex items-center justify-center text-lg">
                    {fileTypeIcon(file)}
                  </div>
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

                <div className="flex items-center gap-2">
                  <div className="hidden sm:flex gap-2 opacity-0 group-hover:opacity-100 transition">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleFileSelect(file);
                      }}
                      className="px-3 py-1.5 rounded bg-blue-600 hover:bg-blue-700 text-white text-sm"
                    >
                      View
                    </button>
                    <a
                      href={getFileUrl(file.id)}
                      download={file.name}
                      onClick={(e) => e.stopPropagation()}
                      className="px-3 py-1.5 rounded bg-gray-800 hover:bg-gray-900 text-white text-sm"
                    >
                      Download
                    </a>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      </main>

      {showModal && (
        <div className="fixed inset-0 bg-black bg-opacity-40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 w-96 shadow-lg">
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
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-6xl max-h-[90vh] overflow-y-auto p-4">
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
                <iframe
                  src={getFileUrl(selectedFile.id)}
                  title={selectedFile.name}
                  className="w-full h-[80vh] rounded"
                  onLoad={() => setIsOpeningFile(false)}
                  onError={() => setIsOpeningFile(false)}
                />
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
                  <a
                    href={getFileUrl(selectedFile.id)}
                    target="_blank"
                    rel="noreferrer"
                    className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded text-sm"
                  >
                    Open in New Tab
                  </a>
                  <a
                    href={getFileUrl(selectedFile.id)}
                    download={selectedFile.name}
                    className="bg-gray-700 hover:bg-gray-800 text-white px-3 py-1 rounded text-sm"
                  >
                    Download
                  </a>
                </div>
              </div>
            )}

            {isJsonSelected && (
              <div>
                {(isLoadingContent || isOpeningFile) && <p className="text-sm text-gray-500">Loading report...</p>}
                {!isLoadingContent && (
                  <>
                    <div className="bg-white rounded-xl shadow p-4 mb-4 border">
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
                                  return (
                                    <tr key={`${sectionTitle}-${index}`} className="border-t">
                                      <td className="p-2 border">
                                        {normalizedEntry.rule || `Rule ${index + 1}`}
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
                {(isLoadingContent || isOpeningFile) && <p className="text-sm text-gray-500">Loading Excel...</p>}
                {!isLoadingContent && <ExcelViewer data={xlsxContent} />}
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

      <ErrorPopup
        error={pipelineError}
        onClose={() => setPipelineError(null)}
        onRetry={() => {
          setPipelineError(null);
          handleRunNow();
        }}
      />

      {success && <SuccessToast success={success} onDismiss={() => setSuccess(null)} />}
    </div>
  );
}

export default Dashboard;
