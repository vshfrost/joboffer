import { render, screen } from "@testing-library/react";
import { Inbox } from "lucide-react";
import { MemoryRouter } from "react-router";
import { describe, expect, test } from "vitest";

import { NavItem } from "./Sidebar";

function renderItem(count?: number) {
  return render(
    <MemoryRouter>
      <NavItem to="/replies" label="Відповіді" icon={Inbox} {...(count === undefined ? {} : { count })} />
    </MemoryRouter>,
  );
}

describe("NavItem", () => {
  test("з новими елементами показує лічильник і каже про нього в назві", () => {
    renderItem(2);
    const link = screen.getByRole("link", { name: "Відповіді: 2 нові" });
    expect(link.textContent).toContain("2");
  });

  test("лічильник має lime-токени Pine", () => {
    renderItem(2);
    const counter = screen.getByText("2");
    expect(counter.className).toContain("bg-counter");
    expect(counter.className).toContain("text-counter-foreground");
  });

  test.each([undefined, 0])("без нових (%s) лічильника нема", (count) => {
    renderItem(count);
    expect(screen.getByRole("link", { name: "Відповіді" })).toBeDefined();
    expect(screen.queryByText("0")).toBeNull();
  });

  test("понад 99 показується як 99+", () => {
    renderItem(240);
    expect(screen.getByText("99+")).toBeDefined();
  });

  test("іконка прихована від скрінрідерів", () => {
    const { container } = renderItem(1);
    expect(container.querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");
  });
});
