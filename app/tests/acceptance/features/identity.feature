# language: uk
Функціонал: Користувачі та вхід
  Правила identity проходять через use cases і in-memory адаптери, без бази й мережі.
  Справжній Argon2 і Postgres перевіряють contract- та integration-тести.

  Сценарій: Новий користувач
    Якщо я створюю користувача "  Taras@Example.COM " з іменем "  Богдан " і паролем "correct horse battery"
    Тоді користувач створений з email "taras@example.com" і іменем "Богдан"

  Сценарій: Пароль зберігається лише як хеш
    Припустимо є користувач "taras@example.com" з іменем "Богдан" і паролем "correct horse battery"
    Тоді у сховищі хеш пароля користувача "taras@example.com" не містить "correct horse battery"

  Сценарій: Той самий email в іншому регістрі вже зайнятий
    Припустимо є користувач "taras@example.com" з іменем "Богдан" і паролем "correct horse battery"
    Якщо я створюю користувача "TARAS@example.com" з іменем "Двійник" і паролем "another long password"
    Тоді отримую помилку "email_taken"

  Сценарій: Некоректний email
    Якщо я створюю користувача "not-an-email" з іменем "Богдан" і паролем "correct horse battery"
    Тоді отримую помилку "invalid_value" для поля "email"

  Сценарій: Порожнє ім'я
    Якщо я створюю користувача "taras@example.com" з іменем "   " і паролем "correct horse battery"
    Тоді отримую помилку "invalid_value" для поля "display_name"

  Структура сценарію: Пароль на межі дозволеної довжини приймається
    Якщо я створюю користувача "taras@example.com" з іменем "Богдан" і паролем із <довжина> символів
    Тоді користувач створений з email "taras@example.com" і іменем "Богдан"

    Приклади:
      | довжина |
      | 12      |
      | 1024    |

  Структура сценарію: Пароль поза межами довжини відхиляється
    Якщо я створюю користувача "taras@example.com" з іменем "Богдан" і паролем із <довжина> символів
    Тоді отримую помилку "invalid_value" для поля "password"

    Приклади:
      | довжина |
      | 0       |
      | 11      |
      | 1025    |

  Сценарій: Вхід з правильним паролем
    Припустимо є користувач "taras@example.com" з іменем "Богдан" і паролем "correct horse battery"
    Якщо я входжу з email "taras@example.com" і паролем "correct horse battery"
    Тоді вхід успішний для "taras@example.com"

  Сценарій: Вхід з email в іншому регістрі та з пробілами
    Припустимо є користувач "taras@example.com" з іменем "Богдан" і паролем "correct horse battery"
    Якщо я входжу з email "  TARAS@Example.com " і паролем "correct horse battery"
    Тоді вхід успішний для "taras@example.com"

  Сценарій: Хибний пароль
    Припустимо є користувач "taras@example.com" з іменем "Богдан" і паролем "correct horse battery"
    Якщо я входжу з email "taras@example.com" і паролем "wrong password 123"
    Тоді отримую помилку "invalid_credentials"

  Сценарій: Невідомий email
    Якщо я входжу з email "nobody@example.com" і паролем "correct horse battery"
    Тоді отримую помилку "invalid_credentials"

  Сценарій: Некоректний email при вході — теж невірні дані
    Якщо я входжу з email "not-an-email" і паролем "correct horse battery"
    Тоді отримую помилку "invalid_credentials"

  Сценарій: Надто довгий пароль при вході — невірні дані
    Припустимо є користувач "taras@example.com" з іменем "Богдан" і паролем "correct horse battery"
    Якщо я входжу з email "taras@example.com" і паролем із 1025 символів
    Тоді отримую помилку "invalid_credentials"

  Сценарій: Хибний пароль і невідомий email дають однакову помилку
    Припустимо є користувач "taras@example.com" з іменем "Богдан" і паролем "correct horse battery"
    Якщо я входжу з email "taras@example.com" і паролем "wrong password 123"
    І я входжу з email "nobody@example.com" і паролем "correct horse battery"
    Тоді обидві спроби дають помилку "invalid_credentials" з однаковим текстом

  Сценарій: Пароль одного користувача не відкриває іншого
    Припустимо є користувач "taras@example.com" з іменем "Богдан" і паролем "correct horse battery"
    І є користувач "katya@example.com" з іменем "Наталя" і паролем "another long password"
    Якщо я входжу з email "taras@example.com" і паролем "another long password"
    Тоді отримую помилку "invalid_credentials"

  Сценарій: Кожен користувач входить у свій обліковий запис
    Припустимо є користувач "taras@example.com" з іменем "Богдан" і паролем "correct horse battery"
    І є користувач "katya@example.com" з іменем "Наталя" і паролем "another long password"
    Якщо я входжу з email "katya@example.com" і паролем "another long password"
    Тоді вхід успішний для "katya@example.com"
    І вхід належить користувачу з іменем "Наталя"
    І користувачі "taras@example.com" і "katya@example.com" мають різні id
