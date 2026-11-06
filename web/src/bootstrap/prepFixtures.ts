/** Тема з четирьох кроків: перший виконано 2026-10-25, решта чекають; для тестів сторінки теми. */
import { apiJob, apiStep, apiTopic, doneStep } from "./prepBackend";

export const LONG_NOTE = "Склав карту контекстів: Scheduling, Employees і Payroll.";

export function ddd() {
  return apiTopic(7, {
    title: "DDD у Symfony",
    kind: "tech",
    summary: "Навчитися визначати межі агрегатів і тримати бізнес-правила незалежними від Symfony та Doctrine.",
    deadline: "2026-11-03",
    jobs: [
      apiJob(24, { title: "Senior Backend Engineer", company: "Northstar", score: 86, gap: "Потрібно підтвердити практику Domain-Driven Design." }),
      apiJob(31, { title: "PHP Platform Engineer", company: "Acme", score: 79, gap: "Бракує прикладу оптимізації SQL." }),
    ],
    quiz: { total: 10, due: 4 },
    steps: [
      doneStep(31, {
        title: "Межі контекстів",
        minutes: 45,
        details: "Опиши bounded contexts і відносини між ними.",
        resources: [{ title: "Bounded Context · Martin Fowler", url: "https://martinfowler.com/bliki/BoundedContext.html" }],
        note: LONG_NOTE,
      }),
      apiStep(32, {
        title: "Агрегати та інваріанти",
        minutes: 60,
        details: "Розбери entities, value objects і consistency boundaries.",
        resources: [
          { title: "DDD Aggregate · Martin Fowler", url: "https://martinfowler.com/bliki/DDD_Aggregate.html" },
          { title: "Embeddables · Doctrine", url: "https://www.doctrine-project.org/projects/doctrine-orm/en/current/tutorials/embeddables.html" },
        ],
      }),
      apiStep(33, { kind: "practice", title: "Змоделювати агрегат Schedule", minutes: 120, details: "Створи Schedule з правилом: зміни не перетинаються." }),
      apiStep(34, { kind: "check", title: "Пояснити рішення англійською", minutes: 30, details: "How do you draw aggregate boundaries?" }),
    ],
  });
}
