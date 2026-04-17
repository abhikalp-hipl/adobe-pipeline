import React, { useState } from "react";

import { uploadDocument } from "../services/api";

function Upload({ onUploadComplete }) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const handleUpload = async () => {
    if (!selectedFile) {
      setError("Please select a file first.");
      return;
    }

    setIsUploading(true);
    setError("");
    setMessage("");
    try {
      const result = await uploadDocument(selectedFile);
      setMessage(`Uploaded: ${result.filename}`);
      setSelectedFile(null);
      if (onUploadComplete) {
        onUploadComplete();
      }
    } catch (uploadError) {
      setError(uploadError?.response?.data?.detail || "Upload failed.");
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="bg-white shadow rounded-xl p-4">
      <h2 className="text-lg font-semibold mb-4">Upload</h2>
      <input
        type="file"
        className="border p-2 rounded w-full"
        onChange={(event) => setSelectedFile(event.target.files?.[0] || null)}
      />
      <button
        type="button"
        onClick={handleUpload}
        disabled={isUploading}
        className="bg-blue-500 hover:bg-blue-600 disabled:opacity-60 text-white px-4 py-2 rounded mt-2"
      >
        {isUploading ? "Uploading..." : "Upload"}
      </button>
      {message && <p className="mt-2 text-sm text-green-600">{message}</p>}
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </div>
  );
}

export default Upload;
