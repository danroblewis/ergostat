import { useState } from "react";
import { apiPost } from "../lib/api";
import { dur } from "../lib/format";
import { useStatus } from "../state/status";
import { AppLink, Button } from "./ui";

/* What waits on a person (the inbox, SPEC §12o: GET /api/inbox, the same list `ergostat inbox` prints), each as a card
   answered where it is drawn, with every verb the CLI has: Approve, Deny (a reason, required for a modelling request),
   Done with a number (a person's request), through POST /api/inbox/ID/VERB. Nothing on a card is only to read: a
   drafted projection's card also opens it in the workbench. */

/** One entry as GET /api/inbox answers it (inbox/entries.py, with its class's record from inbox/stats.py). */
export type Entry = {
  id: string; kind: string; summary: string; age: number; link?: string; verbs: string[]; why?: string; warn?: string;
  run?: string; record?: string; suggest?: string; flow?: string; unit?: string; block?: string; system?: string | null;
  workbench?: { projection: string; link: string }[];
};

/** What each kind of entry is called on its card. */
export const KIND_WORD: Record<string, string> = {
  action: "action", person: "a person's request", advise: "advised command", steptest: "step test", change: "model change",
  request: "modelling request", breaker: "breaker tripped", command: "command",
};

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** One thing the owner decides: what it is (linked to its page), what kind and how long it waited, why in a line or
 *  two, and its answers. */
export function DecisionCard({ e }: { e: Entry }) {
  const { refresh } = useStatus();
  const [said, setSaid] = useState<string | null>(null);
  const [denying, setDenying] = useState(false);
  const [note, setNote] = useState("");
  const [n, setN] = useState("");
  const title = e.summary.replace(/^model change: /, "");
  const needsWhy = e.kind === "request";
  const give = (verb: string, params: Record<string, string> = {}) => {
    apiPost(`inbox/${encodeURIComponent(e.id)}/${verb}`, params)
      .then((r: any) => { setSaid(`${verb === "approve" ? (e.kind === "breaker" ? "Reset" : "Approved") : verb === "deny" ? "Denied" : "Done"}${r?.said ? `: ${r.said}` : ""}`); refresh(); })
      .catch((x) => setSaid(`Not answered: ${x.message}`));
  };
  const why = [e.warn && e.warn !== e.why ? e.warn : "", e.why || ""].filter(Boolean);
  const numberLabel = `${cap(e.unit || "amount")} done${e.flow ? `, along ${e.flow}` : ""} (number)`;
  return (
    <div className="wait-card" data-row={e.id} data-kind={e.kind}>
      <div className="wait-title">
        {e.link ? <AppLink className="plain" to={e.link}><b>{title}</b></AppLink> : <b>{title}</b>}
      </div>
      <div className="wait-meta">{KIND_WORD[e.kind] || e.kind} · waiting {dur(e.age)}{e.record ? ` · ${e.record}` : ""}</div>
      {why.map((w, i) => <div key={i} className="wait-why">{w}</div>)}
      {e.run && <div className="wait-why">It runs: <code>{e.run}</code></div>}
      {e.suggest && <div className="wait-why muted">{e.suggest}</div>}
      {said ? <div className="wait-said" data-answered>{said}</div> : (
        <div className="wait-actions">
          {e.verbs.includes("done") && (
            <label className="wait-box">
              <span>{numberLabel}</span>
              <input type="number" value={n} onChange={(x) => setN(x.target.value)} data-done-n />
            </label>
          )}
          {e.verbs.includes("done") && (
            <Button className="primary" data-answer="done" disabled={n === "" || !Number.isFinite(+n)}
              onClick={() => give("done", { n })}>Done</Button>
          )}
          {e.verbs.includes("approve") && !denying && (
            <Button className="primary" data-answer="approve" onClick={() => give("approve")}>
              {e.kind === "breaker" ? "Reset" : "Approve"}
            </Button>
          )}
          {e.verbs.includes("deny") && !denying && (
            <Button data-answer="deny" onClick={() => setDenying(true)}>Deny</Button>
          )}
          {denying && (
            <>
              <label className="wait-box">
                <span>Reason for denying ({needsWhy ? "required" : "optional"})</span>
                <input type="text" value={note} onChange={(x) => setNote(x.target.value)} autoFocus data-deny-note />
              </label>
              <Button data-answer="deny" data-confirm disabled={needsWhy && !note.trim()}
                onClick={() => give("deny", note.trim() ? { note: note.trim() } : {})}>Deny</Button>
              <Button variant="ghost" onClick={() => { setDenying(false); setNote(""); }}>Cancel</Button>
            </>
          )}
          {(e.workbench || []).map((w) => (
            <AppLink key={w.projection} to={w.link} data-workbench={w.projection}>Open {w.projection} in the workbench</AppLink>
          ))}
        </div>
      )}
    </div>
  );
}

/** The entries, each a card; with none, that nothing waits. */
export function Decisions({ entries }: { entries: Entry[] }) {
  if (!entries.length) return <p id="may-do" className="may-do">Nothing waits for you.</p>;
  return (
    <div className="decisions" role="group" aria-describedby="may-do">
      <p id="may-do" className="may-do">You can look at everything. Approving or denying these is the only thing that changes the system.</p>
      {entries.map((e) => <DecisionCard key={e.id} e={e} />)}
    </div>
  );
}
