import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
// the old page's styles, shared while both pages are served: the components keep its class names
import "../../static/style.css";
import "../../static/panels.css";
import "../../static/plots.css";
import "../../static/panel-editor.css";
import "../../static/dashboard.css";
import "./app.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter basename="/ui">
      <App />
    </BrowserRouter>
  </StrictMode>,
);
