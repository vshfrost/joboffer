import { Menu, X } from "lucide-react";
import { Dialog } from "radix-ui";
import { useState } from "react";

import { Button } from "../components/button";
import { Brand, SidebarNav } from "./Sidebar";

/** Меню для вузьких екранів: ліва панель, закривається вибором розділу, Escape чи кнопкою. */
export function MobileNav() {
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <Button variant="ghost" size="icon" aria-label="Відкрити навігацію" className="-ml-2 md:hidden">
          <Menu aria-hidden="true" />
        </Button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 animate-overlay-in bg-foreground/40 md:hidden" />
        <Dialog.Content
          aria-describedby={undefined}
          className="fixed inset-y-0 left-0 z-50 flex w-72 max-w-[85vw] animate-sheet-in flex-col gap-6 border-r border-sidebar-border bg-sidebar p-4 shadow-overlay md:hidden"
        >
          <div className="flex items-center justify-between">
            <Brand onNavigate={close} expanded />
            <Dialog.Title className="sr-only">Навігація</Dialog.Title>
            <Dialog.Close asChild>
              <Button variant="ghost" size="icon" aria-label="Закрити навігацію">
                <X aria-hidden="true" />
              </Button>
            </Dialog.Close>
          </div>
          <SidebarNav onNavigate={close} expanded />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
