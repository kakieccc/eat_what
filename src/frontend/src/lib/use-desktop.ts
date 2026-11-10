import { useSyncExternalStore } from "react";

const viewport = window.matchMedia("(min-width: 1024px)");
const subscribe = (notify: () => void) => {
  viewport.addEventListener("change", notify);
  return () => viewport.removeEventListener("change", notify);
};

export function useDesktop() {
  return useSyncExternalStore(subscribe, () => viewport.matches);
}
