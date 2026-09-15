import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "render-dds/styles";

import App from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
