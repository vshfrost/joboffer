// Межі гексагональної архітектури клієнта + базовий lint.
import js from "@eslint/js";
import boundaries from "eslint-plugin-boundaries";
import globals from "globals";
import tseslint from "typescript-eslint";

const LAYERS = ["domain", "application", "ports", "infrastructure", "ui", "bootstrap"];

// Хто від кого може залежати (імпорти між шарами web/src).
const ALLOWED = {
  domain: ["domain"],
  application: ["domain", "application", "ports"],
  ports: ["domain", "ports"],
  infrastructure: ["domain", "application", "ports", "infrastructure"],
  ui: ["domain", "application", "ports", "ui"], // ui не бачить конкретну infrastructure
  bootstrap: LAYERS, // єдине місце wiring-у
};

const REACT_AND_QUERY = {
  patterns: [
    { group: ["react", "react/*", "react-dom", "react-dom/*"], message: "React — лише в ui/bootstrap." },
    { group: ["@tanstack/*"], message: "TanStack — лише в ui/bootstrap." },
  ],
};
const BROWSER_IO = ["fetch", "WebSocket", "XMLHttpRequest", "EventSource", "localStorage", "sessionStorage", "indexedDB"];
const DOM = ["window", "document", "navigator", "location", "history"];
const restrictGlobals = (names, where) =>
  names.map((name) => ({ name, message: `${name} недоступний у ${where}: IO живе в infrastructure за портом.` }));

export default tseslint.config(
  { ignores: ["dist/", "node_modules/"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: { globals: globals.browser },
    plugins: { boundaries },
    settings: {
      "import/resolver": { typescript: { alwaysTryTypes: true, project: "./tsconfig.json" } },
      "boundaries/elements": LAYERS.map((type) => ({ type, pattern: `src/${type}` })),
    },
    rules: {
      "boundaries/no-unknown-files": "error",
      "boundaries/dependencies": [
        "error",
        {
          default: "disallow",
          policies: [
            ...Object.entries(ALLOWED).map(([from, to]) => ({
              from: { element: { type: from } },
              allow: { to: { element: { types: { anyOf: to } } } },
            })),
            // Зовнішні пакети дозволені; які саме — обмежує no-restricted-imports нижче.
            { allow: { to: { module: { origin: "external" } } } },
          ],
        },
      ],
    },
  },
  // Core клієнта: без React/TanStack і без браузерного IO чи DOM.
  {
    files: ["src/{domain,application,ports}/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": ["error", REACT_AND_QUERY],
      "no-restricted-globals": ["error", ...restrictGlobals([...BROWSER_IO, ...DOM], "core")],
    },
  },
  // Infrastructure може робити IO, але не рендерить UI.
  {
    files: ["src/infrastructure/**/*.{ts,tsx}"],
    rules: { "no-restricted-imports": ["error", REACT_AND_QUERY] },
  },
  // UI отримує дані через порти: жодного прямого fetch/WebSocket/сховища.
  {
    files: ["src/ui/**/*.{ts,tsx}"],
    rules: { "no-restricted-globals": ["error", ...restrictGlobals(BROWSER_IO, "ui")] },
  },
);
