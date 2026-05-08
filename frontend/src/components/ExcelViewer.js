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
  const [workbook, setWorkbook] = useState(null);
  const [sheetNames, setSheetNames] = useState([]);
  const [selectedSheet, setSelectedSheet] = useState("");
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const parse = async () => {
      if (!data) {
        setWorkbook(null);
        setSheetNames([]);
        setSelectedSheet("");
        setRows([]);
        setError("");
        return;
      }
      setIsParsing(true);
      setError("");
      try {
        const parsedWorkbook = XLSX.read(data, { type: "array" });
        const allSheetNames = Array.isArray(parsedWorkbook?.SheetNames) ? parsedWorkbook.SheetNames : [];
        if (!cancelled) {
          setWorkbook(parsedWorkbook);
          setSheetNames(allSheetNames);
          setSelectedSheet((current) => (current && allSheetNames.includes(current) ? current : allSheetNames[0] || ""));
        }
      } catch (e) {
        if (!cancelled) {
          setWorkbook(null);
          setSheetNames([]);
          setSelectedSheet("");
          setError("Failed to parse XLSX file.");
          setRows([]);
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

  useEffect(() => {
    if (!workbook || !selectedSheet) {
      setRows([]);
      return;
    }
    const sheet = workbook.Sheets?.[selectedSheet] || null;
    const jsonData = sheet ? XLSX.utils.sheet_to_json(sheet, { header: 1 }) : [];
    setRows(Array.isArray(jsonData) ? jsonData : []);
  }, [workbook, selectedSheet]);

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
        <div className="flex items-center gap-2 text-sm text-slate-700">
          <span>Sheet:</span>
          {sheetNames.length > 0 ? (
            <select
              className="border rounded px-2 py-1 text-sm bg-white"
              value={selectedSheet}
              onChange={(event) => setSelectedSheet(event.target.value)}
            >
              {sheetNames.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
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

