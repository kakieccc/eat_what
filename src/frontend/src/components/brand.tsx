import type { ReactNode } from "react";
import { cn } from "../lib/utils";

export function BrandMark({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <path d="M24 7a17 17 0 1 0 16 11" stroke="currentColor" strokeWidth="7" />
      <circle cx="35" cy="9" r="5" fill="currentColor" />
    </svg>
  );
}

export function Brand() {
  return <div className="brand"><BrandMark /><span>今天吃什么</span></div>;
}

export function BrandArcs() {
  return (
    <svg className="brand-arcs" viewBox="0 0 180 180" fill="none" aria-hidden="true">
      <path d="M178 54a65 65 0 0 1-65-65M92 68a62 62 0 1 0 46 20" stroke="currentColor" strokeWidth="10" />
      <circle cx="114" cy="77" r="10" fill="currentColor" />
    </svg>
  );
}

export function PageHero({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <header className={cn("page-hero", className)}><BrandArcs />{children}</header>;
}
