// The page's address helpers (ergostat/web/ui/src/lib/systemRoutes.ts) over route tables Python wrote: node runs the
// .ts as it is (type stripping, node 22.6+; on by default from 23.6). Reads {tables: {MODEL: table}, ask: [...]} from
// the file named first and writes [answer, ...] as JSON: tests/test_system_routes.py compares them with Python's.
import { readFileSync } from "node:fs";

const { href, resolve } = await import(new URL("../../ergostat/web/ui/src/lib/systemRoutes.ts", import.meta.url));
const { tables, ask } = JSON.parse(readFileSync(process.argv[2], "utf8"));
const out = ask.map((q) =>
  q.path !== undefined ? resolve(tables[q.model], q.path) : href(tables[q.model], q.thing, q.scope));
process.stdout.write(JSON.stringify(out));
