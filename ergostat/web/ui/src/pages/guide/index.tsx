import { Fragment, useCallback, useEffect, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { AppLink, Async, Page } from "../../components";
import { useApi } from "../../hooks/useApi";
import { Plot, type GuidePlot } from "./Plot";

/* The Guide (guide.js): a sequence of frames, one line of text each; the frame in the address (frame=), stepped by
   the dots, the arrows (← →, PageUp/PageDown) or a scroll. Where a frame shows behaviour, a small graph of it,
   integrated here. Each frame's tiny model is drawn, in the old page, by the diagram's own renderers; here each view
   is a link to the diagram for now, until the diagram's static drawing can be shared (pages/diagram). */

interface Frame {
  id: string;
  part: string;
  text: string;
  views?: { view: string; graph: any; opened?: any }[];
  plot?: GuidePlot;
}

const VIEW_WORDS: Record<string, string> = { dynamics: "system dynamics", blocks: "control", process: "process" };

export default function GuidePage() {
  const guide = useApi<{ parts: Record<string, string>; frames: Frame[] }>("guide", {}, { window: false });
  return (
    <Page title="Guide">
      <Async state={guide}>{(d) => <Deck parts={d.parts} frames={d.frames} />}</Async>
    </Page>
  );
}

function Deck({ parts, frames }: { parts: Record<string, string>; frames: Frame[] }) {
  const [q, setQ] = useSearchParams();
  const clamp = (k: number) => Math.max(0, Math.min(frames.length - 1, k));
  const i = clamp(parseInt(q.get("frame") || "0", 10) || 0);
  const f = frames[i];
  const deck = useRef<HTMLDivElement>(null);
  const show = useCallback(
    (k: number) => setQ((p) => { const n = new URLSearchParams(p); n.set("frame", String(clamp(k))); return n; }, { replace: true }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [setQ, frames.length],
  );

  useEffect(() => {
    const key = (ev: KeyboardEvent) => {
      if ((ev.target as HTMLElement).closest?.("input, select, textarea")) return;
      if (ev.key === "ArrowRight" || ev.key === "PageDown") { ev.preventDefault(); show(i + 1); }
      if (ev.key === "ArrowLeft" || ev.key === "PageUp") { ev.preventDefault(); show(i - 1); }
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [i, show]);

  useEffect(() => { // scrolling steps too, one frame a gesture
    const el = deck.current;
    if (!el) return;
    let wheelAt = 0;
    const wheel = (ev: WheelEvent) => {
      if (Math.abs(ev.deltaY) < 12 || ev.ctrlKey || ev.metaKey) return;
      ev.preventDefault();
      if (Date.now() - wheelAt < 650) return;
      wheelAt = Date.now();
      show(i + (ev.deltaY > 0 ? 1 : -1));
    };
    el.addEventListener("wheel", wheel, { passive: false });
    return () => el.removeEventListener("wheel", wheel);
  }, [i, show]);

  const two = (f.views?.length ?? 0) > 1 || f.id === "yours";
  const views = f.id === "yours" ? [{ view: "dynamics" }, { view: "blocks" }] : f.views || [];
  return (
    <div className="g-deck" tabIndex={0} ref={deck} data-frame={f.id} data-drawn={f.id}>
      <div className="g-steps">
        {frames.map((x, k) => (
          <Fragment key={x.id}>
            {(k === 0 || frames[k - 1].part !== x.part) && (
              <a
                className={"g-part" + (x.part === f.part ? " on" : "")}
                data-part={x.part}
                href={`/ui/guide?frame=${k}`}
                onClick={(ev) => { ev.preventDefault(); show(k); }}
              >
                {parts[x.part]}
              </a>
            )}
            <button
              type="button"
              className={"g-dot" + (k === i ? " on" : "")}
              data-frame={k}
              title={x.text}
              aria-label={`Step ${k + 1} of ${frames.length}`}
              aria-current={k === i ? "step" : undefined}
              onClick={() => show(k)}
            />
          </Fragment>
        ))}
      </div>
      <p className="g-text">{f.text}</p>
      <div className="g-stage">
        <div className={"g-views" + (two ? " two" : "")}>
          {views.map((v, k) => (
            <div key={k} className="g-view">
              <p className="muted small">
                <AppLink to={`/diagram?view=${v.view}`}>{`Open the ${VIEW_WORDS[v.view] || v.view} diagram`}</AppLink>
              </p>
            </div>
          ))}
        </div>
        {f.plot && <Plot plot={f.plot} />}
      </div>
      <div className="g-nav">
        <button type="button" onClick={() => show(i - 1)} disabled={i === 0} title="The previous frame (←)" aria-label="Previous">←</button>
        <span className="muted small g-count">{`${i + 1} / ${frames.length}`}</span>
        <button type="button" onClick={() => show(i + 1)} disabled={i === frames.length - 1} title="The next frame (→)" aria-label="Next">→</button>
      </div>
    </div>
  );
}
