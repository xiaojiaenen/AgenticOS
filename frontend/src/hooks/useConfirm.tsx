import { useState, useCallback } from 'react';

interface ConfirmState {
  open: boolean;
  title: string;
  message: string;
  onConfirm: () => void;
}

export function useConfirm() {
  const [state, setState] = useState<ConfirmState>({ open: false, title: '', message: '', onConfirm: () => {} });

  const confirm = useCallback((title: string, message: string): Promise<boolean> => {
    return new Promise((resolve) => {
      setState({
        open: true,
        title,
        message,
        onConfirm: () => { setState(s => ({ ...s, open: false })); resolve(true); },
      });
    });
  }, []);

  const cancel = useCallback(() => {
    setState(s => ({ ...s, open: false }));
  }, []);

  return { ...state, confirm, cancel };
}
