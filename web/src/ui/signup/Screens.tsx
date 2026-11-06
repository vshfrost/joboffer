import { usePageTitle } from "../lib/usePageTitle";
import { ProblemScreen } from "./SignupFrame";

const LOGIN = { to: "/login", label: "До сторінки входу" };

/** Нема дійсного запрошення або активної реєстрації: форми не показуємо. */
export function InvalidLinkScreen() {
  usePageTitle("Реєстрація");
  return (
    <ProblemScreen
      title="Посилання недійсне"
      text="Запрошення недійсне, прострочене чи вже використане, або реєстрацію не розпочато. Попроси нове запрошення."
      link={LOGIN}
    />
  );
}

/** Запрошення не вдалося перевірити (збій сервера, забагато перевірок): причина тимчасова. */
export function InviteUnavailableScreen() {
  usePageTitle("Реєстрація");
  return <ProblemScreen title="Не вдалося перевірити запрошення" text="Спробуй ще раз трохи згодом." link={LOGIN} />;
}

/** Код більше не діє: минуло 15 хвилин або вичерпано спроби. */
export function ExpiredScreen({ invite }: { invite: string }) {
  usePageTitle("Реєстрація");
  return (
    <ProblemScreen
      title="Запит прострочено"
      text="Код більше не діє: минуло 15 хвилин або вичерпано спроби. Почни реєстрацію спочатку."
      link={{ to: `/signup?invite=${encodeURIComponent(invite)}`, label: "Почати спочатку" }}
    />
  );
}
