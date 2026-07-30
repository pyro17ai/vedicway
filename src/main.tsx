import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/cormorant-garamond/400.css";
import "@fontsource/cormorant-garamond/500.css";
import "@fontsource/cormorant-garamond/600.css";
import "@fontsource/inter/300.css";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";

import App from "./App";
import { CookieConsentBanner } from "./components/CookieConsentBanner";
import { readSeoBootstrap } from "./lib/seo-bootstrap";
import "./styles.css";
import "./results-showcase.css";
import "./faq-section.css";
import "./chart-workspace.css";
import "./site-shell.css";
import "./guide.css";
import "./legal.css";
import "./recovery.css";
import "./rectification.css";
import "./light-theme.css";

const seoBootstrap = readSeoBootstrap();

createRoot(document.getElementById("root")!).render(
  <StrictMode><App seoBootstrap={seoBootstrap} /><CookieConsentBanner /></StrictMode>,
);
