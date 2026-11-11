import type { ReactNode } from "react";
import { cn } from "../lib/utils";

export function Brand() {
  return <div className="brand">
    <svg viewBox="0 0 40 40" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 18h32v5a13 13 0 0 1-10 12H14A13 13 0 0 1 4 23zM13 35h14M12 12c-3-3 3-4 0-7M20 12c-3-3 3-4 0-7M28 12c-3-3 3-4 0-7" />
    </svg>
    <span>今天吃什么</span>
  </div>;
}

export function PageHero({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <header className={cn("page-hero", className)}>{children}</header>;
}
