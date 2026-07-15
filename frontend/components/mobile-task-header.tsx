import type { ReactNode } from "react";

type MobileTaskHeaderProps = {
  eyebrow: ReactNode;
  title: ReactNode;
  description: ReactNode;
  status?: ReactNode;
};

/** A phone-only, task-first summary that replaces the decorative desktop hero. */
export function MobileTaskHeader({ eyebrow, title, description, status }: MobileTaskHeaderProps) {
  return (
    <section className="mobile-task-header" aria-label="当前功能">
      <div className="mobile-task-header__eyebrow">{eyebrow}</div>
      <h1>{title}</h1>
      <p>{description}</p>
      {status ? <div className="mobile-task-header__status">{status}</div> : null}
    </section>
  );
}
