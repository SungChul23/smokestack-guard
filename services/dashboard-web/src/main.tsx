import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { AuthProvider } from "react-oidc-context";
import App from "./App";
import { oidcConfig } from "./auth";
import "./theme/tokens.css";
import { ThemeProvider } from "./theme/theme";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <AuthProvider {...oidcConfig}>
        <App />
      </AuthProvider>
    </ThemeProvider>
  </StrictMode>,
);
