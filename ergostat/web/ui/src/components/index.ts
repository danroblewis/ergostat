/* The core components: every page is composed of these. A page's own parts stay in its folder under pages/. */
export { Menu, useMenuClose } from "./Menu";
export { Table, DataTable, Fields, type Column } from "./Table";
export { DetailProvider, useDetail } from "./Detail";
export { Markdown, Code } from "./Markdown";
export { Chart, type Series } from "./Chart";
export {
  Page, Section, AppLink, Muted, Note, Empty, Loading, ErrorNote, Async, StatusWord, Rung, Button, Select, Check,
  Filters, Fold, Tabs, Rich,
} from "./ui";
