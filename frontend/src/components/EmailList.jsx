import React from "react";
import { Mail, XCircle } from "lucide-react";
import Button from "./Button";

export default function EmailList({
  emails,
  emailInput,
  setEmailInput,
  canAddEmails,
  isSavingEmail,
  invalidEmailCandidates,
  handleAddEmails,
  handleDeleteEmail,
  deletingEmailId,
}) {
  return (
    <section className="card">
      <div className="mb-3">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Mail size={16} />
          Notification Emails
        </h2>
        <p className="text-sm text-gray-500">{emails.length} recipient{emails.length === 1 ? "" : "s"}</p>
      </div>
      <div className="flex gap-2 mb-3">
        <input type="email" placeholder="Enter email" value={emailInput} onChange={(event) => setEmailInput(event.target.value)} className="input" />
        <Button onClick={handleAddEmails} disabled={!canAddEmails}>
          {isSavingEmail ? "Adding..." : "Add"}
        </Button>
      </div>
      {invalidEmailCandidates.length > 0 && <p className="text-sm text-red-600 mb-3">Enter valid email address(es), comma separated.</p>}
      {emails.length === 0 ? (
        <div className="text-sm text-gray-500 mb-3">No emails added</div>
      ) : (
        <div className="space-y-2 mb-3">
          {emails.map((item) => (
            <div key={item.id} className="flex items-center justify-between border rounded px-3 py-2">
              <span className="text-sm text-gray-800 break-all">{item.email}</span>
              <button type="button" onClick={() => handleDeleteEmail(item.id)} disabled={deletingEmailId === item.id} className="text-red-600 hover:text-red-700 disabled:text-red-300 flex items-center" aria-label={`Delete ${item.email}`}>
                <XCircle size={16} />
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
