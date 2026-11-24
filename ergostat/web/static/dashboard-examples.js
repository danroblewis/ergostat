/* the default dashboard's worked examples: one panel of each chart family the default does not already use, on the
   lead kind's own data, so that opening one in the editor shows how that family is set up */
const dashNumeric = (k) => k.fields.filter((f) => !DASH_NOT_CHARTED.test(f.name) && f.unit && f.unit !== "count");
/* the money field first, then the numbers the default charts, then the rest */
function dashExampleFields(k) {
  const all = dashNumeric(k), wanted = DASH_WANTED.map((w) => all.find((f) => w.match.test(f.name)));
  return [...new Set([...all.filter(dashIsCost), ...wanted.filter(Boolean), ...all])];
}
const dashFieldQuery = (k, f, more) => ({ id: "a", source: "items", kind: k.name, field: f.name, label: f.name, ...more });
const dashFieldUnit = (f) => (dashIsCost(f) ? dashCostUnit(f) : f.unit || "");

function dashFieldExamples(k) {
  const list = dashExampleFields(k), y = list[0], x = list.find((f) => f !== y && !dashIsCost(f)) || list[1];
  if (!y) return [];
  const unit = dashFieldUnit(y), byState = { type: "category", by: "state" };
  const out = [
    { title: `${k.name}: ${y.name} by state`, form: "bar", options: { orientation: "horizontal" }, note: "Total per state",
      queries: [dashFieldQuery(k, y, { agg: "sum", x: byState })], display: { unit } },
    { title: `${k.name}: distribution of ${y.name}`, form: "histogram", note: "How many items fall in each range",
      queries: [dashFieldQuery(k, y, { agg: "count", x: { type: "bins", field: y.name, bins: 20 } })], display: { unit: "items" } },
    { title: `${k.name}: spread of ${y.name} by state`, form: "box", note: "Median, quartiles and outliers",
      queries: [dashFieldQuery(k, y, { agg: "none", x: byState })], display: { unit } },
  ];
  /* a heatmap takes points (SPEC §4e), so it counts the same pairs as the scatter, where there are two fields */
  const pairs = x && [dashFieldQuery(k, y, { agg: "none", x: { type: "field", field: x.name } })];
  if (x) out.push({ title: `${k.name}: ${y.name} against ${x.name}`, form: "scatter", note: "One dot per item",
                    queries: pairs, display: { unit } },
                  { title: `${k.name}: ${y.name} against ${x.name}, heatmap`, form: "heatmap", note: "Darker means more items in that cell",
                    queries: pairs, display: { unit } });
  return out;
}
function dashFlowExamples(k, goals, source) {
  const stay = dashStayStates(k)[0];
  const out = [{ title: `${k.name}: items per state now`, form: "table", note: "Current count of each open state",
                 queries: [{ ...dashCount(k, "a", k.open, "items"), group_by: "state" }], display: { unit: "items", decimals: 0 } },
               { title: `${k.name}: the process map`, form: "graph", note: "Each step its items took, and the lines between them",
                 queries: [{ id: "a", source: "graph", diagram: "process", kind: k.name }], display: {} },
               ...(stay ? [{ title: `${k.name}: time in ${stay}, open to close`, form: "candlestick", options: { up_is: "bad" },     // a longer wait is the bad direction
                             note: "Each bar: first, highest, lowest and last wait in that period",
                             queries: [dashStay(k, "a", stay, "ohlc")], display: { unit: "s" } }] : [])];
  if (k.waiting.length && k.working.length)
    out.push({ title: `${k.name}: waiting against working`, form: "phase", note: "The path the two take together over time",
               queries: [{ ...dashCount(k, "a", k.working, "working"), x: { type: "query", query: "b" } },
                         { ...dashCount(k, "b", k.waiting, "waiting"), hidden: true }],
               display: { unit: "items", decimals: 0, x: { label: "waiting" } } });
  /* arrivals against completions is not an example of a response: nothing excites the arrivals, and their record seldom
     supports one (dev/records/frequency-refuses-noise.md). The examples ask the model data source for a goal's declared
     process, when there is one (dev/records/model-data-source.md) */
  if (!goals[0] || !source) return out;
  const model = { id: "a", source: source.name, text: `goal ${goals[0]}` };
  out.push({ title: `${goals[0]}: the declared process, Bode`, form: "bode", note: "Gain and phase by frequency, from the model", queries: [model], display: {} },
           { title: `${goals[0]}: the declared process, Nyquist`, form: "nyquist", note: "The same response on the complex plane", queries: [model], display: {} },
           { title: `${goals[0]}: poles and zeros`, form: "pole-zero", note: "From the goal's declared process", queries: [model], display: {} });
  return out;
}
/* rows of three, the last row filled */
function dashExamples(k, fields, used) {
  const goals = fields?.sources?.frequency?.goals || [];
  const source = (fields?.datasources || []).find((s) => s.type === "model");
  const made = [...dashFieldExamples(k), ...dashFlowExamples(k, goals, source)].filter((p) => !used.has(p.form));
  const left = made.length % 3;
  return made.map((p, i) => ({ ...p, size: left && i >= made.length - left ? (left === 1 ? "full" : "m") : "s" }));
}
