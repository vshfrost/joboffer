# language: uk
Функціонал: Сесії входу
  Сесії проходять через use cases і in-memory адаптери. Політика в тестах: простій 12 годин,
  абсолютний строк 48 годин, ліміт — 5 невдалих входів за 15 хвилин для пари «клієнт + email».

  Передумова:
    Припустимо є користувач "taras@example.com" з іменем "Богдан" і паролем "correct horse battery"

  Сценарій: Вхід видає сесію, за якою видно користувача
    Якщо я входжу з email "taras@example.com" і паролем "correct horse battery" з клієнта "10.0.0.1"
    Тоді сесію видано для "taras@example.com"
    Якщо я перевіряю сесію користувача "taras@example.com"
    Тоді сесія належить "taras@example.com"

  Сценарій: У сховищі лежить лише дайджест токена
    Якщо я входжу з email "taras@example.com" і паролем "correct horse battery" з клієнта "10.0.0.1"
    Тоді у сховищі сесій немає токена користувача "taras@example.com"

  Сценарій: Хибний пароль не створює сесію
    Якщо я входжу з email "taras@example.com" і паролем "wrong password 123" з клієнта "10.0.0.1"
    Тоді отримую помилку "invalid_credentials"
    І кількість сесій у сховищі — 0

  Сценарій: Невідомий токен
    Якщо я перевіряю сесію з токеном "token-unknown"
    Тоді отримую помилку "not_authenticated"

  Сценарій: Порожній або надто довгий токен
    Якщо я перевіряю сесію з порожнім токеном
    Тоді отримую помилку "not_authenticated"
    Якщо я перевіряю сесію з токеном довжиною 257 символів
    Тоді отримую помилку "not_authenticated"

  Сценарій: Простій довший за ліміт закриває сесію
    Якщо я входжу з email "taras@example.com" і паролем "correct horse battery" з клієнта "10.0.0.1"
    І минає 13 годин
    І я перевіряю сесію користувача "taras@example.com"
    Тоді отримую помилку "not_authenticated"

  Сценарій: Активність продовжує сесію
    Якщо я входжу з email "taras@example.com" і паролем "correct horse battery" з клієнта "10.0.0.1"
    І минає 11 годин
    І я перевіряю сесію користувача "taras@example.com"
    І минає 11 годин
    І я перевіряю сесію користувача "taras@example.com"
    Тоді сесія належить "taras@example.com"

  Сценарій: Абсолютний строк закриває навіть активну сесію
    Якщо я входжу з email "taras@example.com" і паролем "correct horse battery" з клієнта "10.0.0.1"
    І минає 11 годин
    І я перевіряю сесію користувача "taras@example.com"
    І минає 11 годин
    І я перевіряю сесію користувача "taras@example.com"
    І минає 11 годин
    І я перевіряю сесію користувача "taras@example.com"
    І минає 11 годин
    І я перевіряю сесію користувача "taras@example.com"
    Тоді сесія належить "taras@example.com"
    Якщо минає 11 годин
    І я перевіряю сесію користувача "taras@example.com"
    Тоді отримую помилку "not_authenticated"

  Сценарій: Вихід закриває сесію
    Якщо я входжу з email "taras@example.com" і паролем "correct horse battery" з клієнта "10.0.0.1"
    І я закриваю сесію користувача "taras@example.com"
    І я перевіряю сесію користувача "taras@example.com"
    Тоді отримую помилку "not_authenticated"

  Сценарій: Повторний вихід і вихід з невідомим токеном не падають
    Якщо я входжу з email "taras@example.com" і паролем "correct horse battery" з клієнта "10.0.0.1"
    І я закриваю сесію користувача "taras@example.com"
    І я закриваю сесію користувача "taras@example.com"
    І я закриваю сесію з токеном "token-unknown"
    Тоді помилок не було

  Сценарій: Дві сесії одного користувача незалежні
    Якщо я входжу з email "taras@example.com" і паролем "correct horse battery" з клієнта "10.0.0.1"
    І я входжу з email "taras@example.com" і паролем "correct horse battery" з клієнта "10.0.0.2"
    І я закриваю сесію номер 1 користувача "taras@example.com"
    І я перевіряю сесію номер 2 користувача "taras@example.com"
    Тоді сесія належить "taras@example.com"

  Сценарій: Сесія видає саме свого користувача
    Припустимо є користувач "katya@example.com" з іменем "Наталя" і паролем "another long password"
    Якщо я входжу з email "taras@example.com" і паролем "correct horse battery" з клієнта "10.0.0.1"
    І я входжу з email "katya@example.com" і паролем "another long password" з клієнта "10.0.0.1"
    І я перевіряю сесію користувача "katya@example.com"
    Тоді сесія належить "katya@example.com"
    І імʼя в сесії — "Наталя"

  Сценарій: Шостий вхід після п'яти невдалих блокується, навіть з правильним паролем
    Якщо я 5 разів входжу з email "taras@example.com" і хибним паролем з клієнта "10.0.0.1"
    І я входжу з email "taras@example.com" і паролем "correct horse battery" з клієнта "10.0.0.1"
    Тоді отримую помилку "too_many_attempts"
    І кількість сесій у сховищі — 0

  Сценарій: Чотири невдалі входи ще не блокують
    Якщо я 4 разів входжу з email "taras@example.com" і хибним паролем з клієнта "10.0.0.1"
    І я входжу з email "taras@example.com" і паролем "correct horse battery" з клієнта "10.0.0.1"
    Тоді сесію видано для "taras@example.com"

  Сценарій: Блокування знімається, коли минає вікно
    Якщо я 5 разів входжу з email "taras@example.com" і хибним паролем з клієнта "10.0.0.1"
    І минає 16 хвилин
    І я входжу з email "taras@example.com" і паролем "correct horse battery" з клієнта "10.0.0.1"
    Тоді сесію видано для "taras@example.com"

  Сценарій: Блокування каже, через скільки секунд повторити
    Якщо я 5 разів входжу з email "taras@example.com" і хибним паролем з клієнта "10.0.0.1"
    І минає 5 хвилин
    І я входжу з email "taras@example.com" і паролем "correct horse battery" з клієнта "10.0.0.1"
    Тоді отримую помилку "too_many_attempts"
    І повторна спроба можлива через 600 секунд

  Сценарій: Невдачі іншого клієнта не блокують
    Якщо я 5 разів входжу з email "taras@example.com" і хибним паролем з клієнта "10.0.0.1"
    І я входжу з email "taras@example.com" і паролем "correct horse battery" з клієнта "10.0.0.2"
    Тоді сесію видано для "taras@example.com"

  Сценарій: Невдачі для іншого email не блокують
    Припустимо є користувач "katya@example.com" з іменем "Наталя" і паролем "another long password"
    Якщо я 5 разів входжу з email "katya@example.com" і хибним паролем з клієнта "10.0.0.1"
    І я входжу з email "taras@example.com" і паролем "correct horse battery" з клієнта "10.0.0.1"
    Тоді сесію видано для "taras@example.com"

  Сценарій: Невідомий email рахується так само, як хибний пароль
    Якщо я 5 разів входжу з email "nobody@example.com" і хибним паролем з клієнта "10.0.0.1"
    І я входжу з email "nobody@example.com" і паролем "correct horse battery" з клієнта "10.0.0.1"
    Тоді отримую помилку "too_many_attempts"

  Сценарій: Email в іншому регістрі рахується як той самий
    Якщо я 3 разів входжу з email "taras@example.com" і хибним паролем з клієнта "10.0.0.1"
    І я 2 разів входжу з email " TARAS@example.com" і хибним паролем з клієнта "10.0.0.1"
    І я входжу з email "taras@example.com" і паролем "correct horse battery" з клієнта "10.0.0.1"
    Тоді отримую помилку "too_many_attempts"

  Сценарій: Успішний вхід скидає лічильник
    Якщо я 4 разів входжу з email "taras@example.com" і хибним паролем з клієнта "10.0.0.1"
    І я входжу з email "taras@example.com" і паролем "correct horse battery" з клієнта "10.0.0.1"
    І я 4 разів входжу з email "taras@example.com" і хибним паролем з клієнта "10.0.0.1"
    І я входжу з email "taras@example.com" і паролем "correct horse battery" з клієнта "10.0.0.1"
    Тоді сесію видано для "taras@example.com"

  Сценарій: Протухлі сесії прибираються при наступному вході
    Якщо я входжу з email "taras@example.com" і паролем "correct horse battery" з клієнта "10.0.0.1"
    І минає 49 годин
    І я входжу з email "taras@example.com" і паролем "correct horse battery" з клієнта "10.0.0.2"
    Тоді кількість сесій у сховищі — 1

  Сценарій: Старі невдачі забуваються при наступному вході
    Якщо я 3 разів входжу з email "nobody@example.com" і хибним паролем з клієнта "10.0.0.9"
    І минає 20 хвилин
    І я входжу з email "taras@example.com" і паролем "correct horse battery" з клієнта "10.0.0.1"
    Тоді кількість записів про невдалі входи — 0
