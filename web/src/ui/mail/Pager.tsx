import { rangeText, type MailPage } from "../../domain/mail";
import { Button } from "../components/button";

/** Діапазон сторінки й кнопки «Новіші» / «Старіші». */
export function Pager({ page, onPage }: { page: MailPage; onPage(number: number): void }) {
  return (
    <nav aria-label="Сторінки" className="flex items-center justify-between gap-3">
      <span className="text-caption text-muted-foreground">{rangeText(page)}</span>
      <span className="flex gap-2">
        <Button type="button" variant="secondary" size="sm" aria-label="Новіші листи" disabled={!page.hasNewer} onClick={() => onPage(page.number - 1)}>
          ←
        </Button>
        <Button type="button" variant="secondary" size="sm" aria-label="Старіші листи" disabled={!page.hasOlder} onClick={() => onPage(page.number + 1)}>
          →
        </Button>
      </span>
    </nav>
  );
}
