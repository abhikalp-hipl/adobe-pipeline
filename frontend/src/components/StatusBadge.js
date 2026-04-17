import React from "react";

const stylesByStatus = {
  UPLOADED: "bg-gray-200 text-gray-800",
  PROCESSING: "bg-blue-200 text-blue-800",
  TAGGED: "bg-orange-200 text-orange-800",
  CHECKED: "bg-purple-200 text-purple-800",
  COMPLETED: "bg-green-200 text-green-800",
  FAILED: "bg-red-200 text-red-800",
};

function StatusBadge({ status }) {
  const style = stylesByStatus[status] || "bg-gray-100 text-gray-700";
  return (
    <span className={`px-2 py-1 rounded text-xs font-medium ${style}`}>
      {status || "UNKNOWN"}
    </span>
  );
}

export default StatusBadge;
