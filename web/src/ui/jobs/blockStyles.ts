/** Спільні класи блоків «Підготовка» і «Пакет до інтерв'ю» в деталях вакансії. */

export const WRAP = "[overflow-wrap:anywhere]";

/** Посилання блоку: переноситься, на touch-пристроях від 44 px. */
export const LINK = `inline-flex max-w-full items-center text-left text-primary ${WRAP} hover:underline pointer-coarse:min-h-11`;

/** Заголовок розкривного: без системного трикутника, маркер +/− справа, від 44 px на touch-пристроях. */
export const SUMMARY = [
  "flex cursor-pointer list-none items-center gap-3 [&::-webkit-details-marker]:hidden pointer-coarse:min-h-11",
  "after:ml-auto after:shrink-0 after:text-lg after:leading-5 after:text-muted-foreground after:content-['+'] group-open:after:content-['−']",
].join(" ");

export const ALERT = "flex flex-col items-start gap-3 rounded-xl border border-border bg-status-danger p-4 text-status-danger-foreground";
