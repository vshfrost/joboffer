/** Bootstrap: єдине місце wiring-у клієнта — створює залежності й монтує UI. */
import "@fontsource-variable/inter";
import "../ui/theme.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter } from "react-router";
import { RouterProvider } from "react-router/dom";

import { Client } from "./Client";

const root = document.getElementById("root");
if (root === null) {
  throw new Error("#root не знайдено в index.html");
}

// Data router: потрібен `useBlocker` (попередження про незбережене); увесь застосунок — один «*»-маршрут,
// а власні маршрути лишаються в `<Routes>` усередині `App`.
const router = createBrowserRouter([{ path: "*", element: <Client fetchFn={(input, init) => fetch(input, init)} /> }]);

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={new QueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
