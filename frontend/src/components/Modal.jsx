import React from "react";

export default function Modal({ open, onClose, title, children, sizeClass = "w-[95vw] h-[92vh]" }) {
  if (!open) {
    return null;
  }
  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-40 flex items-center justify-center z-50 p-4"
      onClick={onClose}
      role="presentation"
    >
      <div
        className={`bg-white rounded-xl p-4 flex flex-col ${sizeClass}`}
        onClick={(event) => event.stopPropagation()}
        role="presentation"
      >
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-lg font-semibold">{title}</h3>
          <button
            type="button"
            onClick={onClose}
            className="bg-gray-700 hover:bg-gray-800 text-white px-3 py-1 rounded"
          >
            Close
          </button>
        </div>
        <div className="flex-1 overflow-auto">{children}</div>
      </div>
    </div>
  );
}
