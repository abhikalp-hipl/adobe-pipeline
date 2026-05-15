import React from "react";
import { Calendar, LogOut, Mail, Play, User } from "lucide-react";
import Button from "./Button";

export default function Navbar({
  departmentName,
  isRunning,
  onRunNow,
  onOpenSchedule,
  onOpenEmailModal,
  emailCount,
  showProfileMenu,
  setShowProfileMenu,
  onLogout,
}) {
  const title = departmentName?.trim() || "Department";
  const emailLabel = `Emails (${emailCount || 0})`;

  return (
    <header className="sticky top-0 z-30 shrink-0 border-b border-gray-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-4 px-6 py-4">
        <h1 className="min-w-0 flex-1 truncate text-xl font-semibold text-gray-900 sm:text-2xl" title={title}>
          {title}
        </h1>

        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          {isRunning ? (
            <div className="flex items-center gap-3">
              <Button disabled className="flex items-center gap-2">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                <span className="hidden sm:inline">Running...</span>
              </Button>
              <span className="hidden text-sm text-gray-500 md:inline">Pipeline in progress</span>
            </div>
          ) : (
            <>
              <Button onClick={onRunNow} className="flex items-center gap-2" title="Run pipeline now">
                <Play size={16} aria-hidden />
                <span className="hidden sm:inline">Run Now</span>
              </Button>
              <button
                type="button"
                onClick={onOpenEmailModal}
                className="btn-secondary flex items-center gap-2"
                title={emailLabel}
              >
                <Mail size={16} aria-hidden />
                <span className="hidden sm:inline">Manage Emails </span>
                <span>({emailCount || 0})</span>
              </button>
              <button
                type="button"
                onClick={onOpenSchedule}
                className="btn-secondary flex items-center gap-2"
                title="Schedule automation"
              >
                <Calendar size={16} aria-hidden />
                <span className="hidden sm:inline">Schedule</span>
              </button>
            </>
          )}

          <div className="relative" id="profile-menu">
            <button
              type="button"
              onClick={() => setShowProfileMenu((prev) => !prev)}
              className={`flex h-10 w-10 items-center justify-center rounded-full transition-shadow ${
                showProfileMenu
                  ? "bg-gray-200 ring-2 ring-blue-100 ring-offset-1"
                  : "bg-gray-200 hover:bg-gray-300"
              }`}
              aria-label="Profile menu"
              aria-expanded={showProfileMenu}
            >
              <User size={18} className="text-gray-600" />
            </button>
            {showProfileMenu && (
              <div
                className="absolute right-0 mt-2 w-56 overflow-hidden rounded-xl border border-gray-200 bg-white py-1 shadow-xl"
                role="menu"
              >
                <div className="border-b border-gray-100 px-4 py-3">
                  <div className="mt-1 flex items-center gap-3">
                    <User size={18} className="shrink-0 text-gray-500" strokeWidth={1.75} aria-hidden />
                    <span className="truncate text-sm font-medium text-gray-900" title={title}>
                      {title}
                    </span>
                  </div>
                </div>
                <button
                  type="button"
                  role="menuitem"
                  onClick={onLogout}
                  className="flex w-full items-center gap-3 px-4 py-2.5 text-sm text-gray-600 transition-colors hover:bg-gray-50"
                >
                  <LogOut size={18} className="shrink-0" strokeWidth={1.75} aria-hidden />
                  Sign out
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
