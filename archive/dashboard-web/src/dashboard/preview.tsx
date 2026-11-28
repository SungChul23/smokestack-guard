// 개발용 미리보기: 로그인 없이 관제 화면 틀만 띄운다. 운영 빌드(index.html)에는 포함되지 않는다.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "../theme/tokens.css";
import { ThemeProvider } from "../theme/theme";
import DashboardApp from "./DashboardApp";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <DashboardApp email="preview@example.com" onLogout={() => alert("로그아웃(미리보기)")} />
    </ThemeProvider>
  </StrictMode>,
);
