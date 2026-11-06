import { useState } from "react";

const KEY = "joboffer.job-prep.expanded";

/** Згорнуту «Підготовку» запам'ятовує вкладка: після переходу на /prep/{n} і назад блок такий самий. Недоступне сховище — блок початково розгорнутий. */
function read(): boolean {
  try {
    return window.sessionStorage.getItem(KEY) !== "0";
  } catch {
    return true;
  }
}

function write(expanded: boolean): void {
  try {
    window.sessionStorage.setItem(KEY, expanded ? "1" : "0");
  } catch {
    // Сховище недоступне (приватний режим, заборона): стан живе лише поки блок на екрані.
  }
}

export function usePrepExpanded(): [boolean, () => void] {
  const [expanded, setExpanded] = useState(read);
  function toggle() {
    const next = !expanded;
    setExpanded(next);
    write(next);
  }
  return [expanded, toggle];
}
