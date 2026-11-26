import type { PanelKind } from "../types";
import { AGENTS } from "./agents";
import { ATTENTION } from "./attention";
import { CORE } from "./core";
import { ITEMS } from "./items";
import { RECORD } from "./record";

export { asQueryPanel, paramsOf } from "./core";

/** Every kind of panel, by its name in the model's `dashboards:` (spec/dashboards.py KINDS): one file a group. */
export const KINDS: Record<string, PanelKind> = { ...CORE, ...AGENTS, ...ITEMS, ...RECORD, ...ATTENTION };
