import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";

/* The side panel (aside.detail): what a click on a diagram's part, a row or a goal opens beside the page. One at a
   time, for the whole app; closed by Escape, its close button, or going to another page. A page opens it with
   ``useDetail().open(key, <Content/>)``; ``key`` says what is shown, so the page can mark it selected. */

interface DetailApi {
  key: string | null;
  open: (key: string, content: ReactNode) => void;
  close: () => void;
}

const DetailContext = createContext<DetailApi>({ key: null, open: () => {}, close: () => {} });

export function DetailProvider({ children }: { children: ReactNode }) {
  const [shown, setShown] = useState<{ key: string; content: ReactNode } | null>(null);
  const close = useCallback(() => setShown(null), []);
  const open = useCallback((key: string, content: ReactNode) => setShown({ key, content }), []);
  const { pathname } = useLocation();

  useEffect(() => close(), [pathname, close]);
  useEffect(() => {
    const esc = (ev: KeyboardEvent) => { if (ev.key === "Escape") close(); };
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [close]);

  return (
    <DetailContext.Provider value={{ key: shown?.key ?? null, open, close }}>
      {children}
      <aside id="detail" className="detail" hidden={!shown}>
        {shown && (
          <>
            <button type="button" className="ghost close" aria-label="Close" onClick={close}>×</button>
            {shown.content}
          </>
        )}
      </aside>
    </DetailContext.Provider>
  );
}

export const useDetail = () => useContext(DetailContext);
