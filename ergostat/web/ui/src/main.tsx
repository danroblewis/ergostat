import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
// the page's styles: the components use their class names
import "./styles/style.css";
import "./styles/panels.css";
import "./styles/plots.css";
import "./styles/panel-editor.css";
import "./styles/dashboard.css";
import "./app.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter basename="/">
      <App />
    </BrowserRouter>
  </StrictMode>,
);
