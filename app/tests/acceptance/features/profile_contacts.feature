# language: uk
Функціонал: Профіль — контакти для CV
  Ім’я, email, телефон, LinkedIn, GitHub, місто, дозвіл на роботу. Усе необовʼязкове; тексти помилок — як у v1.

  Передумова:
    Припустимо я — користувач "Богдан"

  Сценарій: Збереження контактів
    Якщо я зберігаю контакти: ім’я "Taras Prykladenko", email "taras@example.com", телефон "+34 600 000 000", LinkedIn "https://linkedin.com/in/taras", GitHub "https://github.com/taras", місто "Valencia", дозвіл "Spain / EU work authorization"
    Тоді контакти: email "taras@example.com", ім’я "Taras Prykladenko", телефон "+34 600 000 000", LinkedIn "https://linkedin.com/in/taras", GitHub "https://github.com/taras", місто "Valencia", дозвіл "Spain / EU work authorization"

  Сценарій: Усі контакти можна лишити порожніми
    Якщо я зберігаю контакти: ім’я "", email "", телефон "", LinkedIn "", GitHub "", місто "", дозвіл ""
    Тоді контакти порожні

  Сценарій: Пробіли в іменах і містах стискаються, на краях посилань і email прибираються
    Якщо я зберігаю контакти: ім’я "  Taras   Prykladenko ", email " taras@example.com ", телефон " +34  600 ", LinkedIn " https://linkedin.com/in/taras ", GitHub "", місто " Valencia,   Spain ", дозвіл ""
    Тоді контакти: email "taras@example.com", ім’я "Taras Prykladenko", телефон "+34 600", LinkedIn "https://linkedin.com/in/taras", GitHub "", місто "Valencia, Spain", дозвіл ""

  Структура сценарію: Некоректний email
    Якщо я зберігаю контакти з email "<email>"
    Тоді помилка поля "email" з текстом "Email виглядає некоректно, напр. name@example.com."

    Приклади:
      | email            |
      | taras             |
      | taras@            |
      | @example.com     |
      | taras@example     |
      | vl ad@example.com |

  Сценарій: LinkedIn без https://
    Якщо я зберігаю контакти з LinkedIn "http://linkedin.com/in/taras"
    Тоді помилка поля "linkedin_url" з текстом "LinkedIn — посилання з https://."

  Сценарій: GitHub без https://
    Якщо я зберігаю контакти з GitHub "github.com/taras"
    Тоді помилка поля "github_url" з текстом "GitHub — посилання з https://."

  Структура сценарію: Надто довге значення (понад 200 символів)
    Якщо я зберігаю контакти з полем "<поле>" довжиною 201 символ
    Тоді помилка поля "<поле>" з текстом "<поле> — до 200 символів."

    Приклади:
      | поле               |
      | full_name          |
      | phone              |
      | city               |
      | work_authorization |

  Сценарій: Двісті символів приймаються
    Якщо я зберігаю контакти з полем "full_name" довжиною 200 символів
    Тоді ім’я в контактах має 200 символів

  Сценарій: Надто довгий email — одна помилка
    Якщо я зберігаю контакти з полем "email" довжиною 201 символ
    Тоді помилка поля "email" з текстом "email — до 200 символів."
    І кількість помилок полів — 1

  Сценарій: Усі помилки контактів повертаються разом
    Якщо я зберігаю контакти: ім’я "", email "nope", телефон "", LinkedIn "x", GitHub "y", місто "", дозвіл ""
    Тоді кількість помилок полів — 3
    І помилка поля "email"
    І помилка поля "linkedin_url"
    І помилка поля "github_url"

  Сценарій: Помилка нічого не змінює в збережених контактах
    Припустимо я зберіг контакти: ім’я "Taras", email "taras@example.com", телефон "", LinkedIn "", GitHub "", місто "", дозвіл ""
    Якщо я зберігаю контакти з email "nope"
    Тоді отримую помилку "invalid_fields"
    І контакти: email "taras@example.com", ім’я "Taras", телефон "", LinkedIn "", GitHub "", місто "", дозвіл ""

  Сценарій: Збереження контактів не чіпає інші розділи
    Припустимо у мене заповнений профіль
    Якщо я зберігаю контакти з email "other@example.com"
    Тоді інші розділи профілю, крім "contacts", не змінились
