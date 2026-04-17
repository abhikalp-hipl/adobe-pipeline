import React from "react";

function ErrorPopup({ error, onClose, onRetry }) {
  if (!error) {
    return null;
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl p-6 w-full max-w-md shadow-lg border">
        <div className="text-red-600 font-semibold mb-2 text-lg">Pipeline Failed</div>

        <div className="space-y-2">
          <p className="text-sm">
            <span className="text-gray-500">File:</span> <span className="font-medium">{error.file || "-"}</span>
          </p>
          <p className="text-sm">
            <span className="text-gray-500">Step:</span> <span className="font-medium">{error.step || "-"}</span>
          </p>
          <p className="text-sm text-red-500">{error.message || "Unknown error"}</p>
        </div>

        <div className="flex justify-end gap-2 mt-5">
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded"
            >
              Retry
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            className="bg-gray-200 hover:bg-gray-300 text-gray-800 px-4 py-2 rounded"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

export default ErrorPopup;

