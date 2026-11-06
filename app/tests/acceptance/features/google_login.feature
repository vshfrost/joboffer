# language: uk
Функціонал: Вхід через Google лише для наявних користувачів
  Google ніколи не створює користувача: пускає лише того, хто вже є в `users` (за Google `sub` або за email).
  Сценарії проходять через use cases сесій і in-memory адаптери.

  Сценарій: Наявний користувач заходить за email
    Припустимо є користувач "taras@example.com" з іменем "Богдан" і паролем "correct horse battery"
    Якщо я входжу через Google з sub "sub-1" і підтвердженим email "taras@example.com"
    Тоді сесію видано для "taras@example.com"
    І кількість користувачів у сховищі — 1

  Сценарій: Наявний користувач заходить за Google sub
    Припустимо є користувач "taras@example.com" з іменем "Богдан" і паролем "correct horse battery"
    І я входжу через Google з sub "sub-1" і підтвердженим email "taras@example.com"
    Якщо я входжу через Google з sub "sub-1" і підтвердженим email "other@example.com"
    Тоді сесію видано для "taras@example.com"
    І кількість користувачів у сховищі — 1

  Сценарій: Google не передав email
    Припустимо є користувач "taras@example.com" з іменем "Богдан" і паролем "correct horse battery"
    Якщо я входжу через Google з sub "sub-1" без email
    Тоді отримую помилку "email_required"
    І кількість сесій у сховищі — 0
    І кількість користувачів у сховищі — 1

  Сценарій: Email не підтверджений
    Припустимо є користувач "taras@example.com" з іменем "Богдан" і паролем "correct horse battery"
    Якщо я входжу через Google з sub "sub-1" і непідтвердженим email "taras@example.com"
    Тоді отримую помилку "email_required"
    І кількість сесій у сховищі — 0

  Сценарій: Email, якого немає серед користувачів, не реєструється
    Якщо я входжу через Google з sub "sub-1" і підтвердженим email "stranger@example.com"
    Тоді отримую помилку "email_required"
    І кількість сесій у сховищі — 0
    І кількість користувачів у сховищі — 0
