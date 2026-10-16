import type { StateStorage } from "zustand/middleware";

let disabled = false;
function disable() {
  disabled = true;
  for (const key of ["food-draft-v1", "food-start"]) {
    try { sessionStorage.removeItem(key); } catch { /* Storage may be inaccessible. */ }
  }
}

export const safeSessionStorage: StateStorage = {
  getItem(key) {
    if (disabled) return null;
    try { return sessionStorage.getItem(key); } catch { disable(); return null; }
  },
  setItem(key, value) {
    if (disabled) return;
    try { sessionStorage.setItem(key, value); } catch { disable(); }
  },
  removeItem(key) {
    try { sessionStorage.removeItem(key); } catch { disable(); }
  },
};
