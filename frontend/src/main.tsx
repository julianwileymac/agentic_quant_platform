import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "./styles/tokens.css";

import { App } from "./App";
import { AuthProvider } from "./lib/auth";

const rootEl = document.getElementById("root");
if (!rootEl) {
  throw new Error("AQP frontend: missing #root element in index.html");
}

createRoot(rootEl).render(
  <StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </StrictMode>,
);
