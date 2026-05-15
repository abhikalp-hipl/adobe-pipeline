import React, { useCallback, useEffect, useState } from "react";
import { ChevronDown, ChevronRight, Mail, Pencil, Plug, Trash2, XCircle } from "lucide-react";
import {
  createAdminDepartment,
  deleteAdminDepartment,
  getAdminDepartment,
  getAdminDepartments,
  getMicrosoftDeptLoginUrl,
  getAppJwt,
  parseJwtPayload,
  clearDashboardSessionCache,
  setAppJwt,
  updateAdminDepartment,
} from "../services/api";

import {
  formatIntervalHuman,
} from "../utils/scheduleInterval";
import ScheduleIntervalPicker from "../components/ScheduleIntervalPicker";

const defaultConfig = () => ({
  scheduler_interval_seconds: 300,
  intake_folder: "AdobePipeline/intake",
  processed_folder: "AdobePipeline/processed",
  output_success_folder: "AdobePipeline/output/success",
  output_failure_folder: "AdobePipeline/output/failure",
});

const defaultCreateForm = () => ({
  name: "",
  username: "",
  password: "",
  distributionEmails: [],
  emailDraft: "",
  adminEmail: "",
  config: defaultConfig(),
});

const emailLooksValid = (s) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(s || "").trim());

function DistributionEmailsField({ emails, emailDraft, setEmailDraft, onAdd, onRemove, error, setError }) {
  return (
    <div>
      <label className="block text-xs text-slate-500 mb-1">Distribution emails</label>
      <p className="text-xs text-slate-400 mb-2">Add recipients one at a time (same as dashboard email list).</p>
      <div className="flex gap-2">
        <input
          type="email"
          className="flex-1 border rounded px-3 py-2"
          placeholder="name@company.com"
          value={emailDraft}
          onChange={(e) => setEmailDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              onAdd();
            }
          }}
        />
        <button type="button" className="px-3 py-2 rounded bg-slate-200 hover:bg-slate-300 text-sm shrink-0" onClick={onAdd}>
          Add
        </button>
      </div>
      {error && <p className="text-xs text-red-600 mt-1">{error}</p>}
      <ul className="mt-2 space-y-1 max-h-40 overflow-y-auto border rounded-md divide-y divide-slate-100">
        {emails.length === 0 ? (
          <li className="px-3 py-2 text-xs text-slate-400">No emails yet</li>
        ) : (
          emails.map((em) => (
            <li key={em} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
              <span className="break-all">{em}</span>
              <button type="button" className="text-red-600 shrink-0 p-1 hover:bg-red-50 rounded" onClick={() => onRemove(em)} aria-label={`Remove ${em}`}>
                <XCircle size={16} />
              </button>
            </li>
          ))
        )}
      </ul>
    </div>
  );
}

function AdminSelectField({ value, onChange, distributionEmails }) {
  return (
    <div>
      <label className="block text-xs text-slate-500 mb-1">Department admin (Microsoft)</label>
      <p className="text-xs text-slate-400 mb-2">Must be one of the distribution emails. Used as a sign-in hint when connecting Microsoft for this department.</p>
      <select
        className="w-full border rounded px-3 py-2 bg-white"
        value={value || ""}
        onChange={(e) => onChange(e.target.value || "")}
        disabled={distributionEmails.length === 0}
      >
        <option value="">— None —</option>
        {distributionEmails.map((em) => (
          <option key={em} value={em}>
            {em}
          </option>
        ))}
      </select>
    </div>
  );
}

function DepartmentFormFields({ form, setForm, distError, setDistError, passwordOptional }) {
  const addEmail = () => {
    const raw = form.emailDraft.trim().toLowerCase();
    setDistError("");
    if (!raw) return;
    if (!emailLooksValid(raw)) {
      setDistError("Enter a valid email address.");
      return;
    }
    if (form.distributionEmails.includes(raw)) {
      setDistError("That email is already in the list.");
      return;
    }
    const next = [...form.distributionEmails, raw].sort();
    let adminEmail = form.adminEmail;
    if (adminEmail && !next.includes(adminEmail)) adminEmail = "";
    setForm({ ...form, distributionEmails: next, emailDraft: "", adminEmail });
  };

  const removeEmail = (em) => {
    const next = form.distributionEmails.filter((x) => x !== em);
    let adminEmail = form.adminEmail;
    if (adminEmail === em) adminEmail = "";
    setForm({ ...form, distributionEmails: next, adminEmail });
  };

  return (
    <div className="space-y-3 text-sm">
      <div>
        <label className="block text-xs text-slate-500 mb-1">Name</label>
        <input className="w-full border rounded px-3 py-2" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
      </div>
      <div>
        <label className="block text-xs text-slate-500 mb-1">Shared login username</label>
        <input className="w-full border rounded px-3 py-2" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required />
      </div>
      <div>
        <label className="block text-xs text-slate-500 mb-1">{passwordOptional ? "New password (leave blank to keep current)" : "Shared login password"}</label>
        <input
          type="password"
          className="w-full border rounded px-3 py-2"
          value={form.password}
          onChange={(e) => setForm({ ...form, password: e.target.value })}
          required={!passwordOptional}
          minLength={passwordOptional ? undefined : 6}
          autoComplete="new-password"
        />
      </div>
      <DistributionEmailsField
        emails={form.distributionEmails}
        emailDraft={form.emailDraft}
        setEmailDraft={(v) => setForm({ ...form, emailDraft: v })}
        onAdd={addEmail}
        onRemove={removeEmail}
        error={distError}
        setError={setDistError}
      />
      <AdminSelectField value={form.adminEmail} onChange={(v) => setForm({ ...form, adminEmail: v })} distributionEmails={form.distributionEmails} />
      <ScheduleIntervalPicker
        idPrefix="admin-dept"
        valueSeconds={form.config.scheduler_interval_seconds}
        onChangeSeconds={(s) => setForm({ ...form, config: { ...form.config, scheduler_interval_seconds: s } })}
      />
      <div>
        <label className="block text-xs text-slate-500 mb-1">Intake folder</label>
        <input className="w-full border rounded px-3 py-2" value={form.config.intake_folder} onChange={(e) => setForm({ ...form, config: { ...form.config, intake_folder: e.target.value } })} />
      </div>
      <div>
        <label className="block text-xs text-slate-500 mb-1">Processed folder</label>
        <input
          className="w-full border rounded px-3 py-2"
          value={form.config.processed_folder}
          onChange={(e) => setForm({ ...form, config: { ...form.config, processed_folder: e.target.value } })}
        />
      </div>
      <div>
        <label className="block text-xs text-slate-500 mb-1">Output success</label>
        <input
          className="w-full border rounded px-3 py-2"
          value={form.config.output_success_folder}
          onChange={(e) => setForm({ ...form, config: { ...form.config, output_success_folder: e.target.value } })}
        />
      </div>
      <div>
        <label className="block text-xs text-slate-500 mb-1">Output failure</label>
        <input
          className="w-full border rounded px-3 py-2"
          value={form.config.output_failure_folder}
          onChange={(e) => setForm({ ...form, config: { ...form.config, output_failure_folder: e.target.value } })}
        />
      </div>
    </div>
  );
}

export default function AdminPanel() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState(defaultCreateForm);
  const [createDistError, setCreateDistError] = useState("");
  const [expanded, setExpanded] = useState({});
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState(null);
  const [editDistError, setEditDistError] = useState("");
  const [editLoading, setEditLoading] = useState(false);

  const load = useCallback(async () => {
    setError("");
    setLoading(true);
    try {
      const data = await getAdminDepartments();
      setRows(Array.isArray(data) ? data : []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Failed to load departments.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const token = getAppJwt();
    const payload = parseJwtPayload(token);
    if (!token || payload?.role !== "super_admin") {
      window.location.href = "/login";
      return;
    }
    load();
  }, [load]);

  useEffect(() => {
    const onMsg = (e) => {
      if (e.origin !== window.location.origin) return;
      if (e.data?.type === "dept_oauth_success") load();
    };
    window.addEventListener("message", onMsg);

    const params = new URLSearchParams(window.location.search);
    if (params.get("dept_oauth") === "success") {
      params.delete("dept_oauth");
      const rest = params.toString();
      window.history.replaceState(
        {},
        "",
        `${window.location.pathname}${rest ? `?${rest}` : ""}${window.location.hash}`
      );
      if (window.opener && !window.opener.closed) {
        try {
          window.opener.postMessage({ type: "dept_oauth_success" }, window.location.origin);
        } catch {
          /* ignore */
        }
        window.close();
      } else {
        load();
      }
    }

    return () => window.removeEventListener("message", onMsg);
  }, [load]);

  const handleLogout = () => {
    clearDashboardSessionCache();
    setAppJwt(null);
    window.location.href = "/login";
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    setError("");
    if (!createForm.password || createForm.password.length < 6) {
      setError("Password must be at least 6 characters.");
      return;
    }
    try {
      await createAdminDepartment({
        name: createForm.name.trim(),
        username: createForm.username.trim(),
        password: createForm.password,
        distribution_emails: createForm.distributionEmails,
        admin_email: createForm.adminEmail?.trim() || null,
        config: { ...createForm.config },
      });
      setShowCreate(false);
      setCreateForm(defaultCreateForm());
      setCreateDistError("");
      await load();
    } catch (err) {
      setError(err?.response?.data?.detail || "Create failed.");
    }
  };

  const openEdit = async (id) => {
    setError("");
    setEditDistError("");
    setEditLoading(true);
    setEditingId(id);
    try {
      const d = await getAdminDepartment(id);
      setEditForm({
        name: d.name || "",
        username: d.dept_username || "",
        password: "",
        distributionEmails: [...(d.distribution_emails || [])].sort(),
        emailDraft: "",
        adminEmail: d.admin_email || "",
        config: {
          scheduler_interval_seconds: d.scheduler_interval_seconds ?? 300,
          intake_folder: d.intake_folder,
          processed_folder: d.processed_folder,
          output_success_folder: d.output_success_folder,
          output_failure_folder: d.output_failure_folder,
        },
      });
    } catch (err) {
      setError(err?.response?.data?.detail || "Failed to load department.");
      setEditingId(null);
      setEditForm(null);
    } finally {
      setEditLoading(false);
    }
  };

  const handleEditSave = async (e) => {
    e.preventDefault();
    if (!editingId || !editForm) return;
    setError("");
    try {
      const body = {
        name: editForm.name.trim(),
        username: editForm.username.trim(),
        distribution_emails: editForm.distributionEmails,
        admin_email: editForm.adminEmail?.trim() || null,
        config: { ...editForm.config },
      };
      if (editForm.password.trim()) {
        body.password = editForm.password.trim();
      }
      await updateAdminDepartment(editingId, body);
      setEditingId(null);
      setEditForm(null);
      await load();
    } catch (err) {
      setError(err?.response?.data?.detail || "Save failed.");
    }
  };

  const handleDelete = async (id, name) => {
    if (!window.confirm(`Delete department "${name}"? This cannot be undone.`)) return;
    try {
      await deleteAdminDepartment(id);
      setExpanded((ex) => {
        const n = { ...ex };
        delete n[id];
        return n;
      });
      await load();
    } catch (err) {
      setError(err?.response?.data?.detail || "Delete failed.");
    }
  };

  const connectMicrosoft = (id) => {
    const url = getMicrosoftDeptLoginUrl(id);
    const features = "width=520,height=700,menubar=no,toolbar=no,scrollbars=yes,resizable=yes";
    const w = window.open(url, "microsoft_dept_oauth", features);
    if (!w || typeof w.closed === "undefined" || w.closed) {
      window.location.href = url;
    }
  };

  const toggleExpand = (id) => {
    setExpanded((ex) => ({ ...ex, [id]: !ex[id] }));
  };

  return (
    <div className="min-h-screen bg-slate-100 flex flex-col">
      <header className="bg-slate-900 text-white px-6 py-4 flex items-center justify-between shadow">
        <div>
          <div className="text-lg font-semibold">Admin console</div>
          <div className="text-xs text-slate-400">All departments</div>
        </div>
        <div className="flex gap-2">
          <button type="button" className="text-sm px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-500" onClick={handleLogout}>
            Log out
          </button>
        </div>
      </header>

      <main className="flex-1 w-full max-w-[min(1800px,96vw)] mx-auto px-4 py-6 sm:px-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-slate-800">Departments</h2>
          <button
            type="button"
            onClick={() => {
              setCreateForm(defaultCreateForm());
              setCreateDistError("");
              setShowCreate(true);
            }}
            className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700"
          >
            Create department
          </button>
        </div>

        {error && <div className="mb-4 text-sm text-red-700 bg-red-50 border border-red-100 rounded-lg px-3 py-2">{error}</div>}

        {loading ? (
          <div className="text-slate-500">Loading…</div>
        ) : rows.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center text-slate-500">
            No departments yet. Create one to get started.
          </div>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 text-slate-600 text-left">
                <tr>
                  <th className="px-2 py-3 w-10" aria-label="Expand" />
                  <th className="px-4 py-3 font-medium">Name</th>
                  <th className="px-4 py-3 font-medium">Dept login</th>
                  <th className="px-4 py-3 font-medium">Admin</th>
                  <th className="px-4 py-3 font-medium">Microsoft</th>
                  <th className="px-4 py-3 font-medium">Interval</th>
                  <th className="px-4 py-3 font-medium">Intake folder</th>
                  <th className="px-4 py-3 font-medium text-center">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <React.Fragment key={r.id}>
                    <tr
                      className="border-t border-slate-100 hover:bg-slate-50/80 cursor-pointer"
                      onClick={() => toggleExpand(r.id)}
                      aria-expanded={Boolean(expanded[r.id])}
                      aria-label={`${r.name}: ${expanded[r.id] ? "Collapse" : "Expand"} row details`}
                    >
                      <td className="px-2 py-3 align-middle text-slate-500">
                        <span className="inline-flex p-1 pointer-events-none" aria-hidden>
                          {expanded[r.id] ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-medium text-slate-900">{r.name}</td>
                      <td className="px-4 py-3 text-slate-700">{r.dept_username}</td>
                      <td className="px-4 py-3 text-slate-600 max-w-[220px] truncate" title={r.admin_email || ""}>
                        {r.admin_email || "—"}
                      </td>
                      <td className="px-4 py-3">
                        {r.oauth_connected ? (
                          <span className="text-emerald-700">Connected{r.connected_email ? ` (${r.connected_email})` : ""}</span>
                        ) : (
                          <span className="text-amber-700">Not connected</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-slate-600">{formatIntervalHuman(r.scheduler_interval_seconds)}</td>
                      <td className="px-4 py-3 text-slate-500 max-w-md truncate" title={r.intake_folder}>
                        {r.intake_folder}
                      </td>
                      <td className="px-4 py-3 align-middle" onClick={(e) => e.stopPropagation()}>
                        <div className="flex flex-wrap items-center justify-center gap-2">
                          <button
                            type="button"
                            className="inline-flex items-center justify-center gap-1.5 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50"
                            onClick={() => openEdit(r.id)}
                          >
                            <Pencil size={14} aria-hidden />
                            Edit
                          </button>
                          <button
                            type="button"
                            className="inline-flex items-center justify-center gap-1.5 rounded-md border border-indigo-600 bg-indigo-600 px-2.5 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-indigo-700"
                            onClick={() => connectMicrosoft(r.id)}
                            title="Connect Microsoft account"
                          >
                            <Plug size={14} aria-hidden />
                            Connect
                          </button>
                          <button
                            type="button"
                            className="inline-flex items-center justify-center gap-1.5 rounded-md border border-red-200 bg-white px-2.5 py-1.5 text-xs font-medium text-red-600 shadow-sm hover:bg-red-50"
                            onClick={() => handleDelete(r.id, r.name)}
                          >
                            <Trash2 size={14} aria-hidden />
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                    {expanded[r.id] && (
                      <tr className="border-t border-slate-100 bg-slate-50/90">
                        <td colSpan={8} className="px-6 py-4 text-xs text-slate-700">
                          <div className="grid sm:grid-cols-2 gap-4">
                            <div>
                              <div className="font-semibold text-slate-800 mb-2">Folders</div>
                              <ul className="space-y-1 font-mono text-[11px]">
                                <li>
                                  <span className="text-slate-500">Intake:</span> {r.intake_folder}
                                </li>
                                <li>
                                  <span className="text-slate-500">Processed:</span> {r.processed_folder}
                                </li>
                                <li>
                                  <span className="text-slate-500">Output success:</span> {r.output_success_folder}
                                </li>
                                <li>
                                  <span className="text-slate-500">Output failure:</span> {r.output_failure_folder}
                                </li>
                              </ul>
                            </div>
                            <div>
                              <div className="font-semibold text-slate-800 mb-2 flex items-center gap-1">
                                <Mail size={14} />
                                Distribution ({(r.distribution_emails || []).length})
                              </div>
                              {(r.distribution_emails || []).length === 0 ? (
                                <p className="text-slate-500">No distribution emails.</p>
                              ) : (
                                <ul className="flex flex-wrap gap-1">
                                  {(r.distribution_emails || []).map((em) => (
                                    <li key={em} className="px-2 py-0.5 rounded-full bg-white border border-slate-200 break-all">
                                      {em}
                                    </li>
                                  ))}
                                </ul>
                              )}
                              <p className="mt-2 text-slate-600">
                                <span className="text-slate-500">Department admin:</span> {r.admin_email || "—"}
                              </p>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>

      {showCreate && (
        <div
          className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
          onClick={() => setShowCreate(false)}
          role="presentation"
        >
          <div
            className="bg-white rounded-xl shadow-xl max-w-lg w-full max-h-[90vh] overflow-y-auto p-6"
            onClick={(e) => e.stopPropagation()}
            role="presentation"
          >
            <h3 className="text-lg font-semibold mb-4">Create department</h3>
            <form onSubmit={handleCreate} className="space-y-3">
              <DepartmentFormFields
                form={createForm}
                setForm={setCreateForm}
                distError={createDistError}
                setDistError={setCreateDistError}
                passwordOptional={false}
              />
              <div className="flex justify-end gap-2 pt-2">
                <button type="button" className="px-3 py-2 rounded border" onClick={() => setShowCreate(false)}>
                  Cancel
                </button>
                <button type="submit" className="px-4 py-2 rounded bg-indigo-600 text-white">
                  Create
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {editingId && (
        <div
          className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
          onClick={() => {
            setEditingId(null);
            setEditForm(null);
          }}
          role="presentation"
        >
          <div
            className="bg-white rounded-xl shadow-xl max-w-lg w-full max-h-[90vh] overflow-y-auto p-6"
            onClick={(e) => e.stopPropagation()}
            role="presentation"
          >
            <h3 className="text-lg font-semibold mb-4">Edit department</h3>
            {editLoading || !editForm ? (
              <div className="text-slate-500 py-8 text-center">Loading…</div>
            ) : (
              <form onSubmit={handleEditSave} className="space-y-3">
                <DepartmentFormFields
                  form={editForm}
                  setForm={setEditForm}
                  distError={editDistError}
                  setDistError={setEditDistError}
                  passwordOptional
                />
                <div className="flex justify-end gap-2 pt-2">
                  <button
                    type="button"
                    className="px-3 py-2 rounded border"
                    onClick={() => {
                      setEditingId(null);
                      setEditForm(null);
                    }}
                  >
                    Cancel
                  </button>
                  <button type="submit" className="px-4 py-2 rounded bg-indigo-600 text-white">
                    Save changes
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
