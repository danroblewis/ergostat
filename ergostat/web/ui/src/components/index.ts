/* The components every page is composed of. A part one page alone draws stays in its folder under pages/; anything
   two pages could use lives here. The diagram is imported from "./diagram" (it brings ELK). */
export { Menu, useMenuClose } from "./Menu";
export { Table, DataTable, Fields, type Column } from "./Table";
export { DetailProvider, useDetail } from "./Detail";
export { Markdown, Code } from "./Markdown";
export {
  Page, Section, AppLink, Muted, Note, Empty, Loading, ErrorNote, Async, StatusWord, Rung, Button, Select, Check,
  Filters, Fold, Tabs, Rich, Dl,
} from "./ui";
export { AgentLink, ItemLink, ProjectionLink } from "./links";
export { EventsTable, EventDetail, useShowEvent, changeOf, type RecordEvent } from "./events";
export { ProjectionBar, ProjectionGraph, ItemsTable, FieldValue, StatesChoice, isShort, hiddenStates } from "./items";
export { GoalCells, type GoalColumn } from "./goals";
export { Chart, Plot, PanelView, PanelFrame, QueryPanel, usePanelResults, Spark, FlowChart, ProjectionStates, valueText, type Series, type PlotSeries } from "./charts";
export { GoalDetail } from "./GoalDetail";
export { GoalsTable, ALL_COLUMNS, PANEL_COLUMNS } from "./GoalsTable";
export { Segmented, SearchBox, Pager, PAGE_SIZES, FinishedToggle, FinishedNote, Meta, SystemGroup } from "./controls";
