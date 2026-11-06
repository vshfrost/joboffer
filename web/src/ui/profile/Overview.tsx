import { BriefcaseBusiness, Contact, Image, ListFilter, Mail, MapPin, type LucideIcon } from "lucide-react";
import { useEffect } from "react";
import { Link, useLocation } from "react-router";

import { SECTION_LABELS, SECTION_ORDER, type Profile, type ProfileSection } from "../../domain/profile";
import { summarizePhotos } from "../../domain/photos";
import {
  summarizeContacts,
  summarizeLocations,
  summarizeRules,
  summarizeTarget,
  type Summary,
} from "../../domain/profileSummary";
import { useAuth } from "../auth/AuthProvider";
import { FirstStepsCard } from "../onboarding/FirstStepsCard";
import { usePhotos } from "../photos/PhotosProvider";
import { cn } from "../lib/cn";
import { usePageTitle } from "../lib/usePageTitle";
import { PageHeading } from "../pages/PageHeading";
import { useProfile } from "./ProfileProvider";

interface CardSpec {
  section: ProfileSection;
  icon: LucideIcon;
  hint: string;
  action: string;
  summary(profile: Profile): Summary;
}

const CARDS: Record<ProfileSection, CardSpec> = {
  target: {
    section: "target",
    icon: BriefcaseBusiness,
    hint: "Ролі, рівень, зарплата та галузі",
    action: "Редагувати ціль",
    summary: (profile) => summarizeTarget(profile.target),
  },
  locations: {
    section: "locations",
    icon: MapPin,
    hint: "Формати для кожного місця, синоніми, релокація",
    action: "Керувати локаціями",
    summary: (profile) => summarizeLocations(profile.locations),
  },
  rules: {
    section: "rules",
    icon: ListFilter,
    hint: "Що імпортувати, що відхиляти й що показувати нижче",
    action: "Налаштувати правила",
    summary: (profile) => summarizeRules(profile.rules),
  },
  contacts: {
    section: "contacts",
    icon: Contact,
    hint: "Контакти, посилання й дозвіл на роботу",
    action: "Редагувати контакти",
    summary: (profile) => summarizeContacts(profile.contacts),
  },
};

const CARD = "flex min-h-48 flex-col gap-3 rounded-xl border border-border bg-card p-5 text-left max-sm:min-h-40";

function Title({ icon: Icon, children }: { icon: LucideIcon; children: string }) {
  return (
    <h2 className="flex items-center gap-2.5 text-section font-semibold">
      <Icon aria-hidden="true" className="size-[1.125rem] shrink-0 text-primary" />
      {children}
    </h2>
  );
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter((part) => part !== "")
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join("");
}

/** Картка «Фото для CV»: кількість і останнє додане — з тих самих даних, що й галерея. */
function PhotosCard() {
  const { state } = usePhotos();
  const summary = state.status === "ready" ? summarizePhotos(state.library) : null;
  return (
    <li className="min-w-0">
      <Link id="profile-card-photos" to="/profile/photos" state={{ focus: true }} className={cn(CARD, "h-full transition-colors duration-140 hover:border-primary")}>
        <Title icon={Image}>Фото для CV</Title>
        {summary !== null ? (
          <span className={cn("text-nav [overflow-wrap:anywhere]", summary.empty && "text-muted-foreground")}>
            {summary.lines.map((line) => (
              <span key={line} className="block">
                {line}
              </span>
            ))}
          </span>
        ) : state.status === "error" ? (
          <span className="text-nav text-muted-foreground">
            {state.problem === "unauthorized" ? "Сесія завершилась. Увійди знову." : "Не вдалося завантажити фото."}
          </span>
        ) : (
          <span role="status" aria-label="Завантажуємо фото…" className="text-nav text-muted-foreground">
            Завантажуємо…
          </span>
        )}
        <span className="text-caption text-muted-foreground">Галерея, підписи та кадрування фото</span>
        <span className="mt-auto flex items-center justify-between gap-2 pt-2 text-caption text-primary">Відкрити галерею</span>
      </Link>
    </li>
  );
}

export function Overview() {
  usePageTitle("Профіль");
  const { saved, dirtySections } = useProfile();
  const { state } = useAuth();
  const { state: navigation } = useLocation();
  const from = (navigation as { from?: ProfileSection | "photos" } | null)?.from;

  // Повернулися з розділу: фокус на картку, з якої його відкрито.
  useEffect(() => {
    if (from !== undefined) {
      document.getElementById(`profile-card-${from}`)?.focus();
    }
  }, [from]);

  const name = state.status === "authenticated" ? state.user.displayName : "";
  const position = [saved.target.roles[0], saved.contacts.city].filter((part) => part !== undefined && part !== "").join(" · ");

  return (
    <>
      <PageHeading title="Профіль" subtitle="Усе важливе — в огляді. Деталі — у своєму розділі." />
      {name === "" ? null : (
        <div className="mb-6 flex min-w-0 items-center gap-4">
          <div aria-hidden="true" className="flex size-12 shrink-0 items-center justify-center rounded-full bg-selected text-section font-semibold text-selected-foreground">
            {initials(name)}
          </div>
          <div className="min-w-0">
            <p className="text-section font-semibold [overflow-wrap:anywhere]">{name}</p>
            {position === "" ? null : (
              <p title={position} className="truncate text-caption text-muted-foreground">
                {position}
              </p>
            )}
          </div>
        </div>
      )}
      {dirtySections.length === 0 ? null : (
        <p className="mb-5 rounded-lg bg-selected px-4 py-3 text-caption text-selected-foreground">
          {`Незбережені зміни: ${dirtySections.map((section) => SECTION_LABELS[section]).join(", ")}. Чернетки зберігаються, поки ця сторінка відкрита.`}
        </p>
      )}
      <FirstStepsCard />
      <ul className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {SECTION_ORDER.map((section) => {
          const spec = CARDS[section];
          const summary = spec.summary(saved);
          return (
            <li key={section} className="min-w-0">
              <Link
                id={`profile-card-${section}`}
                to={`/profile/${section}`}
                state={{ focus: true }}
                className={cn(CARD, "h-full transition-colors duration-140 hover:border-primary")}
              >
                <Title icon={spec.icon}>{SECTION_LABELS[section]}</Title>
                <span className={cn("text-nav [overflow-wrap:anywhere]", summary.empty && "text-muted-foreground")}>
                  {summary.lines.map((line) => (
                    <span key={line} className="block">
                      {line}
                    </span>
                  ))}
                </span>
                <span className="text-caption text-muted-foreground">{spec.hint}</span>
                <span className="mt-auto flex items-center justify-between gap-2 pt-2 text-caption text-primary">
                  {spec.action}
                  {dirtySections.includes(section) ? (
                    <span className="rounded-md bg-selected px-2 py-0.5 font-medium text-selected-foreground">Є зміни</span>
                  ) : null}
                </span>
              </Link>
            </li>
          );
        })}
        <PhotosCard />
        <li className="min-w-0">
          <Link id="profile-card-mail" to="/profile/mail" className={cn(CARD, "h-full transition-colors duration-140 hover:border-primary")}>
            <Title icon={Mail}>Пошта</Title>
            <span className="text-nav">Вхідні, адреса для пересилання та синк</span>
            <span className="text-caption text-muted-foreground">Переслані листи рекрутерів і код підтвердження Gmail</span>
            <span className="mt-auto flex items-center justify-between gap-2 pt-2 text-caption text-primary">Відкрити пошту</span>
          </Link>
        </li>
      </ul>
    </>
  );
}
