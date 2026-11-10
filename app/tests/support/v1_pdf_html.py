"""Зразки документів і еталонний HTML, знятий із шаблонів v1 (`origin/main` `99a2007`, Jinja2).

Згенеровано одноразово зі справжнього рендера v1: CV без фото, CV з фото (`PHOTO`) і лист.

Після v1 (63d7b9): LinkedIn і GitHub у шапці — активні посилання `<a href>` з повним URL, видимий текст той самий,
у стилях одне правило `a` (колір і підкреслення як у тексту)."""

from typing import Any

CV: dict[str, Any] = {
    "headline": {
        "text": "Senior Backend Engineer — Payments & <Cards>",
        "fact_ids": [1],
    },
    "summary": {
        "text": "Backend engineer with 8 years building financial APIs in Python & Kotlin.",
        "fact_ids": [1],
    },
    "sections": [
        {
            "name": "Skills",
            "entries": [
                {
                    "heading": {"text": "Backend & Architecture", "fact_ids": [1]},
                    "bullets": [
                        {"text": "Python (5 years)", "fact_ids": [1]},
                        {"text": "FastAPI", "fact_ids": [1]},
                        {"text": "PHP · Laravel", "fact_ids": [1]},
                    ],
                },
                {
                    "heading": {"text": "Cloud: AWS, GCP, Kubernetes", "fact_ids": [1]},
                    "bullets": [],
                },
            ],
        },
        {
            "name": "Experience",
            "entries": [
                {
                    "heading": {
                        "text": "Senior Backend Engineer · Acme Bank",
                        "fact_ids": [1],
                    },
                    "meta": {"text": "Jan 2021 - Dec 2024", "fact_ids": [1]},
                    "subtitle": {
                        "text": "Payments platform · team of six",
                        "fact_ids": [1],
                    },
                    "bullets": [
                        {
                            "text": "Cut payment latency by 40% across 12 services",
                            "fact_ids": [1],
                        },
                        {
                            "text": "Built <card> issuing APIs (PCI DSS)",
                            "fact_ids": [1],
                        },
                    ],
                },
                {
                    "heading": {"text": "Backend Engineer · Startup", "fact_ids": [1]},
                    "bullets": [
                        {"text": "Built the first version of the API", "fact_ids": [1]}
                    ],
                },
                {"heading": {"text": "Intern · Beta", "fact_ids": [1]}, "bullets": []},
            ],
        },
        {
            "name": "Projects",
            "entries": [
                {
                    "heading": {"text": "AI Stylist", "fact_ids": [1]},
                    "meta": {"text": "Independent project", "fact_ids": [1]},
                    "bullets": [
                        {"text": "Assistant that assembles outfits", "fact_ids": [1]}
                    ],
                }
            ],
        },
        {
            "name": "Education and Languages",
            "entries": [
                {
                    "heading": {
                        "text": "MSc Software Engineering · Example University · 2015",
                        "fact_ids": [1],
                    },
                    "bullets": [],
                },
                {
                    "heading": {"text": "English C1 · Spanish B1", "fact_ids": [1]},
                    "bullets": [],
                },
            ],
        },
    ],
}

LETTER: dict[str, Any] = {
    "paragraphs": [
        "Dear Acme team, I am applying for the Senior Backend Engineer role. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. ",
        "At Acme Bank I cut payment latency by 40% across 12 services & kept 99.99% availability <always>.",
        "Best regards,\nAlex <Example>\n+34 600 000 000",
    ],
    "fact_ids": [1],
}

CONTACTS: dict[str, str] = {
    "full_name": "Alex Example",
    "email": "alex@example.com",
    "phone": "+34 600 000 000",
    "city": "Valencia, Spain",
    "linkedin_url": "https://www.linkedin.com/in/alex-example/",
    "github_url": "https://github.com/alex-example",
    "work_authorization": "Spain / EU work authorization",
}

# Байти «фото» для еталона CV з фото; у HTML вони стають data URI.
PHOTO = b"\xff\xd8photo"

V1_CV_HTML = '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<title>Alex Example — CV</title>\n<style>\n  /* Стиль зразка власника (CV 2026-09-26): A4, DejaVu Sans, темна шапка #191919 із золотою\n     смугою #DA9F1A; з 2-ї сторінки — вузька шапка з ім\'ям і посадою (колонтитул для lint). */\n  @page {\n    size: A4;\n    margin: 70pt 48pt 54pt;\n    @top-left {\n      content: string(name);\n      vertical-align: top; padding-top: 19pt;\n      font: bold 11pt "DejaVu Sans", sans-serif; color: #fff; text-transform: uppercase;\n    }\n    @top-right {\n      content: string(headline);\n      vertical-align: top; padding-top: 21.5pt;\n      font: 8pt "DejaVu Sans", sans-serif; color: #FFCB55; text-transform: uppercase;\n    }\n    @bottom-right {\n      content: counter(page);\n      vertical-align: bottom; padding-bottom: 20pt;\n      font: 7pt "DejaVu Sans", sans-serif; color: #5C5C5C;\n    }\n  }\n  @page :first {\n    margin-top: 0;\n    @top-left { content: none; }\n    @top-right { content: none; }\n  }\n  /* Смуги — блоки position: fixed (повторюються на кожній сторінці; фон @page WeasyPrint\n     малює лише в межах поля сторінки). На 1-й сторінці вузька смуга поза аркушем. */\n  .band { position: fixed; top: -70pt; left: -48pt; width: 595.3pt; height: 49pt; background: #191919; border-bottom: 4pt solid #DA9F1A; }\n  .footer-rule { position: fixed; bottom: -18pt; left: 0; right: 0; border-top: 0.5pt solid #D9D9D9; }\n  body { font-family: "DejaVu Sans", sans-serif; font-kerning: none; font-size: 9.15pt; line-height: 13.6pt; color: #191919; margin: 0; }\n  header { height: 149pt; box-sizing: border-box; margin: 0 -48pt 17pt; padding: 25pt 48pt 0; background: #191919; border-bottom: 4pt solid #DA9F1A; color: #fff; }\n  /* Рамка фото — пропорції зразка (858 × 960); кадр під неї користувач обирає в редакторі на /profile.\n     Позиція — від поля 1-ї сторінки: позиціонована шапка малювалася б після тексту сторінки,\n     і парсер читав би її текст останнім. */\n  .photo { position: absolute; top: 19pt; right: 0; width: 101pt; height: 113pt; }\n  .with-photo > h1, .with-photo > p { padding-right: 115pt; }\n  h1 { font-size: 20.5pt; line-height: 24pt; margin: 0; text-transform: uppercase; string-set: name content(text); }\n  .headline { font-size: 10.2pt; font-weight: bold; color: #FFCB55; text-transform: uppercase; margin: 6pt 0 9pt; string-set: headline content(text); }\n  .contacts { font-size: 8pt; line-height: 16pt; margin: 0; }\n  .contacts span { white-space: nowrap; }\n  .sep { margin: 0 4pt; }\n  a { color: inherit; text-decoration: none; }\n  h2 { font-size: 10.6pt; text-transform: uppercase; margin: 12pt 0 7pt; padding-bottom: 5pt; border-bottom: 0.6pt solid #DA9F1A; break-after: avoid; }\n  section:first-of-type h2 { margin-top: 0; }\n  .summary { font-size: 9.4pt; line-height: 13.8pt; margin: 0; }\n  table { border-collapse: collapse; width: 100%; }\n  td, th { padding: 0; text-align: left; vertical-align: baseline; }\n  .skills th { width: 1%; white-space: nowrap; padding: 2pt 10pt 4pt 0; font-size: 8pt; text-transform: uppercase; }\n  .skills td { padding: 2pt 0 4pt 10pt; border-left: 0.8pt solid #DA9F1A; font-size: 8.8pt; line-height: 12.7pt; }\n  .entry { margin-bottom: 7pt; }\n  .row { break-after: avoid; }\n  .title { font-size: 10.2pt; font-weight: bold; }\n  .meta { white-space: nowrap; text-align: right; padding-left: 12pt; font-size: 8.4pt; color: #5C5C5C; }\n  .subtitle { font-size: 8.8pt; line-height: 12.7pt; color: #5C5C5C; margin: 2pt 0 0; break-after: avoid; }\n  ul { margin: 3pt 0 0; padding-left: 13pt; }\n  li { margin: 0 0 2.2pt; break-inside: avoid; }\n  .line { margin: 0 0 3pt; font-size: 8.8pt; }\n</style>\n</head>\n<body>\n<div class="band"></div>\n<div class="footer-rule"></div>\n<header>\n  <h1>Alex Example</h1>\n  <p class="headline">Senior Backend Engineer — Payments &amp; &lt;Cards&gt;</p>\n  <p class="contacts"><span>Valencia, Spain</span><span class="sep">·</span><span>Spain / EU work authorization</span></p>\n  <p class="contacts"><span>alex@example.com</span><span class="sep">·</span><span>+34 600 000 000</span></p>\n  <p class="contacts"><span><a href="https://www.linkedin.com/in/alex-example/">linkedin.com/in/alex-example</a></span><span class="sep">·</span><span><a href="https://github.com/alex-example">github.com/alex-example</a></span></p>\n</header>\n<section>\n  <h2>Profile</h2>\n  <p class="summary">Backend engineer with 8 years building financial APIs in Python &amp; Kotlin.</p>\n</section>\n<section>\n  <h2>Skills</h2>\n  <table class="skills">\n    <tr><th>Backend &amp; Architecture</th><td>Python (5 years) · FastAPI · PHP · Laravel</td></tr>\n    <tr><td colspan="2">Cloud: AWS, GCP, Kubernetes</td></tr>\n  </table>\n</section>\n<section>\n  <h2>Professional Experience</h2>\n  <div class="entry">\n    <table class="row"><tr>\n      <td class="title">Senior Backend Engineer · Acme Bank</td>\n<td class="meta">Jan 2021 - Dec 2024</td>    </tr></table>\n<p class="subtitle">Payments platform · team of six</p>    <ul>\n      <li>Cut payment latency by 40% across 12 services</li>\n      <li>Built &lt;card&gt; issuing APIs (PCI DSS)</li>\n    </ul>\n  </div>\n  <div class="entry">\n    <table class="row"><tr>\n      <td class="title">Backend Engineer · Startup</td>\n    </tr></table>\n    <ul>\n      <li>Built the first version of the API</li>\n    </ul>\n  </div>\n  <p class="line">Intern · Beta</p>\n</section>\n<section>\n  <h2>Selected Projects</h2>\n  <div class="entry">\n    <table class="row"><tr>\n      <td class="title">AI Stylist</td>\n<td class="meta">Independent project</td>    </tr></table>\n    <ul>\n      <li>Assistant that assembles outfits</li>\n    </ul>\n  </div>\n</section>\n<section>\n  <h2>Education and Languages</h2>\n  <p class="line">MSc Software Engineering · Example University · 2015</p>\n  <p class="line">English C1 · Spanish B1</p>\n</section>\n</body>\n</html>'

V1_CV_HTML_WITH_PHOTO = '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<title>Alex Example — CV</title>\n<style>\n  /* Стиль зразка власника (CV 2026-09-26): A4, DejaVu Sans, темна шапка #191919 із золотою\n     смугою #DA9F1A; з 2-ї сторінки — вузька шапка з ім\'ям і посадою (колонтитул для lint). */\n  @page {\n    size: A4;\n    margin: 70pt 48pt 54pt;\n    @top-left {\n      content: string(name);\n      vertical-align: top; padding-top: 19pt;\n      font: bold 11pt "DejaVu Sans", sans-serif; color: #fff; text-transform: uppercase;\n    }\n    @top-right {\n      content: string(headline);\n      vertical-align: top; padding-top: 21.5pt;\n      font: 8pt "DejaVu Sans", sans-serif; color: #FFCB55; text-transform: uppercase;\n    }\n    @bottom-right {\n      content: counter(page);\n      vertical-align: bottom; padding-bottom: 20pt;\n      font: 7pt "DejaVu Sans", sans-serif; color: #5C5C5C;\n    }\n  }\n  @page :first {\n    margin-top: 0;\n    @top-left { content: none; }\n    @top-right { content: none; }\n  }\n  /* Смуги — блоки position: fixed (повторюються на кожній сторінці; фон @page WeasyPrint\n     малює лише в межах поля сторінки). На 1-й сторінці вузька смуга поза аркушем. */\n  .band { position: fixed; top: -70pt; left: -48pt; width: 595.3pt; height: 49pt; background: #191919; border-bottom: 4pt solid #DA9F1A; }\n  .footer-rule { position: fixed; bottom: -18pt; left: 0; right: 0; border-top: 0.5pt solid #D9D9D9; }\n  body { font-family: "DejaVu Sans", sans-serif; font-kerning: none; font-size: 9.15pt; line-height: 13.6pt; color: #191919; margin: 0; }\n  header { height: 149pt; box-sizing: border-box; margin: 0 -48pt 17pt; padding: 25pt 48pt 0; background: #191919; border-bottom: 4pt solid #DA9F1A; color: #fff; }\n  /* Рамка фото — пропорції зразка (858 × 960); кадр під неї користувач обирає в редакторі на /profile.\n     Позиція — від поля 1-ї сторінки: позиціонована шапка малювалася б після тексту сторінки,\n     і парсер читав би її текст останнім. */\n  .photo { position: absolute; top: 19pt; right: 0; width: 101pt; height: 113pt; }\n  .with-photo > h1, .with-photo > p { padding-right: 115pt; }\n  h1 { font-size: 20.5pt; line-height: 24pt; margin: 0; text-transform: uppercase; string-set: name content(text); }\n  .headline { font-size: 10.2pt; font-weight: bold; color: #FFCB55; text-transform: uppercase; margin: 6pt 0 9pt; string-set: headline content(text); }\n  .contacts { font-size: 8pt; line-height: 16pt; margin: 0; }\n  .contacts span { white-space: nowrap; }\n  .sep { margin: 0 4pt; }\n  a { color: inherit; text-decoration: none; }\n  h2 { font-size: 10.6pt; text-transform: uppercase; margin: 12pt 0 7pt; padding-bottom: 5pt; border-bottom: 0.6pt solid #DA9F1A; break-after: avoid; }\n  section:first-of-type h2 { margin-top: 0; }\n  .summary { font-size: 9.4pt; line-height: 13.8pt; margin: 0; }\n  table { border-collapse: collapse; width: 100%; }\n  td, th { padding: 0; text-align: left; vertical-align: baseline; }\n  .skills th { width: 1%; white-space: nowrap; padding: 2pt 10pt 4pt 0; font-size: 8pt; text-transform: uppercase; }\n  .skills td { padding: 2pt 0 4pt 10pt; border-left: 0.8pt solid #DA9F1A; font-size: 8.8pt; line-height: 12.7pt; }\n  .entry { margin-bottom: 7pt; }\n  .row { break-after: avoid; }\n  .title { font-size: 10.2pt; font-weight: bold; }\n  .meta { white-space: nowrap; text-align: right; padding-left: 12pt; font-size: 8.4pt; color: #5C5C5C; }\n  .subtitle { font-size: 8.8pt; line-height: 12.7pt; color: #5C5C5C; margin: 2pt 0 0; break-after: avoid; }\n  ul { margin: 3pt 0 0; padding-left: 13pt; }\n  li { margin: 0 0 2.2pt; break-inside: avoid; }\n  .line { margin: 0 0 3pt; font-size: 8.8pt; }\n</style>\n</head>\n<body>\n<div class="band"></div>\n<div class="footer-rule"></div>\n<header class="with-photo">\n<img class="photo" src="data:image/jpeg;base64,/9hwaG90bw==" alt="">  <h1>Alex Example</h1>\n  <p class="headline">Senior Backend Engineer — Payments &amp; &lt;Cards&gt;</p>\n  <p class="contacts"><span>Valencia, Spain</span><span class="sep">·</span><span>Spain / EU work authorization</span></p>\n  <p class="contacts"><span>alex@example.com</span><span class="sep">·</span><span>+34 600 000 000</span></p>\n  <p class="contacts"><span><a href="https://www.linkedin.com/in/alex-example/">linkedin.com/in/alex-example</a></span><span class="sep">·</span><span><a href="https://github.com/alex-example">github.com/alex-example</a></span></p>\n</header>\n<section>\n  <h2>Profile</h2>\n  <p class="summary">Backend engineer with 8 years building financial APIs in Python &amp; Kotlin.</p>\n</section>\n<section>\n  <h2>Skills</h2>\n  <table class="skills">\n    <tr><th>Backend &amp; Architecture</th><td>Python (5 years) · FastAPI · PHP · Laravel</td></tr>\n    <tr><td colspan="2">Cloud: AWS, GCP, Kubernetes</td></tr>\n  </table>\n</section>\n<section>\n  <h2>Professional Experience</h2>\n  <div class="entry">\n    <table class="row"><tr>\n      <td class="title">Senior Backend Engineer · Acme Bank</td>\n<td class="meta">Jan 2021 - Dec 2024</td>    </tr></table>\n<p class="subtitle">Payments platform · team of six</p>    <ul>\n      <li>Cut payment latency by 40% across 12 services</li>\n      <li>Built &lt;card&gt; issuing APIs (PCI DSS)</li>\n    </ul>\n  </div>\n  <div class="entry">\n    <table class="row"><tr>\n      <td class="title">Backend Engineer · Startup</td>\n    </tr></table>\n    <ul>\n      <li>Built the first version of the API</li>\n    </ul>\n  </div>\n  <p class="line">Intern · Beta</p>\n</section>\n<section>\n  <h2>Selected Projects</h2>\n  <div class="entry">\n    <table class="row"><tr>\n      <td class="title">AI Stylist</td>\n<td class="meta">Independent project</td>    </tr></table>\n    <ul>\n      <li>Assistant that assembles outfits</li>\n    </ul>\n  </div>\n</section>\n<section>\n  <h2>Education and Languages</h2>\n  <p class="line">MSc Software Engineering · Example University · 2015</p>\n  <p class="line">English C1 · Spanish B1</p>\n</section>\n</body>\n</html>'

V1_LETTER_HTML = '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<title>Alex Example — Cover Letter</title>\n<style>\n  /* Та сама шапка, що в CV (cv.html), без фото; лист — одна сторінка. */\n  @page { size: A4; margin: 0 48pt 54pt; }\n  body { font-family: "DejaVu Sans", sans-serif; font-kerning: none; font-size: 10pt; line-height: 15pt; color: #191919; margin: 0; }\n  header { margin: 0 -48pt 30pt; padding: 25pt 48pt 18pt; background: #191919; border-bottom: 4pt solid #DA9F1A; color: #fff; }\n  h1 { font-size: 20.5pt; line-height: 24pt; margin: 0 0 10pt; text-transform: uppercase; }\n  .contacts { font-size: 8pt; line-height: 16pt; margin: 0; }\n  .contacts span { white-space: nowrap; }\n  .sep { margin: 0 4pt; }\n  a { color: inherit; text-decoration: none; }\n  p { margin: 0 0 10pt; }\n</style>\n</head>\n<body>\n<header>\n  <h1>Alex Example</h1>\n  <p class="contacts"><span>Valencia, Spain</span><span class="sep">·</span><span>Spain / EU work authorization</span></p>\n  <p class="contacts"><span>alex@example.com</span><span class="sep">·</span><span>+34 600 000 000</span></p>\n  <p class="contacts"><span><a href="https://www.linkedin.com/in/alex-example/">linkedin.com/in/alex-example</a></span><span class="sep">·</span><span><a href="https://github.com/alex-example">github.com/alex-example</a></span></p>\n</header>\n<p>Dear Acme team, I am applying for the Senior Backend Engineer role. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. I build efficient financial APIs. </p>\n<p>At Acme Bank I cut payment latency by 40% across 12 services &amp; kept 99.99% availability &lt;always&gt;.</p>\n<p>Best regards,<br>Alex &lt;Example&gt;<br>+34 600 000 000</p>\n</body>\n</html>'
