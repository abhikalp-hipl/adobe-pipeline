import React, { useEffect } from "react";
import { LocalizationProvider } from "@mui/x-date-pickers/LocalizationProvider";
import { AdapterDayjs } from "@mui/x-date-pickers/AdapterDayjs";
import { TimePicker } from "@mui/x-date-pickers/TimePicker";
import dayjs from "dayjs";

export default function DailyReportModal({
  open,
  onClose,
  enabled,
  onToggleEnabled,
  time,
  onTimeChange,
  onSave,
  isSaving,
  isLoadingSettings,
}) {
  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  const selectedTime = dayjs(`2000-01-01T${time || "14:00"}`);
  const displayTime = selectedTime.isValid() ? selectedTime.format("hh:mm A") : "02:00 PM";

  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-40 flex items-center justify-center z-50 p-4"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div className="bg-white rounded-xl w-[420px] p-6 shadow-lg transition-all duration-200 ease-out">
        <h3 className="text-lg font-semibold">Daily Report Settings</h3>

        <div className="space-y-4 mt-4">
          <label className="flex items-center gap-2">
          <input type="checkbox" checked={enabled} onChange={(event) => onToggleEnabled(event.target.checked)} />
          Enable Daily Report
          </label>

          <div>
          <div className="mt-2 w-full">
              <LocalizationProvider dateAdapter={AdapterDayjs}>
                <TimePicker
                  label="Report Time"
                  value={selectedTime}
                  onChange={(newValue) => onTimeChange(newValue?.format("HH:mm") || "14:00")}
                  slotProps={{
                    textField: {
                      fullWidth: true,
                      size: "small",
                      autoFocus: true,
                    },
                  }}
                />
              </LocalizationProvider>
            </div>
          </div>
        </div>

        <p className="text-xs text-gray-500 mt-2">Report will be sent daily at {displayTime}</p>
        {isLoadingSettings && <p className="text-xs text-gray-500 mt-2">Loading current settings...</p>}

        <div className="flex justify-end gap-2 mt-6">
          <button type="button" className="btn-secondary" onClick={onClose} disabled={isSaving}>
            Cancel
          </button>
          <button type="button" className="btn-primary" onClick={onSave} disabled={isSaving || isLoadingSettings || !time}>
            {isSaving ? "Saving..." : isLoadingSettings ? "Loading..." : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
