import React, { useCallback, useEffect, useState } from "react";
import { Mail, XCircle } from "lucide-react";
import ScheduleIntervalPicker from "./ScheduleIntervalPicker";
import { getDepartmentMe, updateDepartmentMe } from "../services/api";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function DistributionEmailsSection({ distributionEmails, emailInput, setEmailInput, emailError, onAddEmail, onRemoveEmail }) {
  return (
    <div className="pt-4 border-t border-gray-100">
      <h3 className="text-sm font-semibold flex items-center gap-2 text-gray-800 mb-1">
        <Mail size={16} />
        Distribution emails
      </h3>
      <p className="text-xs text-gray-500 mb-3">
        {distributionEmails.length} recipient{distributionEmails.length === 1 ? "" : "s"} — add one at a time
      </p>
      <input
        type="email"
        placeholder="Enter email"
        value={emailInput}
        onChange={(e) => setEmailInput(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            onAddEmail();
          }
        }}
        className="input"
      />
      <button type="button" onClick={onAddEmail} className="btn-primary mt-2 text-sm">
        Add
      </button>
      {emailError && <p className="text-sm text-red-600 mt-2">{emailError}</p>}
      <div className="mt-4 max-w-lg">
        {distributionEmails.length === 0 ? (
          <div className="text-sm text-gray-500">No emails added</div>
        ) : (
          distributionEmails.map((em) => (
            <div key={em} className="flex justify-between items-center mt-2 border rounded px-3 py-2 gap-2">
              <span className="text-sm break-all">{em}</span>
              <button
                type="button"
                onClick={() => onRemoveEmail(em)}
                className="text-red-600 hover:text-red-700 shrink-0"
                aria-label={`Remove ${em}`}
              >
                <XCircle size={16} />
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default function DepartmentSettingsPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [distributionEmails, setDistributionEmails] = useState([]);
  const [emailInput, setEmailInput] = useState("");
  const [emailError, setEmailError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const d = await getDepartmentMe();
      setData(d);
      setDistributionEmails([...(d.distribution_emails || [])].sort());
      setEmailInput("");
      setEmailError("");
    } catch (e) {
      setError(e?.response?.data?.detail || "Failed to load settings.");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleAddEmail = () => {
    const raw = emailInput.trim().toLowerCase();
    setEmailError("");
    if (!raw) return;
    if (!EMAIL_PATTERN.test(raw)) {
      setEmailError("Enter a valid email address.");
      return;
    }
    if (distributionEmails.includes(raw)) {
      setEmailError("That email is already in the list.");
      return;
    }
    setDistributionEmails((prev) => [...prev, raw].sort());
    setEmailInput("");
  };

  const handleRemoveEmail = (em) => {
    setDistributionEmails((prev) => prev.filter((x) => x !== em));
  };

  const handleSave = async (e) => {
    e.preventDefault();
    if (!data) return;
    setSaving(true);
    setError("");
    try {
      const saved = await updateDepartmentMe({
        config: {
          scheduler_interval_seconds: data.scheduler_interval_seconds ?? 300,
          intake_folder: data.intake_folder,
          processed_folder: data.processed_folder,
          output_success_folder: data.output_success_folder,
          output_failure_folder: data.output_failure_folder,
        },
        distribution_emails: distributionEmails,
      });
      setData(saved);
      setDistributionEmails([...(saved.distribution_emails || [])].sort());
    } catch (err) {
      setError(err?.response?.data?.detail || "Save failed.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="bg-white shadow rounded-xl p-6">
      <p className="text-xs text-gray-500 mb-6">Schedule, folders, and notification recipients for your department</p>

      {loading ? (
        <p className="text-sm text-gray-500">Loading…</p>
      ) : !data ? (
        <p className="text-sm text-red-600">{error || "Could not load settings."}</p>
      ) : (
        <form onSubmit={handleSave} className="space-y-4 text-sm max-w-2xl">
          {error && (
            <div className="text-sm text-red-700 bg-red-50 border border-red-100 rounded-lg px-3 py-2">{error}</div>
          )}
          <DeptReadonlyField label="Department name" value={data.name} />
          <DeptReadonlyField
            label="Department admin (Microsoft)"
            value={data.admin_email || "— (set by super admin)"}
          />
          <ScheduleIntervalPicker
            idPrefix="dept-settings"
            valueSeconds={data.scheduler_interval_seconds}
            onChangeSeconds={(s) => setData({ ...data, scheduler_interval_seconds: s })}
          />
          <DeptFolderField label="Intake folder" field="intake_folder" data={data} setData={setData} />
          <DeptFolderField label="Processed folder" field="processed_folder" data={data} setData={setData} />
          <DeptFolderField label="Output success folder" field="output_success_folder" data={data} setData={setData} />
          <DeptFolderField label="Output failure folder" field="output_failure_folder" data={data} setData={setData} />
          <DistributionEmailsSection
            distributionEmails={distributionEmails}
            emailInput={emailInput}
            setEmailInput={setEmailInput}
            emailError={emailError}
            onAddEmail={handleAddEmail}
            onRemoveEmail={handleRemoveEmail}
          />
          <div className="pt-2">
            <button type="submit" disabled={saving} className="btn-primary disabled:opacity-50">
              {saving ? "Saving…" : "Save changes"}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

function DeptReadonlyField({ label, value }) {
  return (
    <div>
      <label className="block text-xs text-gray-500 mb-1">{label}</label>
      <input className="input bg-gray-50 text-gray-600" value={value} readOnly />
    </div>
  );
}

function DeptFolderField({ label, field, data, setData }) {
  return (
    <div>
      <label className="block text-xs text-gray-500 mb-1">{label}</label>
      <input className="input" value={data[field]} onChange={(e) => setData({ ...data, [field]: e.target.value })} />
    </div>
  );
}
