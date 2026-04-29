import React from 'react';

const MODAL_OPEN_CLASS = 'admin-modal-open';
const MODAL_COUNT_ATTR = 'data-admin-modal-count';

export function useAdminModalBackdrop(active: boolean): void {
  React.useEffect(() => {
    if (!active || typeof document === 'undefined') {
      return;
    }

    const { body } = document;
    const currentCount = Number(body.getAttribute(MODAL_COUNT_ATTR) || '0');
    const nextCount = currentCount + 1;

    body.setAttribute(MODAL_COUNT_ATTR, String(nextCount));
    body.classList.add(MODAL_OPEN_CLASS);

    return () => {
      const latestCount = Number(body.getAttribute(MODAL_COUNT_ATTR) || '1');
      const remainingCount = Math.max(0, latestCount - 1);

      if (remainingCount === 0) {
        body.removeAttribute(MODAL_COUNT_ATTR);
        body.classList.remove(MODAL_OPEN_CLASS);
        return;
      }

      body.setAttribute(MODAL_COUNT_ATTR, String(remainingCount));
    };
  }, [active]);
}
