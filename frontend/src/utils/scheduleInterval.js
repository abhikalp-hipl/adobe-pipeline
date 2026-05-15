/** Preset values for "every N minutes/hours" (matches dashboard modal). */
export const PRESET_INTERVALS = [1, 2, 5, 10, 15, 30, 60];

/**
 * Map persisted seconds to dashboard-style picker state.
 * @returns {{ value: number, unit: 'minutes'|'hours'|'seconds', isCustom: boolean }}
 */
export function secondsToPickerState(intervalSeconds) {
  const s = Number(intervalSeconds);
  if (!Number.isFinite(s) || s <= 0) {
    return { value: 5, unit: "minutes", isCustom: false };
  }

  if (s % 60 === 0) {
    const minutes = s / 60;
    if (s % 3600 === 0 && minutes / 60 >= 1 && Number.isInteger(minutes / 60)) {
      const hours = minutes / 60;
      if (PRESET_INTERVALS.includes(hours)) {
        return { value: hours, unit: "hours", isCustom: false };
      }
    }
    if (PRESET_INTERVALS.includes(minutes)) {
      return { value: minutes, unit: "minutes", isCustom: false };
    }
    return { value: minutes, unit: "minutes", isCustom: true };
  }

  return { value: Math.max(1, Math.floor(s)), unit: "seconds", isCustom: true };
}

/** @param {number} value @param {'minutes'|'hours'|'seconds'} unit */
export function pickerStateToSeconds(value, unit) {
  const v = Number(value);
  if (!Number.isFinite(v) || v < 1) return 300;
  if (unit === "hours") return Math.max(1, Math.floor(v)) * 3600;
  if (unit === "minutes") return Math.max(1, Math.floor(v)) * 60;
  return Math.max(60, Math.floor(v));
}

/** Short label for tables (e.g. "every 5 min", "every 1 hour"). */
export function formatIntervalHuman(seconds) {
  const s = Number(seconds) || 0;
  if (s <= 0) return "—";
  if (s % 3600 === 0) {
    const h = s / 3600;
    return `every ${h} hour${h === 1 ? "" : "s"}`;
  }
  if (s % 60 === 0) {
    const m = s / 60;
    return `every ${m} min`;
  }
  return `every ${s}s`;
}
