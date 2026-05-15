import React, { useEffect, useState } from "react";
import { PRESET_INTERVALS, pickerStateToSeconds, secondsToPickerState } from "../utils/scheduleInterval";

/**
 * Dashboard-style "every N minutes/hours" control; persists interval in seconds (≥ 60).
 */
export default function ScheduleIntervalPicker({ valueSeconds, onChangeSeconds, idPrefix = "sched" }) {
  const [sched, setSched] = useState(() => secondsToPickerState(valueSeconds ?? 300));

  useEffect(() => {
    setSched(secondsToPickerState(valueSeconds ?? 300));
  }, [valueSeconds]);

  const push = (next) => {
    setSched(next);
    onChangeSeconds(pickerStateToSeconds(next.value, next.unit));
  };

  return (
    <div>
      <label className="block text-xs text-slate-500 mb-1" htmlFor={`${idPrefix}-interval`}>
        Automation interval
      </label>
      <p className="text-xs text-slate-400 mb-2">How often the pipeline checks OneDrive (same presets as the dashboard).</p>
      {!sched.isCustom ? (
        <div id={`${idPrefix}-interval`} className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-slate-600">Every</span>
          <select
            className="border rounded px-2 py-1.5 text-sm bg-white"
            value={sched.value}
            onChange={(e) => push({ ...sched, value: Number(e.target.value), isCustom: false })}
          >
            {PRESET_INTERVALS.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
          <select
            className="border rounded px-2 py-1.5 text-sm bg-white"
            value={sched.unit}
            onChange={(e) => {
              const unit = e.target.value;
              let v = sched.value;
              if (unit === "hours" && !PRESET_INTERVALS.includes(v)) v = 1;
              if (unit === "minutes" && !PRESET_INTERVALS.includes(v)) v = 5;
              push({ value: v, unit, isCustom: false });
            }}
          >
            <option value="minutes">minutes</option>
            <option value="hours">hours</option>
          </select>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-slate-600">Every</span>
          <input
            type="number"
            min={sched.unit === "seconds" ? 60 : 1}
            className="border rounded px-2 py-1.5 text-sm w-24"
            value={sched.value}
            onChange={(e) => push({ ...sched, value: Number(e.target.value) || 1 })}
          />
          <select
            className="border rounded px-2 py-1.5 text-sm bg-white"
            value={sched.unit}
            onChange={(e) => push({ ...sched, unit: e.target.value })}
          >
            <option value="seconds">seconds</option>
            <option value="minutes">minutes</option>
            <option value="hours">hours</option>
          </select>
        </div>
      )}
      {!sched.isCustom && (
        <button type="button" className="text-xs text-indigo-600 mt-1.5 hover:underline" onClick={() => push({ ...sched, isCustom: true })}>
          Custom interval…
        </button>
      )}
      {sched.isCustom && (
        <button
          type="button"
          className="text-xs text-indigo-600 mt-1.5 hover:underline"
          onClick={() => {
            const s = pickerStateToSeconds(sched.value, sched.unit);
            push(secondsToPickerState(s));
          }}
        >
          Use preset intervals
        </button>
      )}
      <p className="text-xs text-slate-500 mt-1">Saved as {valueSeconds ?? 300} seconds (minimum 60).</p>
    </div>
  );
}
