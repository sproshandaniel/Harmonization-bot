import type { ReactNode } from "react";

export default function Modal({
  open, onClose, title, children, footer
}: { open: boolean; onClose: () => void; title?: string; children?: ReactNode; footer?: ReactNode; }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="absolute left-1/2 top-1/2 w-[92vw] md:w-[900px] -translate-x-1/2 -translate-y-1/2 bg-white rounded-lg shadow-xl border">
        {title && (
          <div className="px-5 py-3 border-b font-semibold text-gray-700">
            {title}
          </div>
        )}
        <div className="p-5">{children}</div>
        {footer && <div className="px-5 py-3 border-t bg-gray-50">{footer}</div>}
      </div>
    </div>
  );
}
