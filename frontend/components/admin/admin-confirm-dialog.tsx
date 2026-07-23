"use client";

import { AlertTriangle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useModalAccessibility } from "@/lib/modal-accessibility";

export type AdminConfirmIntent = {
  actionLabel: string;
  confirmLabel: string;
  description: string;
  details?: string[];
  danger?: boolean;
  reasonLabel?: string;
  reasonPlaceholder?: string;
  reasonRequired?: boolean;
  initialReason?: string;
  busyLabel?: string;
  onConfirm: (reason: string) => Promise<void> | void;
};

export function AdminConfirmDialog({
  intent,
  submitting,
  onClose,
}: {
  intent: AdminConfirmIntent | null;
  submitting: boolean;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLElement>(null);
  const [reason, setReason] = useState("");

  useEffect(() => {
    setReason(intent?.initialReason || "");
  }, [intent]);

  useModalAccessibility(Boolean(intent), onClose, dialogRef, !submitting);

  if (!intent) return null;

  const reasonRequired = Boolean(intent.reasonRequired);
  const reasonInvalid = reasonRequired && reason.trim().length < 2;

  async function handleConfirm() {
    if (!intent || submitting || reasonInvalid) return;
    await intent.onConfirm(reason.trim());
  }

  return (
    <div className="admin-publish-backdrop" role="presentation" onMouseDown={() => !submitting && onClose()}>
      <section
        className="admin-publish-dialog admin-confirm-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="admin-confirm-title"
        ref={dialogRef}
        tabIndex={-1}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <AlertTriangle aria-hidden="true" />
        <h2 id="admin-confirm-title">{intent.actionLabel}</h2>
        <p>{intent.description}</p>
        {intent.details?.length ? (
          <div className="admin-confirm-details">
            {intent.details.map((detail) => (
              <span key={detail}>{detail}</span>
            ))}
          </div>
        ) : null}
        {intent.reasonLabel ? (
          <label className="admin-confirm-reason">
            <span>{intent.reasonLabel}</span>
            <textarea
              rows={4}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder={intent.reasonPlaceholder || ""}
              aria-invalid={reasonInvalid || undefined}
            />
          </label>
        ) : null}
        {reasonInvalid ? <div className="admin-alert">请至少填写 2 个字的处理说明。</div> : null}
        <div className="admin-confirm-actions">
          <button type="button" className={intent.danger ? "admin-danger-button" : ""} onClick={handleConfirm} disabled={submitting || reasonInvalid}>
            {submitting ? intent.busyLabel || "正在提交..." : intent.confirmLabel}
          </button>
          <button type="button" className="admin-secondary-button" onClick={onClose} disabled={submitting}>
            取消
          </button>
        </div>
      </section>
    </div>
  );
}
