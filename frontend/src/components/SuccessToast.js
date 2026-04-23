import React, { useEffect } from "react";
import { CheckCircle } from "lucide-react";

function SuccessToast({ success, onDismiss }) {
  useEffect(() => {
    const id = window.setTimeout(() => {
      onDismiss?.();
    }, 3000);
    return () => window.clearTimeout(id);
  }, [onDismiss]);

  if (!success) {
    return null;
  }

  return (
    <div className="fixed top-5 right-5 bg-green-500 text-white px-4 py-3 rounded-lg shadow-lg z-50 flex items-center gap-2">
      <CheckCircle size={16} aria-hidden />
      <div>
        <p className="text-sm font-semibold">Pipeline Completed</p>
        <p className="text-xs">{success.file || ""}</p>
      </div>
    </div>
  );
}

export default SuccessToast;

