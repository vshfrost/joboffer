import { describe, expect, test } from "vitest";

import { fillPrompt, PROMPT_KEYS, PROMPT_UNAVAILABLE, REQUESTS } from "./prompts";

describe("fillPrompt", () => {
  test("підставляє номер вакансії замість {job_id}", () => {
    expect(fillPrompt("Analyse job #{job_id} in joboffer", { job_id: 104 })).toBe("Analyse job #104 in joboffer");
  });

  test("підставляє номер теми замість {topic_id}", () => {
    expect(fillPrompt("Create or update the plan for topic #{topic_id} in joboffer", { topic_id: 7 })).toBe("Create or update the plan for topic #7 in joboffer");
  });

  test("підставляє кожне входження", () => {
    expect(fillPrompt("#{job_id} and again #{job_id}", { job_id: 3 })).toBe("#3 and again #3");
  });

  test("шаблон без позначок лишається як є, дослівно", () => {
    const text = "Triage the new jobs in joboffer\n\nRules\n- one";

    expect(fillPrompt(text)).toBe(text);
    expect(fillPrompt(text, { job_id: 1 })).toBe(text);
  });

  test("позначка без значення лишається в тексті", () => {
    expect(fillPrompt("job #{job_id}, topic #{topic_id}", { job_id: 5 })).toBe("job #5, topic #{topic_id}");
  });
});

describe("REQUESTS: який шаблон просить кожна кнопка", () => {
  test("перші кроки: налаштування профілю без номерів", () => {
    expect(REQUESTS.setup).toEqual({ key: "onboarding/setup" });
  });

  test("прогалини вакансії: шаблон з номером вакансії", () => {
    expect(REQUESTS.gaps(24)).toEqual({ key: "requests/gaps", values: { job_id: 24 } });
  });

  test("додавання вакансії: шаблон без номерів", () => {
    expect(REQUESTS.addJob).toEqual({ key: "requests/add_job" });
  });

  test("додавання фактів: шаблон без номерів", () => {
    expect(REQUESTS.facts).toEqual({ key: "requests/facts" });
  });

  test("подача вакансії агентом", () => {
    expect(REQUESTS.apply(24)).toEqual({ key: "requests/apply", values: { job_id: 24 } });
  });

  test("вакансія: аналіз, підготовка, пакет до інтервʼю", () => {
    expect(REQUESTS.analysis(104)).toEqual({ key: "requests/analysis", values: { job_id: 104 } });
    expect(REQUESTS.jobPrep(24)).toEqual({ key: "requests/job_prep", values: { job_id: 24 } });
    expect(REQUESTS.interviewKit(24)).toEqual({ key: "requests/interview_kit", values: { job_id: 24 } });
  });

  test("тріаж і теми підготовки — без номерів", () => {
    expect(REQUESTS.triage).toEqual({ key: "requests/triage" });
    expect(REQUESTS.topics).toEqual({ key: "requests/topics" });
  });

  test("документ: CV і лист мають свої шаблони", () => {
    expect(REQUESTS.document("cv", 104)).toEqual({ key: "requests/cv", values: { job_id: 104 } });
    expect(REQUESTS.document("cl", 7)).toEqual({ key: "requests/cover_letter", values: { job_id: 7 } });
  });

  test("тема: план і питання", () => {
    expect(REQUESTS.plan(7)).toEqual({ key: "requests/plan", values: { topic_id: 7 } });
    expect(REQUESTS.questions(7)).toEqual({ key: "requests/questions", values: { topic_id: 7 } });
  });

  test("квіз: по всіх темах і по одній", () => {
    expect(REQUESTS.quiz()).toEqual({ key: "requests/quiz" });
    expect(REQUESTS.quiz(7)).toEqual({ key: "requests/quiz_topic", values: { topic_id: 7 } });
  });

  test("кожен ключ сервера хтось просить", () => {
    const asked = [
      REQUESTS.setup,
      REQUESTS.analysis(1),
      REQUESTS.triage,
      REQUESTS.document("cv", 1),
      REQUESTS.document("cl", 1),
      REQUESTS.plan(1),
      REQUESTS.questions(1),
      REQUESTS.quiz(),
      REQUESTS.quiz(1),
      REQUESTS.topics,
      REQUESTS.jobPrep(1),
      REQUESTS.interviewKit(1),
      REQUESTS.gaps(1),
      REQUESTS.facts,
      REQUESTS.addJob,
      REQUESTS.apply(1),
    ].map((request) => request.key);

    expect([...asked].sort()).toEqual([...PROMPT_KEYS].sort());
  });
});

test("підпис про недоступний текст запиту", () => {
  expect(PROMPT_UNAVAILABLE).toBe("Не вдалося отримати текст запиту. Спробуй ще раз.");
});
