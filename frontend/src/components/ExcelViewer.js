import React, { useEffect, useMemo, useState } from "react";

import * as XLSX from "xlsx";

function normalizeCell(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return String(value);
}

function ExcelViewer({ data }) {
  const [isParsing, setIsParsing] = useState(false);
  const [sheetName, setSheetName] = useState("");
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const parse = async () => {
      if (!data) {
        setRows([]);
        setSheetName("");
        setError("");
        return;
      }
      setIsParsing(true);
      setError("");
      try {
        const workbook = XLSX.read(data, { type: "array" });
        const firstSheetName = workbook?.SheetNames?.[0] || "";
        const sheet = firstSheetName ? workbook.Sheets[firstSheetName] : null;
        const jsonData = sheet ? XLSX.utils.sheet_to_json(sheet, { header: 1 }) : [];
        if (!cancelled) {
          setSheetName(firstSheetName);
          setRows(Array.isArray(jsonData) ? jsonData : []);
        }
      } catch (e) {
        if (!cancelled) {
          setError("Failed to parse XLSX file.");
          setRows([]);
          setSheetName("");
        }
      } finally {
        if (!cancelled) {
          setIsParsing(false);
        }
      }
    };
    parse();
    return () => {
      cancelled = true;
    };
  }, [data]);

  const normalizedRows = useMemo(() => {
    if (!Array.isArray(rows) || rows.length === 0) {
      return [];
    }
    const maxCols = rows.reduce((max, row) => Math.max(max, Array.isArray(row) ? row.length : 0), 0);
    return rows.map((row) => {
      const safeRow = Array.isArray(row) ? row : [];
      return Array.from({ length: maxCols }, (_, idx) => normalizeCell(safeRow[idx]));
    });
  }, [rows]);

  return (
    <div className="bg-white shadow rounded-xl p-4 overflow-auto max-h-[80vh] border">
      <div className="flex items-center justify-between mb-3">
        <div className="text-sm text-slate-700">
          {sheetName ? (
            <>
              Sheet: <span className="font-semibold">{sheetName}</span>
            </>
          ) : (
            <span className="text-slate-500">No sheet found</span>
          )}
        </div>
        {isParsing && (
          <div className="flex items-center gap-2 text-sm text-gray-600">
            <span className="inline-block w-4 h-4 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
            Parsing...
          </div>
        )}
      </div>

      {error && <p className="text-sm text-red-600 mb-2">{error}</p>}

      {!isParsing && !error && normalizedRows.length === 0 && (
        <p className="text-sm text-slate-500">This Excel sheet is empty.</p>
      )}

      {normalizedRows.length > 0 && (
        <table className="min-w-full text-sm text-left border">
          <tbody>
            {normalizedRows.map((row, i) => (
              <tr key={i} className={`border-b ${i === 0 ? "bg-gray-100 font-semibold" : ""}`}>
                {row.map((cell, j) => (
                  <td key={j} className="px-3 py-2 border whitespace-nowrap">
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default ExcelViewer;

