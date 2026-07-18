import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "./styles.css";
import "./results-showcase.css";
import "./faq-section.css";
import "./chart-workspace.css";
import "./site-shell.css";
import "./guide.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
