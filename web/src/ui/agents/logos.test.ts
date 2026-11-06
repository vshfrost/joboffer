/** Логотипи агентів лежать у web/public/agents (без CDN), з приміткою про ліцензію. */
import { describe, expect, test } from "vitest";

const files = import.meta.glob<string>("/public/agents/*", { query: "?raw", import: "default", eager: true });

describe("web/public/agents", () => {
  test.each(["claude.svg", "claudecode.svg", "openai.svg", "codex.svg"])("%s — SVG", (name) => {
    expect(files[`/public/agents/${name}`]).toMatch(/^<svg\b/);
  });

  test("поруч є примітка: @lobehub/icons-static-svg 1.101.0, MIT", () => {
    const note = files["/public/agents/README.md"];

    expect(note).toContain("@lobehub/icons-static-svg");
    expect(note).toContain("1.101.0");
    expect(note).toContain("MIT");
  });
});
