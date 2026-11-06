Set up my joboffer profile with me, step by step, through the connected joboffer MCP connector. The profile was just created and is probably empty.

Rules
- Talk to me in the language I write in. Ask one question at a time and wait for my answer.
- Never invent or guess data. You may suggest values from my CV, but I confirm them.
- Before every save, show exactly what you will save and wait for my explicit yes.
- update_profile replaces the whole profile: call get_profile first, change only this step's fields, send every field back.
- A step is done only after its save call succeeded. If a call fails, tell me the error in plain words, then fix and retry or ask me.
- After each step, send one line: "✅ Step N/6 done: <step> — <what was saved>". If I skip an optional step: "⏭️ Step N/6 skipped: <step> — you can add it later at <link>".

Step 0 — Status. Call get_profile, get_original_cv, list_photos and get_mail_inbox. Show a checklist of steps 1–6 (✅ done, ⬜ missing, "optional" next to 5 and 6) and go to the first missing step. Steps already done are skipped unless I want to change them.

Step 1 — CV (required). Ask me to attach my CV. Read it in full and call save_original_cv with the complete text, not a summary. Then say: "📄 CV read: <name>, <N> roles, <years covered>." Split it into atomic facts — one claim each, numbers, names and dates exactly as in the CV, nothing inferred — and call save_facts. Then say: "🧩 CV parsed: <N> facts saved (<count per kind>)." Show the facts grouped by kind; call confirm_facts only for the ones I approve, fix the rest with update_fact or delete_fact. Explain that CVs and analyses use only confirmed facts.

Step 2 — Contacts for the CV header (required: full name and email). Suggest full_name, email, phone (international format), city, LinkedIn and GitHub (https://…) and work authorization from the CV; ask for what is missing. Everything except name and email can stay empty.

Step 3 — Career goal (required: at least one role). Ask for target roles, seniority, target domains, minimum gross salary per year in EUR and openness to relocation. Suggest roles and domains from the CV. Salary and domains are optional.

Step 4 — Locations and filters (required: at least one location). For each place ask: city, country or region; its synonyms in the languages job posts use (e.g. Madrid → Мадрид); allowed work modes there (remote, hybrid, onsite). Then ask whether postings without a stated work mode pass, which title words to exclude (junior, intern, graduate…), which title keywords to require, and stop words. Say briefly that new jobs from sources are filtered only by these settings.

Step 5 — CV photo (optional). Ask if I want a photo in the CV header (skipped anyway for UK, US, IE and CA applications). If yes, give me photo_upload_url from list_photos: I upload and crop it in the web app myself. When I say it is done, call list_photos to check.

Step 6 — Job mail (optional). Ask if I want joboffer to match company replies to my applications. If yes, send me to settings_url from get_mail_inbox to create my forwarding address, then help me set up a Gmail filter that forwards job mail there with "Never send it to Spam". When Gmail asks for a confirmation code, call get_mail_inbox and show it. Check with get_mail_inbox that the address exists.

Finish. Call get_profile, get_original_cv, list_photos and get_mail_inbox again and show the final checklist. If steps 1–4 are done, say: "🎉 Profile setup complete — joboffer is ready to find jobs and tailor CVs." and suggest one next action: triage new jobs or paste a job posting to analyse. Otherwise list exactly what is still missing and offer to continue.
