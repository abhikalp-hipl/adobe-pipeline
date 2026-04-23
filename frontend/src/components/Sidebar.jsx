import React from "react";
import { LayoutDashboard, FileClock, Folder } from "lucide-react";

const FOLDERS = [
  { key: "intake", label: "Intake" },
  { key: "processed", label: "Processed Originals" },
  { key: "output/success", label: "Output Success" },
  { key: "output/failure", label: "Output Failure" },
];

export default function Sidebar({
  activePage,
  setActivePage,
  selectedFolder,
  setSelectedFolder,
  folderCounts,
}) {
  return (
    <aside className="w-72 bg-gray-900 text-white">
      <div className="p-4 pb-2">
        <div className="font-semibold text-lg">Accessibility Automation Pipeline</div>
        <div className="text-xs text-gray-300 mt-1">Dashboard and pipeline run history</div>
      </div>
      <div className="px-2 space-y-1">
        <button type="button" className={`sidebar-item ${activePage === "dashboard" ? "sidebar-active" : ""}`} onClick={() => setActivePage("dashboard")}>
          <span className="flex items-center gap-2"><LayoutDashboard size={16} />Dashboard</span>
        </button>
        <button type="button" className={`sidebar-item ${activePage === "runs" ? "sidebar-active" : ""}`} onClick={() => setActivePage("runs")}>
          <span className="flex items-center gap-2"><FileClock size={16} />Runs</span>
        </button>
      </div>
      <p className="text-xs text-gray-400 mt-4 mb-2 px-3 tracking-wide">FOLDERS</p>
      <div className="px-2 space-y-1 pb-4">
        {FOLDERS.map((folder) => (
          <button
            key={folder.key}
            className={`sidebar-item ${activePage === "folder" && selectedFolder === folder.key ? "sidebar-active" : "text-gray-200"}`}
            onClick={() => {
              setSelectedFolder(folder.key);
              setActivePage("folder");
            }}
            type="button"
          >
            <span className="text-sm flex items-center gap-2 min-w-0 pr-3">
              <Folder size={16} />
              <span className="truncate">{folder.label}</span>
            </span>
            <span className={`ml-3 shrink-0 text-xs px-2 py-0.5 rounded-full ${selectedFolder === folder.key ? "bg-white/20" : "bg-white/10"}`}>
              {folderCounts?.[folder.key] ?? 0}
            </span>
          </button>
        ))}
      </div>
    </aside>
  );
}
