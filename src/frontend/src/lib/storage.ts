import type { StateStorage } from "zustand/middleware";

let disabled = false;
function disable(error: unknown) {
  if (!disabled) console.error("Session storage unavailable; changes remain in memory", error);
  disabled = true;
  try { sessionStorage.removeItem("food-draft-v1"); } catch { /* The storage failure was reported above. */ }
}

export const safeSessionStorage: StateStorage = {
  getItem(key) {
    if (disabled) return null;
    try { return sessionStorage.getItem(key); } catch (error) { disable(error); return null; }
  },
  setItem(key, value) {
    if (disabled) return;
    try { sessionStorage.setItem(key, value); } catch (error) { disable(error); }
  },
  removeItem(key) {
    try { sessionStorage.removeItem(key); } catch (error) { disable(error); }
  },
};
