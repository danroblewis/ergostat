/* reports upstream (SPEC §12m): a report about ergostat itself, drafted and scrubbed for the owner. Its page shows the
   text to paste with a Copy button, a link that opens a new issue on ergostat's GitHub project with its title filled
   in (only a link: the owner opens it, nothing is sent), the owner's marks (reviewed, submitted, dismissed), and the
   scrub log: what was removed from the text, and why, kept here and never part of it */
const REPORT_KIND = "ergostat.report";

async function copyText(text, said) {
  try { await navigator.clipboard.writeText(text); said.textContent = " Copied."; }
  catch (e) {                                          // no clipboard (an insecure context): select it for the owner
    const ta = h("textarea", { class: "offscreen", "aria-hidden": "true" });
    ta.value = text; document.body.append(ta); ta.select();
    try { document.execCommand("copy"); said.textContent = " Copied."; } catch (err) { said.textContent = " Select the text and copy it."; }
    ta.remove();
  }
}

function reportMarks(d, done) {
  if (SNAP || !["drafted", "reviewed"].includes(d.state)) return null;
  const note = h("input", { type: "text", placeholder: "the issue's link, or why (optional)", "aria-label": "Note" });
  const said = h("span", { class: "note", "aria-live": "polite" });
  const mark = (to, label, cls = "") => h("button", { class: cls, "data-mark": to, onclick: async () => {
    for (const b of row.querySelectorAll("button")) b.disabled = true;
    try { const got = await apiPost(`report/${encodeURIComponent(d.id)}/${to}`, note.value.trim() ? { note: note.value.trim() } : {}); said.textContent = ` ${got.state}`; done?.(); }
    catch (e) { said.textContent = ` ${e.message}`; for (const b of row.querySelectorAll("button")) b.disabled = false; }
  } }, label);
  const row = h("div", { class: "row action-act report-marks" },
    d.state === "drafted" ? mark("reviewed", "Reviewed", "ghost") : null, mark("submitted", "Submitted"), mark("dismissed", "Dismiss", "ghost"), note, said);
  return row;
}

function scrubLog(removed, counts) {
  const n = Object.entries(counts || {}).map(([k, v]) => `${v} ${k}`).join(", ");
  return h("div", { class: "scrub-log" },
    h("p", { class: "note" }, removed.length ? `Removed before you saw it (${n}); kept here, never part of the text:` : "Nothing was removed."),
    removed.length ? table(["stand-in", "rule", "what", ["times", "num"], "original", "why"], removed.map((x) => h("tr", { key: `${x.rule}|${x.stand_in}` },
      h("td", {}, h("code", {}, x.stand_in)), h("td", {}, x.rule), h("td", { class: "muted" }, x.what || ""), h("td", { class: "num" }, String(x.count)),
      h("td", { class: "mono small" }, x.original), h("td", { class: "muted" }, x.why)))) : null);
}

function reportView(d, refresh) {
  const f = d.fields;
  const box = h("div", { class: "report-text" }, h("p", { class: "muted" }, "Reading the report…"));
  const head = h("p", {}, h("span", { class: d.state === "drafted" ? "s-open" : d.state === "dismissed" ? "muted" : "status" }, d.state === "drafted" ? "waiting for you to read" : d.state),
    h("span", { class: "muted" }, ` drafted by ${f.by || f.origin || "?"}`, (f.occurrences || 1) > 1 ? `, seen ${f.occurrences} times` : "", f.note ? ` (${f.note})` : ""));
  (async () => {
    let r = null;
    try { r = await api(`report/${encodeURIComponent(d.id)}`); } catch (e) { r = null; }
    if (!r) { patch(box, h("p", { class: "muted" }, SNAP ? "The report's text is not in a snapshot." : "The report's file could not be read.")); return; }
    const said = h("span", { class: "note", "aria-live": "polite" });
    patch(box,
      h("p", { class: "note" }, "Nothing is sent: read it, then, if you choose, open a new issue and paste the body. ", h("span", { class: "muted" }, r.path)),
      h("div", { class: "row report-acts" },
        h("button", { class: "report-copy", onclick: () => copyText(r.body ?? r.text ?? "", said) }, "Copy the body"),
        h("a", { class: "button report-issue", href: r.issue_url, target: "_blank", rel: "noopener noreferrer" }, "Open a new issue on GitHub"), said),
      h("p", {}, h("b", {}, "Title "), h("span", { class: "report-title" }, r.title || ""), h("span", { class: "muted" }, (r.labels || []).length ? ` · labels: ${r.labels.join(", ")}` : "")),
      h("pre", { class: "mono small report-body" }, r.body ?? r.text ?? "(its file is gone)"),
      h("h3", {}, "Scrubbed"), scrubLog(r.removed || [], r.counts || {}));
  })();
  return h("div", { class: "claim report" }, head, reportMarks(d, refresh), box);
}
