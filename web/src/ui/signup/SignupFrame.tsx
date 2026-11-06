import { CircleAlert, CircleCheck } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";

/** Каркас екранів реєстрації: логотип, картка в стилі входу й посилання на правові документи. */
export function SignupFrame({ title, subtitle, children }: { title: string; subtitle?: string; children?: ReactNode }) {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-6 px-4 py-8">
      <div className="flex items-center gap-2.5">
        <img src={`${import.meta.env.BASE_URL}brand/logo.svg`} alt="" width={32} height={32} className="size-8" />
        <span className="text-2xl font-semibold tracking-tight">joboffer</span>
      </div>
      <div className="w-full max-w-sm rounded-xl border border-border bg-card p-6 md:p-8">
        <h1 className="text-page-title font-semibold tracking-tight">{title}</h1>
        {subtitle === undefined ? null : <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
        {children}
      </div>
      <nav aria-label="Правові документи" className="flex flex-wrap justify-center gap-x-4 gap-y-1 text-caption text-muted-foreground">
        <Link to="/terms" className="hover:underline">
          Умови користування
        </Link>
        <Link to="/privacy" className="hover:underline">
          Політика конфіденційності
        </Link>
      </nav>
    </main>
  );
}

export type NoticeTone = "danger" | "warning" | "success";

const TONES: Record<NoticeTone, string> = {
  danger: "bg-status-danger text-status-danger-foreground",
  warning: "bg-status-warning text-status-warning-foreground",
  success: "bg-status-success text-status-success-foreground",
};

/** Повідомлення форми: помилка й попередження — `alert`, підтвердження — `status`. */
export function Notice({ tone, children }: { tone: NoticeTone; children: ReactNode }) {
  const Icon = tone === "success" ? CircleCheck : CircleAlert;
  return (
    <div
      role={tone === "success" ? "status" : "alert"}
      className={`flex items-start gap-2 rounded-lg px-3 py-2 text-caption ${TONES[tone]}`}
    >
      <Icon aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
      <span>{children}</span>
    </div>
  );
}

/** Екран без форми: що пішло не так і куди йти далі. */
export function ProblemScreen({ title, text, link }: { title: string; text: string; link: { to: string; label: string } }) {
  return (
    <SignupFrame title={title}>
      <p className="mt-3 text-sm text-muted-foreground">{text}</p>
      <Link to={link.to} className="mt-6 inline-block text-nav font-medium text-primary hover:underline">
        {link.label}
      </Link>
    </SignupFrame>
  );
}
