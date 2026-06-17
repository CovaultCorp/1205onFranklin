import type { ReactNode } from "react";

export function PageTitle({
  eyebrow,
  title,
  description,
  action
}: {
  eyebrow: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-header">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1 className="text-3xl font-bold tracking-tight">{title}</h1>
        {description ? <p className="mt-2 max-w-2xl text-sm text-default-500">{description}</p> : null}
      </div>
      {action}
    </div>
  );
}
