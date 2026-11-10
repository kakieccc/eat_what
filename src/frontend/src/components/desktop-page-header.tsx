import type { ReactNode } from "react";

export function DesktopPageHeader({ title, description, children }: {
  title: string;
  description?: ReactNode;
  children?: ReactNode;
}) {
  return <header className="desktop-page-header">
    <div><h1>{title}</h1>{description && <p>{description}</p>}</div>
    {children}
  </header>;
}
