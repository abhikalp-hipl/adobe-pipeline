import React from "react";
import { Calendar, Mail, Play, User } from "lucide-react";
import Button from "./Button";

export default function Navbar({
  activePage,
  isRunning,
  onRunNow,
  onOpenSchedule,
  onOpenEmailModal,
  emailCount,
  showProfileMenu,
  setShowProfileMenu,
  onLogout,
}) {
  return (
    <div className="flex justify-between items-center mb-6">
      <h1 className="text-2xl font-semibold text-gray-900">{activePage === "runs" ? "Runs" : "Dashboard"}</h1>
      <div className="flex items-center gap-3">
        {!isRunning ? (
          <>
            <Button onClick={onRunNow} className="flex items-center gap-2">
              <Play size={16} />
              Run Now
            </Button>
            <button
              type="button"
              onClick={onOpenEmailModal}
              className="btn-secondary flex items-center gap-2"
            >
              <Mail size={16} />
              Manage Emails ({emailCount || 0})
            </button>
            <Button onClick={onOpenSchedule} className="flex items-center gap-2 bg-gray-800 hover:bg-gray-900">
              <Calendar size={16} />
              Schedule
            </Button>
          </>
        ) : (
          <Button disabled className="flex items-center gap-2">
            <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
            Running...
          </Button>
        )}
        <div className="relative" id="profile-menu">
          <button type="button" onClick={() => setShowProfileMenu((prev) => !prev)} className="ml-2 w-10 h-10 rounded-full bg-gray-200 flex items-center justify-center hover:bg-gray-300" aria-label="Profile menu">
            <User size={18} />
          </button>
          {showProfileMenu && (
            <div className="absolute right-0 mt-2 w-40 bg-white shadow-lg rounded-lg border z-50">
              <button type="button" onClick={onLogout} className="w-full text-left px-4 py-2 hover:bg-gray-100 text-sm">
                Logout
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
