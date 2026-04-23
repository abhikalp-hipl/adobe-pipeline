import React from "react";
import { Mail, XCircle } from "lucide-react";

export default function EmailModal({
  open,
  onClose,
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
  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl w-[400px] p-6 shadow-lg max-h-[85vh] overflow-y-auto">
        <div className="mb-4">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Mail size={16} />
            Notification Emails
          </h2>
          <p className="text-sm text-gray-500">
            {emails.length} recipient{emails.length === 1 ? "" : "s"}
          </p>
        </div>

        <input
          type="email"
          placeholder="Enter email"
          value={emailInput}
          onChange={(event) => setEmailInput(event.target.value)}
          className="input"
        />
        <button
          type="button"
          onClick={handleAddEmails}
          disabled={!canAddEmails}
          className="btn-primary mt-2 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isSavingEmail ? "Adding..." : "Add"}
        </button>

        {invalidEmailCandidates.length > 0 && (
          <p className="text-sm text-red-600 mt-2">Enter valid email address(es), comma separated.</p>
        )}

        <div className="mt-4">
          {emails.length === 0 ? (
            <div className="text-sm text-gray-500">No emails added</div>
          ) : (
            emails.map((item) => (
              <div key={item.id} className="flex justify-between items-center mt-2 border rounded px-3 py-2">
                <span className="text-sm break-all">{item.email}</span>
                <button
                  type="button"
                  onClick={() => handleDeleteEmail(item.id)}
                  disabled={deletingEmailId === item.id}
                  className="text-red-600 hover:text-red-700 disabled:text-red-300"
                  aria-label={`Delete ${item.email}`}
                >
                  <XCircle size={16} />
                </button>
              </div>
            ))
          )}
        </div>

        <div className="flex justify-end mt-6">
          <button type="button" onClick={onClose} className="px-4 py-2 rounded bg-gray-200 hover:bg-gray-300">
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
