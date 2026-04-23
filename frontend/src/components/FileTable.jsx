import React, { useEffect, useMemo, useState } from "react";
import { ArrowDownAZ, ArrowUpAZ, Code, FileText, Table } from "lucide-react";

export default function FileTable({ isLoadingDashboardFiles, dashboardFiles, openFile, lastUpdatedLabel }) {
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState("name");
  const [sortOrder, setSortOrder] = useState("asc");
  const pageSize = 20;

  useEffect(() => {
    setPage(1);
  }, [dashboardFiles]);

  const sortedDashboardFiles = useMemo(() => {
    const rows = [...(dashboardFiles || [])];
    rows.sort((a, b) => {
      const left =
        sortBy === "status" ? String(a?.status || "").toLowerCase() : String(a?.name || "").toLowerCase();
      const right =
        sortBy === "status" ? String(b?.status || "").toLowerCase() : String(b?.name || "").toLowerCase();
      if (left < right) return sortOrder === "asc" ? -1 : 1;
      if (left > right) return sortOrder === "asc" ? 1 : -1;
      return 0;
    });
    return rows;
  }, [dashboardFiles, sortBy, sortOrder]);

  const totalPages = Math.max(1, Math.ceil((sortedDashboardFiles?.length || 0) / pageSize));

  const paginatedDashboardFiles = useMemo(
    () => sortedDashboardFiles.slice((page - 1) * pageSize, page * pageSize),
    [sortedDashboardFiles, page]
  );

  const totalFiles = dashboardFiles?.length || 0;
  const successCount = (dashboardFiles || []).filter((item) => item?.status === "COMPLETED").length;
  const failedCount = totalFiles - successCount;

  const toggleSort = (column) => {
    if (sortBy === column) {
      setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
      return;
    }
    setSortBy(column);
    setSortOrder("asc");
  };

  return (
    <section className="card mt-6">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <h2 className="text-lg font-semibold">Processed Files</h2>
          <p className="text-xs text-gray-500 mt-1">Latest file-level outcomes from recent runs</p>
          <p className="text-xs text-gray-500 mt-1">Last updated: {lastUpdatedLabel || "-"}</p>
          <div className="flex gap-4 text-sm mt-2">
            <span>Files: {totalFiles}</span>
            <span className="text-green-600">Success: {successCount}</span>
            <span className="text-red-600">Failed: {failedCount}</span>
          </div>
        </div>
      </div>
      {isLoadingDashboardFiles && (
        <div className="flex items-center gap-2 text-sm text-gray-500 mb-2">
          <span className="inline-block w-4 h-4 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
          Loading results...
        </div>
      )}
      {!isLoadingDashboardFiles && dashboardFiles.length === 0 && (
        <div className="border border-dashed rounded-xl p-8 text-center bg-gray-50">
          <div className="text-lg font-semibold text-gray-800">No files processed yet</div>
          <div className="text-sm text-gray-500 mt-1">Run pipeline or upload files to begin</div>
        </div>
      )}
      {!isLoadingDashboardFiles && dashboardFiles.length > 0 && (
        <table className="w-full text-xs border bg-white">
          <thead className="bg-gray-50">
            <tr>
              <th className="text-left p-2 border">
                <button type="button" onClick={() => toggleSort("name")} className="inline-flex items-center gap-1 font-semibold">
                  File Name
                  {sortBy === "name" && sortOrder === "asc" ? <ArrowUpAZ size={12} /> : <ArrowDownAZ size={12} />}
                </button>
              </th>
              <th className="text-left p-2 border">
                <button type="button" onClick={() => toggleSort("status")} className="inline-flex items-center gap-1 font-semibold">
                  Status
                  {sortBy === "status" && sortOrder === "asc" ? <ArrowUpAZ size={12} /> : <ArrowDownAZ size={12} />}
                </button>
              </th>
              <th className="text-left p-2 border">Accessibility</th>
              <th className="text-left p-2 border">Outputs</th>
            </tr>
          </thead>
          <tbody>
            {paginatedDashboardFiles.map((file, idx) => (
              <tr key={`${file.name}-${idx}`} className="border-t align-top">
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
                <td className="p-2 border text-gray-500">
                  <div className="flex gap-2 text-xs">
                    <span className="text-green-600">{"\u2714"} {file.accessibility?.passed || 0}</span>
                    <span className="text-red-600">{"\u2716"} {file.accessibility?.failed || 0}</span>
                    <span className="text-yellow-600">{"\u26A0"} {file.accessibility?.manual || 0}</span>
                  </div>
                </td>
                <td className="p-2 border">
                  <div className="flex gap-2">
                    <button type="button" title={canOpenPdf ? "View Tagged PDF" : unavailableTitle} disabled={!canOpenPdf} onClick={() => openFile("pdf", file?.outputs?.pdf_url, "Tagged PDF")} className="px-2 py-1 text-xs bg-gray-100 rounded hover:bg-gray-200 disabled:opacity-40 disabled:cursor-not-allowed inline-flex items-center gap-1"><FileText size={14} />Tagged PDF</button>
                    <button type="button" title={canOpenJson ? "View Accessibility Report" : unavailableTitle} disabled={!canOpenJson} onClick={() => openFile("json", file?.outputs?.json_url, "Accessibility Report")} className="px-2 py-1 text-xs bg-gray-100 rounded hover:bg-gray-200 disabled:opacity-40 disabled:cursor-not-allowed inline-flex items-center gap-1"><Code size={14} />Accessibility Report</button>
                    <button type="button" title={canOpenXlsx ? "View Tagging Report" : unavailableTitle} disabled={!canOpenXlsx} onClick={() => openFile("xlsx", file?.outputs?.xlsx_url, "Tagging Report")} className="px-2 py-1 text-xs bg-gray-100 rounded hover:bg-gray-200 disabled:opacity-40 disabled:cursor-not-allowed inline-flex items-center gap-1"><Table size={14} />Tagging Report</button>
                  </div>
                  {!canOpenPdf && !canOpenJson && !canOpenXlsx && (
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
      {!isLoadingDashboardFiles && dashboardFiles.length > 0 && (
        <div className="flex justify-between items-center mt-4">
          <button
            type="button"
            disabled={page === 1}
            onClick={() => setPage((prev) => prev - 1)}
            className="px-3 py-1 text-sm rounded bg-gray-100 hover:bg-gray-200 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Prev
          </button>
          <span className="text-sm text-gray-600">
            Page {page} of {totalPages}
          </span>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => setPage((prev) => prev + 1)}
            className="px-3 py-1 text-sm rounded bg-gray-100 hover:bg-gray-200 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Next
          </button>
        </div>
      )}
    </section>
  );
}
