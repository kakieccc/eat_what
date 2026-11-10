import type { ReactNode } from "react";
import { Utensils } from "lucide-react";
import { cn } from "../lib/utils";

export function Brand() {
  return <div className="brand"><Utensils aria-hidden="true" /><span>今天吃什么</span></div>;
}

export function PageHero({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <header className={cn("page-hero", className)}>{children}</header>;
}
