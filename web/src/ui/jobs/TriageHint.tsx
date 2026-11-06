import { CircleHelp } from "lucide-react";

import { Button } from "../components/button";
import { Popover, PopoverContent, PopoverTrigger } from "../components/popover";

const HINT = "Тріаж — швидка попередня оцінка вакансії: бал 0–100 і вердикт. Він нічого не ховає. Оцінює сервер за ключовими словами або агент за тими самими правилами. Повний аналіз глибший: порівнює вимоги з твоїми підтвердженими фактами й показує прогалини.";

/** Кнопка «?» з поясненням, що таке тріаж. Popover, а не Tooltip: Tooltip не відкривається дотиком на телефоні. */
export function TriageHint() {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Що таке тріаж?" className="text-muted-foreground">
          <CircleHelp aria-hidden="true" />
        </Button>
      </PopoverTrigger>
      <PopoverContent aria-label="Що таке тріаж?" className="text-sm">
        {HINT}
      </PopoverContent>
    </Popover>
  );
}
