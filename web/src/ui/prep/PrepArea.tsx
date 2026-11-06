import { Route, Routes } from "react-router";

import { NotFoundPage } from "../pages/NotFoundPage";
import { PrepListPage } from "./PrepListPage";
import { TopicPage } from "./TopicPage";

/** `/prep`: реєстр тем і сторінка теми `/prep/{n}`. */
export function PrepArea() {
  return (
    <Routes>
      <Route index element={<PrepListPage />} />
      <Route path=":topicId" element={<TopicPage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
