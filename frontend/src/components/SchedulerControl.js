import React, { useEffect, useState } from "react";

import { getScheduler, processOneDriveIntake, updateScheduler } from "../services/api";

function SchedulerControl() {
  const [status, setStatus] = useState("unknown");
  const [interval, setInterval] = useState(300);
  const [draftInterval, setDraftInterval] = useState(300);
  const [provider, setProvider] = useState("local");
  const [automationEnabled, setAutomationEnabled] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [isProcessingOneDrive, setIsProcessingOneDrive] = useState(false);

  const fetchScheduler = async () => {
    try {
      const scheduler = await getScheduler();
      setStatus(scheduler.status);
      setInterval(scheduler.interval);
      setDraftInterval(scheduler.interval);
      setProvider(scheduler.provider || "local");
      setAutomationEnabled(Boolean(scheduler.automation_enabled));
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Failed to fetch scheduler.");
    }
  };

  useEffect(() => {
    fetchScheduler();
  }, []);

  const handleUpdate = async () => {
    if (Number(draftInterval) < 60) {
      setError("Interval must be at least 60 seconds.");
      return;
    }

    setError("");
    setMessage("");
    setIsSaving(true);
    try {
      const updated = await updateScheduler(Number(draftInterval));
      setStatus(updated.status);
      setInterval(updated.interval);
      setProvider(updated.provider || provider);
      setAutomationEnabled(Boolean(updated.automation_enabled));
      setMessage("Scheduler interval updated.");
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Failed to update scheduler.");
    } finally {
      setIsSaving(false);
    }
  };

  const handleProcessOneDriveIntake = async () => {
    setError("");
    setMessage("");
    setIsProcessingOneDrive(true);
    try {
      const result = await processOneDriveIntake();
      setMessage(
        `OneDrive intake processed. Processed: ${result.processed}, Skipped: ${result.skipped}, Failed: ${result.failed}.`
      );
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Failed to process OneDrive intake.");
    } finally {
      setIsProcessingOneDrive(false);
    }
  };

  return (
    <div className="bg-white shadow rounded-xl p-4">
      <h2 className="text-lg font-semibold mb-4">Scheduler Control</h2>
      <div className="mb-4 text-sm text-slate-700">
        <p>
          Storage provider: <span className="font-medium capitalize">{provider}</span>
        </p>
        <p>Current status: <span className="font-medium capitalize">{status}</span></p>
        <p>Current interval: <span className="font-medium">{interval}s</span></p>
      </div>
      {automationEnabled ? (
        <div className="flex items-center">
          <input
            type="number"
            min={60}
            value={draftInterval}
            onChange={(event) => setDraftInterval(event.target.value)}
            className="border p-2 rounded w-32"
          />
          <button
            type="button"
            onClick={handleUpdate}
            disabled={isSaving}
            className="bg-green-500 hover:bg-green-600 disabled:opacity-60 text-white px-4 py-2 rounded ml-2"
          >
            {isSaving ? "Updating..." : "Update"}
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-slate-600">
            Background scheduler is disabled in OneDrive delegated mode. Trigger intake processing manually.
          </p>
          <button
            type="button"
            onClick={handleProcessOneDriveIntake}
            disabled={isProcessingOneDrive}
            className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white px-4 py-2 rounded"
          >
            {isProcessingOneDrive ? "Processing..." : "Process OneDrive Intake"}
          </button>
        </div>
      )}
      {message && <p className="mt-2 text-sm text-green-600">{message}</p>}
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </div>
  );
}

export default SchedulerControl;
