# Writing-task scoring overview: 2022–2026

**Status:** Decision recorded — use the shared recent practice rubric for all official Task 10 prompts.

This overview compares the 11 available A8 Task 10 prompt/guide pairs from 2022–2026. It is intended to support the decision about how the workshop should score historic prompts; it does not replace the official source files in `W:\Users\Felvi\assets\text\`.

## Similarities

- Every year has writing tasks that can be practiced with the original prompt and its matching Task 10 marking guide.
- The prompts are different, but the recent guide families broadly assess task fulfillment/content, organization, language or style, spelling, and presentation.
- The official requirements are task-specific: the number and balance of arguments, whether the learner chooses a position, whether personal experience is required, and the requested length can change.
- Presentation or handwriting cannot be judged from a typed draft. The tested workshop correctly marks that dimension as unassessable rather than inferring it.
- A practice evaluation remains formative, not an official entrance-exam result.

## Differences by year and variant

| Year | Variant | Prompt topic and format | Distinct requirement or training emphasis |
|---:|---:|---|---|
| 2022 | 1 | Whether printed textbooks are still needed in upper grades | Weigh the role of printed learning materials. |
| 2022 | 2 | Group work versus individual schoolwork | Compare two ways of working; develop reasons relevant to school. |
| 2022 | 3 | School events commemorating national holidays | The task includes a personal-experience requirement. |
| 2023 | 1 | “A múzeumoknak vége?” — museums versus learning about the world through the internet | The configured prompt extraction asks for a 10–12-sentence text and three arguments. The range is shown as task guidance, not used as an automatic score cutoff. |
| 2023 | 2 | “Versenyezni jó?” — whether competition is good | Opinion supported by three arguments in 10–12 sentences. |
| 2024 | 1 | Whether the class trip is important | Support the position with arguments and personal experience. |
| 2024 | 2 | Online/phone/computer conversations versus face-to-face meetings | Compare communication modes; do not assume the learner has access to every device or platform. |
| 2025 | 1 | Growing up with siblings versus as an only child | Compare family situations without assuming either experience is universal. |
| 2025 | 2 | Camp versus family holiday | Choose a position, give at least three arguments, include personal experience, and write 10–12 sentences. |
| 2026 | 1 | Subtitled/original-language films versus dubbing | Give two arguments for and against and include personal experience in 10–12 sentences. |
| 2026 | 2 | Traditional board games versus online games | Give two arguments for each type and include personal experience in 10–12 sentences. |

The table shows why the same generic essay instructions cannot be copied to every task. Even closely related comparison prompts differ in the required number of arguments, stance, experience, and length.

## What the tested scoring experience establishes

The in-app reference task, `A8_2026_2`, uses this 10-point guide:

| Criterion | Maximum | Typed-text treatment |
|---|---:|---|
| Content / task fulfillment | 3 | Assessable |
| Structure | 3 | Assessable |
| Style and word choice | 1 | Assessable |
| Spelling | 2 | Assessable |
| Appearance | 1 | Not assessable from typed text |

The learner-facing maximum is therefore 9 assessable points for typed text. This is the scoring experience already tried in the app and the strongest concrete basis for a consistent practice rubric.

All 11 recent guides use the same five criteria and weights shown above: **3+3+1+2+1 = 10 official points**, with **9 points assessable from typed text**. The matching `_ut.txt` files confirm this for every 2022–2026 variant; the previous concern about incompatible recent score denominators is resolved. What changes from task to task is how the guide defines successful content and task fulfillment, not the recent point scale.

## Selected approach

Use the recent **3+3+1+2+1** rubric for every official Task 10 prompt, including older exams. Keep appearance unassessable from typed work, and use each task's own prompt and guide for content requirements and accepted alternatives. Ignore historical point bands when assigning practice scores. This gives learners one consistent scoring experience; scores for older prompts are modern practice scores, not reconstructions of historical exam totals.

The alternative—preserving older official point scales for pre-2022 prompts—was not selected. The 2005–2021 source guides remain useful for prompt-specific expectations and acceptable answers, but their older point scales do not determine the learner-facing score.

## Source notes

- The task/topic index and prior validation notes are in [the writing-task user story](./user-story/user-story-writing-task-training.md).
- The verified in-app guide is loaded by [writing_tasks.py](../src/felvi_games/writing_tasks.py).
- Source pairs for this comparison: `A8_2022_1`–`A8_2022_3`, `A8_2023_1`–`A8_2023_2`, `A8_2024_1`–`A8_2024_2`, `A8_2025_1`–`A8_2025_2`, and `A8_2026_1`–`A8_2026_2`, each with matching `_fl.txt` and `_ut.txt` files.
- The five criterion-weight locations in those guides are:
  - 2022: `_ut.txt` lines 179, 203, 213, 215, 229 (`A8_2022_1`); 180, 203, 213, 215, 229 (`A8_2022_2`); 138, 158, 168, 170, 184 (`A8_2022_3`).
  - 2023: lines 157, 179, 196, 215, 251 (`A8_2023_1`); 175, 208, 222, 229, 275 (`A8_2023_2`).
  - 2024: lines 166, 186, 210, 217, 262 (`A8_2024_1`); 167, 200, 214, 221, 267 (`A8_2024_2`).
  - 2025: lines 152, 176, 189, 206, 241 (`A8_2025_1`); 153, 178, 202, 209, 244 (`A8_2025_2`).
  - 2026: lines 166, 210, 225, 233, 277 (`A8_2026_1`); 154, 200, 215, 223, 268 (`A8_2026_2`).
