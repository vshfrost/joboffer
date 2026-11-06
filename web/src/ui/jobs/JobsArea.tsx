import { useMemo, useRef } from "react";
import { Route, Routes } from "react-router";

import { NotFoundPage } from "../pages/NotFoundPage";
import { AddJobPage } from "./AddJobPage";
import { JobDetailsPage } from "./JobDetailsPage";
import { JobsListPage } from "./JobsListPage";
import { OpenedJobContext, type OpenedJob } from "./OpenedJob";

/** `/vacancies/*`: список і деталі вакансії; деталі відкриваються в основній області замість списку. */
export function JobsArea() {
  const last = useRef<number | null>(null);
  const opened = useMemo<OpenedJob>(
    () => ({
      remember(id) {
        last.current = id;
      },
      take() {
        const id = last.current;
        last.current = null;
        return id;
      },
    }),
    [],
  );
  return (
    <OpenedJobContext value={opened}>
      <Routes>
        <Route index element={<JobsListPage />} />
        <Route path="new" element={<AddJobPage />} />
        <Route path=":jobId" element={<JobDetailsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </OpenedJobContext>
  );
}
