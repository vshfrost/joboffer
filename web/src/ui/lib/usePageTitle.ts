import { useLayoutEffect } from "react";

const SUFFIX = "joboffer";

/** Заголовок вкладки: «Розділ · joboffer». */
export function usePageTitle(title: string): void {
  useLayoutEffect(() => {
    document.title = `${title} · ${SUFFIX}`;
  }, [title]);
}
