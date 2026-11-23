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
  if (x) out.push({ title: `${k.name}: ${y.name} against ${x.name}`, form: "scatter", note: "One dot per item",
                    queries: [dashFieldQuery(k, y, { agg: "none", x: { type: "field", field: x.name } })], display: { unit } });
  out.push({ title: `${k.name}: ${y.name} per hour, heatmap`, form: "heatmap", note: "Darker means more time periods at that level",
             queries: [dashFieldQuery(k, y, { agg: "sum", transform: "rate", rate_per: "hour" })], display: { unit: `${unit}/h` } });
  return out;
}
function dashFlowExamples(k, goals) {
  const stay = dashStayStates(k)[0];
  const out = [{ title: `${k.name}: items per state now`, form: "table", note: "Current count of each open state",
                 queries: [{ ...dashCount(k, "a", k.open, "items"), group_by: "state" }], display: { unit: "items", decimals: 0 } },
               ...(stay ? [{ title: `${k.name}: time in ${stay}, open to close`, form: "candlestick",
                             note: "Each bar: first, highest, lowest and last wait in that period",
                             queries: [dashStay(k, "a", stay, "ohlc")], display: { unit: "s" } }] : [])];
  if (k.waiting.length && k.working.length)
    out.push({ title: `${k.name}: waiting against working`, form: "phase", note: "The path the two take together over time",
               queries: [{ ...dashCount(k, "a", k.working, "working"), x: { type: "query", query: "b" } },
                         { ...dashCount(k, "b", k.waiting, "waiting"), hidden: true }], display: { unit: "items", decimals: 0 } });
  if (!k.done.length) return out;
  const io = { id: "a", source: "frequency", input: { ...dashArrivals(k), id: "in" }, output: { ...dashCompletions(k), id: "out" } };
  out.push({ title: `${k.name}: arrivals to completions, Bode`, form: "bode", note: "Gain and phase by frequency", queries: [io], display: {} },
           { title: `${k.name}: arrivals to completions, Nyquist`, form: "nyquist", note: "The same response on the complex plane", queries: [io], display: {} });
  out.push({ title: goals[0] ? `${goals[0]}: poles and zeros` : `${k.name}: poles and zeros`, form: "pole-zero",
             note: goals[0] ? "From the goal's declared process" : "Needs a goal that declares a process",
             queries: [goals[0] ? { id: "a", source: "frequency", model: { goal: goals[0] } } : io], display: {} });
  return out;
}
/* rows of three, the last row filled */
function dashExamples(k, fields, used) {
  const goals = fields?.sources?.frequency?.goals || [];
  const made = [...dashFieldExamples(k), ...dashFlowExamples(k, goals)].filter((p) => !used.has(p.form));
  const left = made.length % 3;
  return made.map((p, i) => ({ ...p, size: left && i >= made.length - left ? (left === 1 ? "full" : "m") : "s" }));
}
