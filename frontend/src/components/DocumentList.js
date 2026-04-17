import React, { useEffect, useState } from "react";

import { getDocuments, processDocument } from "../services/api";
import StatusBadge from "./StatusBadge";

function DocumentList({ refreshKey }) {
  const [documents, setDocuments] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [processingId, setProcessingId] = useState("");

  const fetchDocuments = async () => {
    try {
      const data = await getDocuments();
      setDocuments(data);
      setError("");
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Failed to fetch documents.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, [refreshKey]);

  const handleProcess = async (id) => {
    setProcessingId(id);
    try {
      await processDocument(id);
      await fetchDocuments();
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Failed to process document.");
    } finally {
      setProcessingId("");
    }
  };

  return (
    <div className="bg-white shadow rounded-xl p-4">
      <h2 className="text-lg font-semibold mb-4">Documents</h2>
      {isLoading && <p className="text-sm text-gray-500 mb-4">Loading documents...</p>}
      {error && <p className="text-sm text-red-600 mb-4">{error}</p>}

      <table className="w-full text-left">
        <thead>
          <tr className="text-sm text-gray-500 border-b">
            <th className="py-2">Filename</th>
            <th className="py-2">Status</th>
            <th className="py-2">Created At</th>
            <th className="py-2">Action</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => (
            <tr key={doc.id} className="border-b hover:bg-gray-50">
              <td className="py-3 pr-2 text-sm text-slate-700 break-all">{doc.filename}</td>
              <td className="py-3 pr-2">
                <StatusBadge status={doc.status} />
              </td>
              <td className="py-3 pr-2 text-sm text-slate-600">
                {doc.created_at ? new Date(doc.created_at).toLocaleString() : "-"}
              </td>
              <td className="py-3">
                <button
                  type="button"
                  onClick={() => handleProcess(doc.id)}
                  disabled={processingId === doc.id}
                  className="bg-blue-500 hover:bg-blue-600 disabled:opacity-60 text-white px-3 py-1 rounded"
                >
                  {processingId === doc.id ? "Processing..." : "Process"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default DocumentList;
