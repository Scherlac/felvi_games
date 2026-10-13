# User Story & Product Evaluation: Writing-Task Practice

**ID:** US-WRITING-001  
**Epic:** Exam Preparation & Writing Skills  
**Priority:** P1  
**Status:** Draft — validated against representative exam samples; broader review and educator validation remain

---

## User Story

As a learner preparing for the Hungarian secondary-school entrance exam,  
I want a supportive tutor chat that helps me plan, write, and revise compositions at my own pace and gives feedback against the appropriate review guide,  
so that I can improve my argumentation, organization, language use, and spelling before exam day.

As a learner,  
I want my tutor session, draft, feedback, and elapsed practice time saved for later review,  
so that I can see how my writing and confidence develop over time.

As a parent or teacher,  
I want to review a learner's saved tutor sessions and see which parts of the writing rubric the learner is improving,  
so that I can support the learner without relying on an unexplained AI score.

---

## Exam Evidence and Requirement Validation

The review began with the 8th-grade Hungarian language paper **MNy2, 3 February 2026**, Task 10 and its marking guide (`A8_2026_2_fl.txt`, `A8_2026_2_ut.txt`). A broader keyword scan of available `A8_*_fl.txt` files returned writing-related matches in 43 files. Representative task/guide pairs across different years and writing genres were then checked directly. This supports the need for writing practice, but is not an exhaustive manual audit of every exam file.

The checked files are in `W:\Users\Felvi\assets\text\`. Use the named task and guide item below to verify each requirement in the original text:

| Exam source | Task 10 prompt and guide evidence | Requirement validated |
|---|---|---|
| `A8_2026_2_fl.txt`, `A8_2026_2_ut.txt` — MNy2, 2026 | Task 10 asks for a comparison of traditional board games and online games: 10–12 sentences, two arguments for each, and a personal experience. The cover advises spending at least 10–15 minutes on Task 10. Guide Item 10 scores content, structure, style, spelling, and appearance. | The initial reference task; explicit argument counts, personal experience, sentence and time guidance, full rubric. |
| `A8_2026_1_fl.txt`, `A8_2026_1_ut.txt` — MNy1, 2026 | Task 10 asks for two arguments both for and against subtitled films, 10–12 sentences, and a personal experience. Guide Item 10 uses the same 3+3+1+2+1 point dimensions and says score must not depend on the learner's opinion. | Same recent rubric structure can be reused as a rubric template, but task-specific evidence and constraints must differ. |
| `A8_2025_2_fl.txt`, `A8_2025_2_ut.txt` — MNy2, 2025 | Task 10 asks the learner to choose between camp and family holiday, support the position with at least three arguments, and refer to personal experience in 10–12 sentences. Guide Item 10 uses content, structure, style, spelling, and appearance. | Similar length and dimensions do not mean every prompt asks for two-sided arguments; argument count and stance are prompt-specific. |
| `A8_2023_2_fl.txt`, `A8_2023_2_ut.txt` — MNy2, 2023 | Task 10, “Versenyezni jó?”, asks for an opinion supported by three arguments in 10–12 sentences. Guide Item 10 scores content, structure, style, spelling, and appearance. | Another opinion/argument task with a different evidence requirement. |
| `A8_2019_2_fl.txt`, `A8_2019_2_ut.txt` — MNy2, 2019 | Task 10, “Szóban vagy írásban?”, asks for 2–2 arguments for two positions and the learner's preferred position in 10–12 sentences. Guide Item 10 has explicit content bands, sentence thresholds, and opinion-neutral scoring. | Two-sided reasoning and stance are separate requirements; length thresholds affect score. |
| `A8_2013_1_fl.txt`, `A8_2013_1_ut.txt` — MNy1, 2013 | Task 10 asks for an opinion on internet/social-network use and at least two advantages and disadvantages of each, in 10–12 sentences. Guide Item 10 scores argument/content and organization. | Multi-part prompts may require pros and cons across more than one subject. |
| `A8_2009_1_fl.txt`, `A8_2009_1_ut.txt` — MNy1, 2009 | Task 10 asks for a 10–12-sentence story whose punchline is a supplied proverb. Guide Item 10 rewards originality, idea development, and integrating the proverb into the story. | Writing practice must include narrative writing, not only argumentative essays. |
| `A8_2006_1_fl.txt`, `A8_2006_1_ut.txt` — A–1, 2006 | Task 10 asks the learner to choose two of three functional-writing prompts and write 3–4 sentence texts. The guide scores genre suitability, cohesion, closure, style, spelling, language use, and (for an SMS) concision/relevance; criteria that cannot be judged from a short text are not scored. | Include short, genre-specific exercises and criterion applicability, not only full-length compositions. |
| `A8_2005_1_fl.txt`, `A8_2005_1_ut.txt` — A–1, 2005 | Task 10 asks for a 10–15-sentence text from one of two titles. Guide Item 10 separately covers content, coherence, style, language correctness, and spelling. | The long-form format is longstanding, while the scoring dimensions and exact rules vary by task/year. |

**Validated conclusion:** In the reviewed A8 Hungarian papers, Task 10 repeatedly requires writing, but “writing task” spans short functional texts, narratives, opinion pieces, and structured arguments. Recent 2025–2026 examples share a 10-point content/structure/style/spelling/appearance rubric, but prompts still differ in argument count, stance, personal-experience requirements, and length rules. Do not infer the exact task, length, genre, or scoring rules from the number 10 alone. Import and display the specific prompt and marking guide for each exam.

### Official marking dimensions in the 2026 MNy2 reference sample

| Dimension | Maximum | What the guide assesses |
|---|---:|---|
| Content | 3 | Relevance and development of ideas, personal experience, arguments for both types of game, and length. |
| Structure | 3 | A complete composition, identifiable introduction/body/conclusion, logical and proportionate organization, and length. |
| Style and vocabulary | 1 | Topic-appropriate, standard Hungarian, rich vocabulary, and correct language use. |
| Spelling | 2 | Hungarian spelling and punctuation, with different thresholds for ordinary and serious errors; the guide also ties scores to minimum length. |
| Appearance / handwriting | 1 | Legibility, clear corrections and letter/diacritic forms, neat layout, and staying within the writing area. |
| **Total** | **10** | Guide Item 10 defines separate criteria and sentence-count cutoffs. |

The full marking guide must be represented as task-specific structured rubric rules, not replaced by a generic “good writing” judgement. For the 2026 MNy2 example, preserve the content bands for 10, 8–9, 5–7, and fewer than 5 sentences; the global under-four-sentence rule; the title exclusion; the handwriting criterion; and Hungarian-specific spelling distinctions. Other source tasks may require different bands or criteria.

---

## Current Project Evaluation

### Existing foundations

- The data model already defines a `fogalmazas` task type and includes maximum points, a text-form partial-scoring rule, and evaluator notes.
- The quiz accepts open-text answers, and the general AI evaluator can return a score within a maximum-point range.
- The quiz already presents task explanations and feedback after an answer.
- The project has a separate teacher analytics chat in [teacher_chainlit_app.py](../../src/felvi_games/teacher_chainlit_app.py), supported by [teacher_chat.py](../../src/felvi_games/teacher_chat.py) and [teacher_agent_tools.py](../../src/felvi_games/teacher_agent_tools.py). It analyzes a selected learner's attempts and suggests training; it is not a learner-facing writing tutor.

### Gaps blocking end-to-end writing practice

- **Ingestion excludes the target task:** the system prompt in [pdf_parser.py](../../src/felvi_games/pdf_parser.py) explicitly says not to generate composition/essay tasks without a short, unambiguous correct answer. The sample Task 10 is therefore omitted from the normal parsed practice set.
- **The grader is generic, not rubric-structured:** it returns one score and short feedback. It does not return independently scored content, structure, style, and spelling criteria with evidence from the learner's own writing.
- **The normal answer field is not a writing workspace:** the shared text area is configured at 80 pixels high and the flow is designed around submitting one answer, not composing and revising a 10–12 sentence text.
- **There is no writing-specific practice loop in the documented product flow:** the README describes question/answer quiz practice, not planning, drafting, rubric-based revision, or exam-mode writing practice.
- **Existing chat serves a different user and goal:** the teacher analytics chat is for adult review of learner data; it does not coach a learner turn by turn through a writing exercise or preserve learner writing-tutor sessions for later review.
- **One official point is not assessable from typed text:** handwriting legibility and page layout cannot fairly be scored in the current text-only answer flow. The app must not silently assign or imply this point.
- **Difficulty metadata is not an adaptive writing path:** tasks have a general difficulty value, but the current task picker prioritizes least-attempted tasks; it does not advance a learner through writing skills based on rubric mastery or confidence.
- **No criterion-level mastery is stored:** the game state tracks overall points, streak, and solved task IDs, not progress in planning, paragraph structure, arguments, spelling, or other writing skills.

The existing `FOGALMAZAS` type and task scoring fields are in [models.py](../../src/felvi_games/models.py). The selection and answer flows in [app.py](../../src/felvi_games/app.py) reuse general quiz behavior; they do not currently implement the staged writing path proposed here.

**Evaluation:** The project has reusable primitives for task types, open text, task difficulty, partial credit, attempt history, and AI feedback, but it does not currently provide writing practice end to end. The ingestion exclusion is the immediate functional blocker; rubric-aware teaching, focused skill drills, and learner progress by criterion are the main product gaps. A dedicated writing mode is feasible as an extension of the existing session and persistence infrastructure, but its progression and scoring need new writing-specific behavior.

---

## Product Requirements

### 1. Preserve writing tasks during exam import (`WR-01`)

- The importer must recognize a long-form writing task and retain its complete prompt and associated marking guide instead of dropping it for lacking one short correct answer.
- Store the rubric as distinct criteria, score bands, maximum points, sentence thresholds, and applicable exceptions. Keep the original source text available for verification.
- Do not require a single canonical essay or a fixed list of accepted sentences. Many different compositions can meet the requirements.
- Keep exam year, variant, grade, subject, task number, and source provenance attached to the practice task.
- Represent genre and requirements explicitly (for example: narrative, argument/opinion, picture-based composition, or functional writing; required stance, argument count, personal example, length, and rubric).
- Do not assume Task 10 is a composition based on position alone. Review the task and guide for each imported paper, and never apply one year's rubric to another task without validation.

### 2. Provide a gradual, selectable writing game (`WR-02`)

The proposed game mode is **Fogalmazásműhely** (Writing Workshop). It should build from manageable subskills toward an independent exam composition, while allowing the learner to practise only one aspect when that is what they need.

| Stage | Example activity | Scaffolding |
|---|---|---|
| 1. Understand the prompt | Identify the topic, genre, required viewpoint, number of arguments, personal-example requirement, and length. | Checklist and examples; no long composition required. |
| 2. Build a relevant idea | Choose or write one on-topic claim; distinguish a reason from an example. | Sentence starters and optional hints. |
| 3. Practise a single skill | Write one argument, personal example, opening, transition, or conclusion; correct a sentence or spelling pattern. | Focus on the selected criterion; do not grade unrelated criteria as if they were the exercise goal. |
| 4. Build a paragraph | Arrange or write a main idea, supporting reason/example, and link to the topic. | Outline, ordering cards, then free writing. |
| 5. Connect the composition | Plan and write an introduction, body, and conclusion; practise coherence and paragraph transitions. | A visible structure plan, gradually reduced. |
| 6. Combine skills | Write a short composition, then increase toward the source task's required length and constraints. | Optional outline and one-step feedback; prompts fade as the learner succeeds. |
| 7. Exam simulation | Complete the authentic task under its stated time and rubric conditions. | No hints during the attempt; feedback appears after submission. |

The learner can select a **focus practice** at any stage: prompt understanding, idea relevance, arguments/reasons, examples or personal experience, introduction, body paragraphs, conclusion, coherence/transitions, sentence craft/vocabulary, spelling/punctuation, or integrated timed writing. The game can recommend a focus from past rubric results, but must not force a strictly linear route or lock the learner out of other skills.

Progression should use demonstrated performance over repeated tries together with the learner's own confidence check, rather than advancing on one AI score. A possible starting rule is to recommend the next stage after two successful attempts at the current skill and a positive learner confidence rating; this threshold is a hypothesis to validate with educators, not an exam rule. Learners can retry, choose another focus, or ask for support at any time.

Progress is primarily shown as growth by writing skill and independent performance. Medals can be optional reinforcement, not the main measure of success; this aligns with [progress_report.md](../progress_report.md), which recommends foregrounding mastery and weak-spot recovery rather than rewards.

### 3. Support both guided practice and exam simulation (`WR-03`)

- Guided practice helps the learner identify the prompt's requirements, brainstorm arguments, plan an introduction/body/conclusion, draft, and revise.
- Exam simulation presents the authentic prompt without pre-answer scaffolding and withholds evaluation feedback until the learner submits.
- Show and record elapsed practice time in both guided practice and exam simulation. Use the source exam's recommended time as guidance where available; the timer is a visible learning aid, not a time limit.
- Never auto-submit, disable writing, or discard work because of elapsed time. The learner decides when to finish and submit.
- Let the learner pause and resume a session; record elapsed active practice time across pauses and preserve the session state.
- Show the source task's actual length target and required elements before starting. Count sentences as an aid, exclude a title when the source guide says to, and let the learner correct a count when punctuation or abbreviations make automatic counting uncertain.
- Keep draft editing simple and suitable for a child writing a full composition. Allow the learner to revise and submit again in guided practice.

### 4. Provide a supportive tutor chat (`WR-04`)

- The chat follows the learner's selected stage and focus skill: understand the prompt, build an idea, practise one skill, build a paragraph, connect a composition, or complete an exam simulation.
- Use a supportive, age-appropriate Hungarian tutor voice. Ask one manageable coaching question at a time, acknowledge effort, and let the learner request a hint, example, simpler explanation, or different focus.
- Help the learner discover and express their own ideas. Do not write or silently replace the learner's complete composition. Any short example must be clearly labelled as an example and must not be counted as learner-authored work.
- Ground coaching and final review in the selected task's prompt, constraints, and review guide. Keep coaching open-ended where the task allows multiple valid answers; do not invent official rules.
- The tutor may help check a plan or partial draft during guided practice. For exam simulation, do not provide hints or evaluate the draft until the learner submits.
- When the learner asks for a score, distinguish formative feedback from official exam scoring and explain uncertainty; route ambiguous cases to adult review where available.

### 5. Give formative, criterion-based feedback (`WR-05`)

- Evaluate an authentic exam task against its imported official marking guide. For a proposed/generated practice task, provide a separate, clearly labelled **practice review guide**; do not represent it as an official solution guide.
- Extend each proposed practice task with a structured review guide before it is offered for scoring. Define applicable criteria, score bands or feedback levels, task-specific requirements, evidence expected, and example acceptable approaches. Educator review is required before claiming alignment to exam standards.
- Return a score or progress judgement and a short explanation for each applicable criterion, plus one or two actionable next steps.
- Show what in the composition supports a judgement (for example, identify the two distinct arguments for each side and the personal-experience reference). Do not rely on keyword matching alone.
- Distinguish required conditions from quality judgements. Be tolerant of different valid arguments, wording, and viewpoints; never award or deduct points based on whether the learner agrees with a preferred opinion.
- Explain spelling corrections in age-appropriate Hungarian. Apply the source guide's distinction between error types and severity rather than treating every spelling issue equally.
- Do not write the learner's complete composition for them or silently replace their words. Suggestions should help the child develop and revise their own ideas.
- If the model is uncertain, make the uncertainty visible and invite teacher/parent review instead of presenting a confident, exact score.

### 6. Handle official scoring transparently (`WR-06`)

- The score must be the sum of valid criterion scores and never exceed the applicable maximum.
- Apply the source task's actual minimum-length and score-band rules. In the 2026 MNy2 reference sample, fewer than four sentences results in zero for every item; do not assume that sentence rule applies identically to every source task.
- For a typed submission under the 2026 10-point rubric, score the four text-assessable criteria only (maximum 9 points) and label appearance/handwriting **not assessed**. Do not count that criterion as zero or imply that the typed score is the complete official 10-point exam score. Follow a different source rubric when its criteria differ.
- If handwritten-image submission is added later, handwriting/appearance should remain subject to an explicit, validated review method; do not assume that text extraction can assess legibility or page layout.
- Keep practice feedback formative. Clearly state that an AI practice score is an estimate, not an official exam result.

### 7. Preserve and review tutor sessions (`WR-07`)

- Save each completed (and explicitly paused) writing tutor session so the learner can reopen it later for review.
- Preserve the prompt text and source/provenance, official or practice review-guide version, selected focus skill and scaffold level, learner-authored drafts/submissions, tutor and learner chat turns, criterion feedback, confidence check-ins, and elapsed active practice time.
- Keep draft revisions distinguishable; do not overwrite earlier learner drafts when a new revision is submitted.
- Let the learner review prior conversation, draft revisions, and feedback, then start a new attempt or continue a paused session without confusing it with a new result.
- Let an authorized parent/teacher review saved sessions and see changes by review criterion and focus skill, not only total points.
- Define access control, draft visibility, deletion, and retention for child users before enabling long-term session history.
- Let learners privately rate confidence in the practised skill before/after a session; treat this as a self-report alongside demonstrated writing, not as a substitute for it.
- End a practice attempt with a manageable next step (for example, add a second distinct argument or improve the conclusion), not a discouraging judgement.

### 8. Add main-page entry points and reuse the current architecture (`WR-08`)

- Add a clear main-page button to start the **Fogalmazásműhely** tutor game mode.
- Add a main-page entry to review saved writing tutor sessions; only offer continue/resume where a session was explicitly paused and is still valid.
- From the game entry flow, let the learner choose an official exam task or an educator-reviewed practice prompt, then choose guided or simulation practice and a focus skill where applicable.
- Reuse the existing learner, session, attempt-history, chat, and scoring infrastructure where suitable; the existing teacher analytics chat is not itself the learner's tutor.
- Add writing-specific task/step metadata for genre, focus skill, scaffold level, prompt source, rubric version, and criterion evidence.
- Persist tutor session messages and writing-specific session state with references to the learner, task, and review guide.
- Add learner progress by focus skill and rubric criterion; do not treat the existing general difficulty stars or least-attempted task selection as mastery-based adaptation.
- Extend the parser so verified writing tasks are retained. Keep their long prompt and rubric structured separately from the short-answer evaluation path.
- Provide an explicit writing workspace with comfortable long-text entry, draft/revision state, elapsed timer, tutor chat, and criterion-level results.

---

## Acceptance Criteria

- [ ] Parsing the reviewed exam sample creates a writing-practice task for Task 10 instead of skipping it.
- [ ] Every imported writing task retains its own source prompt, genre, constraints, rubric, exam/variant provenance, and rubric version; requirements are not copied from another year or variant.
- [ ] The reviewed 2026 MNy2 task retains its actual requirements: 10–12 sentences, two arguments for each game type, and a personal-experience reference.
- [ ] The learner can practise an individual focus skill (such as a claim, paragraph structure, examples, conclusion, or spelling) without being scored on unrelated full-essay criteria.
- [ ] The learner can progress from short/supported work toward a complete composition, while choosing a focus, repeating a stage, or entering integrated practice without a forced linear lock.
- [ ] Scaffolding can be reduced as the learner succeeds; progression recommendations use repeated evidence and the learner's confidence check, not one AI score alone.
- [ ] Available exercise formats include the reviewed short functional-writing and narrative examples as well as argumentative compositions; the task's genre determines the exercise and assessment.
- [ ] A learner can complete guided tutor-chat practice and an exam simulation; the simulation does not reveal feedback before submission.
- [ ] The tutor follows the selected practice stage and review guide, uses supportive age-appropriate Hungarian, and asks manageable coaching questions without writing the learner's complete answer.
- [ ] When the learner asks for an example, it is clearly distinguished from the learner's own draft and is not included in the learner's score.
- [ ] The app's main page has an entry button to start Fogalmazásműhely and an entry to review saved writing sessions.
- [ ] A visible elapsed-time display starts with the session and records active practice time. The source task's suggested duration may be shown as guidance but does not stop, submit, or restrict the learner.
- [ ] Pausing and resuming preserves the draft and chat; paused time is not counted as active practice time.
- [ ] A completed or explicitly paused tutor session can be reopened later with its transcript, original prompt/source, review-guide version, learner drafts and revisions, feedback, confidence check-ins, and recorded elapsed practice time intact.
- [ ] Saved sessions can be distinguished as official-exam or practice-task sessions, and a proposed task's review guide is visibly labelled as practice rather than official.
- [ ] The learner sees the actual source task's sentence target; a title is excluded only when the relevant marking guide says so, and the count can be corrected if automatic segmentation is ambiguous.
- [ ] After submission, the learner sees feedback for each applicable criterion and an accurate total for the selected guide. For the 2026 MNy2 reference task, typed work is scored out of 9 and appearance is clearly marked not assessed.
- [ ] A submission under four sentences receives zero for all rubric items on the 2026 MNy2 task; other tasks follow their own guide rather than inheriting this rule.
- [ ] Different valid arguments and either opinion about online or traditional games can receive full credit when all rubric requirements are met.
- [ ] A revision can be compared with the prior attempt by criterion, while preserving the learner's original text.
- [ ] Confidence self-ratings are visible as learner reflections and are not presented as proof of skill or used as a substitute for writing evidence.
- [ ] Feedback is age-appropriate, actionable, and does not present a generated replacement essay as the learner's work.
- [ ] Practice scores are labelled as AI estimates and uncertain judgements can be referred to an adult.

---

## Requirement-to-Source Traceability

Requirements below are product proposals grounded in the listed exam evidence. The exam documents validate the task variety and official scoring constraints; they do **not** prescribe the staged game or its advancement heuristic.

| Requirement | Exam evidence for reviewer |
|---|---|
| `WR-01` Keep each prompt and rubric task-specific | Compare Task 10 in `A8_2026_1_fl.txt` / Item 10 in `A8_2026_1_ut.txt` with `A8_2026_2_fl.txt` / `A8_2026_2_ut.txt`, and `A8_2025_2_fl.txt` / `A8_2025_2_ut.txt`: same broad writing task family, but different topic constraints and argument requirements. |
| `WR-02` Include genre and skill-focused drills | Short functional texts: `A8_2006_1_fl.txt`, Task 10 / `A8_2006_1_ut.txt`, Item 10. Narrative: `A8_2009_1_fl.txt`, Task 10 / `A8_2009_1_ut.txt`, Item 10. Argument/opinion: `A8_2019_2_fl.txt`, `A8_2023_2_fl.txt`, `A8_2025_2_fl.txt`, and `A8_2026_1_fl.txt`, each Task 10. The drills and stages are a teaching design derived from this variety, not a stated exam rule. |
| `WR-03` Preserve authentic constraints in simulation | `A8_2026_2_fl.txt`, cover instructions and Task 10; compare with Task 10 in `A8_2026_1_fl.txt` and `A8_2025_2_fl.txt`. Time guidance is specific to the 2026_2 cover and must not be applied to every exam without checking its instructions. |
| `WR-04` Provide supportive tutor chat | Exam documents establish task constraints but do not require a chat-based tutor; the one-question-at-a-time coaching workflow is a product design proposal. Its coaching must remain faithful to the selected task/guide, for example `A8_2026_2_fl.txt` Task 10 and `A8_2026_2_ut.txt` Item 10. |
| `WR-05` Give criterion-specific, opinion-neutral feedback | `A8_2026_2_ut.txt`, Item 10(a)–(e), including content/structure/style/spelling/appearance and the note that score must not depend on opinion. Also see `A8_2026_1_ut.txt`, Item 10(a)–(e), and `A8_2025_2_ut.txt`, Item 10(a)–(e). |
| `WR-06` Respect rubric-specific scores and sentence rules | `A8_2026_2_ut.txt`, Item 10(a)–(e), and compare sentence/score bands with `A8_2019_2_ut.txt`, Item 10(a)–(e), and `A8_2006_1_ut.txt`, Item 10(a)–(m). These rules differ and must remain attached to their source task. |
| `WR-07` Preserve and review tutor sessions | Official guides above define evidence worth reviewing; saving chat turns, revisions, and elapsed time is a product requirement rather than an exam rule. Privacy and retention need a child-user policy. |
| `WR-08` Add main-page entry points and reuse existing behavior | [app.py](../../src/felvi_games/app.py), [teacher_chainlit_app.py](../../src/felvi_games/teacher_chainlit_app.py), [teacher_chat.py](../../src/felvi_games/teacher_chat.py), [pdf_parser.py](../../src/felvi_games/pdf_parser.py), and [models.py](../../src/felvi_games/models.py). The existing teacher analytics chat is a reuse reference, not the learner tutor itself. |

---

## Evaluation and Validation Plan

The rubric should be validated before AI scores are used as more than formative guidance. Create a permissioned benchmark spanning the reviewed genres (short functional writing, narrative, and argumentative composition) and include strong, partial, off-topic, short, and borderline examples. Have Hungarian-language educators score each response with its own official guide, then compare the product's criterion-level results and feedback with those human ratings.

### Required test cases

- 3 versus 4 sentences, and 4 versus 5 sentences;
- 9 versus 10 sentences, with a title that must not count;
- two distinct arguments for each game type versus a missing, repeated, or unclear argument;
- explicit personal experience versus a generic claim;
- on-topic and off-topic writing;
- a valid composition expressing either opinion;
- coherent and incoherent paragraph structure;
- Hungarian spelling examples from the guide's minor and serious error categories;
- typed work where appearance must remain not assessed;
- punctuation, abbreviations, and other cases where sentence counting is ambiguous.
- a short functional text where the correct genre and task-appropriate criteria matter more than essay-length structure;
- a narrative that integrates a supplied proverb or other required element;
- a learner selecting one focus skill, repeating it, and later completing an integrated task;
- progression when skill evidence is mixed, confidence is low, or confidence is high without matching writing evidence.
- tutor turns that coach rather than provide a complete learner answer, and clearly labelled short examples that are not mistaken for learner work;
- a paused session restored with the correct transcript, drafts, feedback, rubric version, and elapsed active time;
- a session that passes the suggested duration without auto-submitting, disabling input, or losing any work;
- both official-exam and generated practice tasks, with official marking guides kept separate from practice review guides;
- main-page start and saved-session review entry points that route to the correct learner's writing sessions.

### Proposed initial quality gates

These are recommendations for educator review, not measured capabilities or results:

- 100% of imported benchmark tasks preserve the prompt and rubric criteria.
- 100% of scoring cases respect the selected source rubric's point bounds and explicit sentence rules, including the 2026 MNy2 under-four-sentence rule.
- On an educator-scored benchmark, at least 90% of total typed scores are within one point of the educator's total on tasks whose text-assessable maximum is 9, and at least 85% of individual criterion scores match the educator's score or differ by no more than one point. Measure other rubrics against their own assessable maxima and report each genre separately.
- No benchmark response loses credit solely because of the learner's opinion or a valid paraphrase.
- Learners can reach integrated writing practice by retrying or selecting their route; a single low score or confidence rating does not block access.
- An educator reviews examples of both false praise and overly harsh feedback before broader release.

These gates need a sufficiently varied, permissioned sample and educator agreement on how ambiguous rubric language should be interpreted. Report results by criterion and genre; a passing total-score average must not hide weak spelling, structure, or short-form task evaluation. The 43-file keyword scan is not a substitute for completing the broader exam-corpus audit.

---

## Out of Scope for the First Release

- Claiming that one reviewed exam proves all years, grades, or final tasks use the same writing format.
- Official examination scoring, high-stakes placement decisions, or replacing a teacher's judgement.
- Automated scoring of handwriting appearance from typed text.
- Automatically generating a complete answer for the learner.
- Applying the 2026 MNy2 rubric unchanged to other prompts or exam levels.

---

## Open Decisions

1. Should the first release cover only typed composition practice, or also accept handwriting images for adult review?
2. Which educator-approved sample set and scoring guidance should calibrate the AI evaluator and progression thresholds?
3. Which remaining years, variants, and grades should be manually reviewed to complete the exam-corpus inventory?
4. Should initial focus practice cover argumentation first, or launch with narrative and functional-writing tasks as well?
5. Local-prototype decision: retain writing sessions without automatic expiry. Before production or shared/remote use, define deletion, access controls, parent/teacher visibility, and applicable privacy safeguards.
6. Should the tutor chat be native Streamlit (`st.chat_message`/`st.chat_input`, recommended: same entry point as the main-page buttons, shared session state) or a separate Chainlit app like the teacher chat?
7. Who reviews and approves generated "practice review guides" before learners see them (educator sign-off flag)?

---

## Task 10 Topic Index for External Research

This index summarizes the available Hungarian-language `A8` paper files; the variant number is the middle number in each filename. It is a discovery aid, not a substitute for the source paper. Where the extracted text does not describe an image, the theme is marked as unknown rather than guessed. The corresponding marking guide is the same filename ending in `_ut.txt`.

| Exam year | Variant / source file | Main Task 10 theme |
|---:|---|---|
| 2005 | 1 — `A8_2005_1_fl.txt` | Short titled composition; visible choices include “A jó szó orvosság” and “Meglepetés ért”. |
| 2005 | 2 — `A8_2005_2_fl.txt` | Short titled composition; visible choice “Ajándékozni jó” (giving gifts). |
| 2006 | 1 — `A8_2006_1_fl.txt` | Choose two short functional texts: greetings, an invitation, or a message to a teacher. |
| 2006 | 2 — `A8_2006_2_fl.txt` | Choose two short texts from several genres; one option argues that a younger sibling does not need a mobile phone. |
| 2006 | 3 — `A8_2006_3_fl.txt` | Choose two short texts from several genres; one option is a monologue about what the learner would like to eat for their birthday. |
| 2007 | 1 — `A8_2007_1_fl.txt` | Persuade a friend to read a recommended book. |
| 2007 | 2 — `A8_2007_2_fl.txt` | Whether the internet can replace books. |
| 2007 | 3 — `A8_2007_3_fl.txt` | Propose and justify criteria for a “World Book Award”. |
| 2008 | 1 — `A8_2008_1_fl.txt` | Picture-based composition; the extracted text does not identify the picture's theme. |
| 2008 | 2 — `A8_2008_2_fl.txt` | Picture-based composition; the extracted text does not identify the picture's theme. |
| 2009 | 1 — `A8_2009_1_fl.txt` | Story whose punchline is the proverb “Ha hallgattál volna, bölcs maradtál volna” (“If you had kept quiet, you would have remained wise”). |
| 2009 | 2 — `A8_2009_2_fl.txt` | Story whose lesson is the proverb “Kétszer ad, aki gyorsan ad” (“He gives twice who gives promptly”). |
| 2010 | 1 — `A8_2010_1_fl.txt` | Continue a story under the title “Eggyel többen” (“One more”). |
| 2010 | 2 — `A8_2010_2_fl.txt` | “Ahol nagyon szeretek lenni” (“Where I really like to be”): a favourite place. |
| 2010 | 3 — `A8_2010_3_fl.txt` | Composition incorporating the sentence “Nem gondoltam volna, hogy sikerülni fog” (“I didn't think I would succeed”). |
| 2011 | 1 — `A8_2011_1_fl.txt` | “A kor, amelyben szívesen élnék” (“The era I would like to live in”). |
| 2011 | 2 — `A8_2011_2_fl.txt` | Story using a supplied set of words and a phrase. |
| 2012 | 1 — `A8_2012_1_fl.txt` | “Kedvenc hősöm” (“My favourite hero”): describe a favourite film or book character. |
| 2012 | 2 — `A8_2012_2_fl.txt` | “Legemlékezetesebb ajándékom” (“My most memorable gift”). |
| 2013 | 1 — `A8_2013_1_fl.txt` | Internet and social-network use: evaluate the phenomenon and discuss advantages and disadvantages. |
| 2013 | 2 — `A8_2013_2_fl.txt` | Young people's attitudes toward reading; give arguments for both liking and disliking it. |
| 2014 | 1 — `A8_2014_1_fl.txt` | Whether the required school-reading list should be updated. |
| 2014 | 2 — `A8_2014_2_fl.txt` | “Film vagy könyv?” (“Film or book?”): whether a film adaptation can replace reading the book. |
| 2015 | 1 — `A8_2015_1_fl.txt` | Whether handwriting still needs to be learned and used in an increasingly digital world. |
| 2015 | 2 — `A8_2015_2_fl.txt` | Whether homework is necessary. |
| 2016 | 1 — `A8_2016_1_fl.txt` | Keeping animals in an apartment: arguments for and against. |
| 2016 | 2 — `A8_2016_2_fl.txt` | Propose a new school subject and justify the choice. |
| 2017 | 1 — `A8_2017_1_fl.txt` | Social-network use as a way of staying in contact: arguments for and against. |
| 2017 | 2 — `A8_2017_2_fl.txt` | How to spend school breaks: excursions, school camps, or family trips. |
| 2018 | 1 — `A8_2018_1_fl.txt` | Whether school uniforms should be compulsory. |
| 2018 | 2 — `A8_2018_2_fl.txt` | Whether talent competitions are a good way to demonstrate artistic ability. |
| 2019 | 1 — `A8_2019_1_fl.txt` | Whether it is better to be an adult or a child. |
| 2019 | 2 — `A8_2019_2_fl.txt` | “Szóban vagy írásban?” (“Orally or in writing?”): preferred way of answering school assessments. |
| 2020 | 1 — `A8_2020_1_fl.txt` | Going to the cinema versus watching films at home. |
| 2020 | 2 — `A8_2020_2_fl.txt` | Oral examination versus written test. |
| 2021 | 1 — `A8_2021_1_fl.txt` | In-person schooling versus distance learning. |
| 2021 | 2 — `A8_2021_2_fl.txt` | Team sports versus individual sports. |
| 2021 | 3 — `A8_2021_3_fl.txt` | Different school-year systems: a longer school year versus more frequent holidays. |
| 2022 | 1 — `A8_2022_1_fl.txt` | Whether printed textbooks are still needed in upper grades. |
| 2022 | 2 — `A8_2022_2_fl.txt` | Group work versus individual schoolwork. |
| 2022 | 3 — `A8_2022_3_fl.txt` | The value of school events commemorating national holidays; include a personal experience. |
| 2023 | 1 — `A8_2023_1_fl.txt` | “A múzeumoknak vége?” (“Are museums over?”): museums versus learning about distant worlds through the internet. |
| 2023 | 2 — `A8_2023_2_fl.txt` | “Versenyezni jó?” (“Is competing good?”). |
| 2024 | 1 — `A8_2024_1_fl.txt` | Whether the class trip is important; support the answer with arguments and personal experience. |
| 2024 | 2 — `A8_2024_2_fl.txt` | Online/phone/computer conversations versus face-to-face meetings. |
| 2025 | 1 — `A8_2025_1_fl.txt` | Growing up with siblings versus as an only child; compare family models. |
| 2025 | 2 — `A8_2025_2_fl.txt` | “Tábor vagy családi nyaralás?” (“Camp or family holiday?”). |
| 2026 | 1 — `A8_2026_1_fl.txt` | Subtitled/original-language films versus dubbing. |
| 2026 | 2 — `A8_2026_2_fl.txt` | Online games versus traditional board games. |

### Copy-ready request for an internet-connected RAG researcher

```text
Role: Research assistant studying Hungarian central secondary-school entrance-exam writing prompts.

Use the attached Task 10 topic index from the available A8 Hungarian-language papers (2005–2026). Research, using internet-connected retrieval, whether the topics or prompt formats show recurring patterns and whether credible sources explain how the topics are selected.

Research questions:
1. Group the topics into a transparent taxonomy (for example school/education, technology/media, books/culture, family/relationships, leisure/sport, personal narrative, and functional writing). Count theme occurrences by year and variant; explain ambiguous classifications.
2. Identify repeated or closely related themes, recurring contrasts (such as online/offline or individual/group), and gaps or rotations. Distinguish a genuinely repeated topic from a broad thematic resemblance.
3. Describe changes in task format over time: short functional writing, narrative, picture-based writing, and argument/opinion; note sentence limits, number of arguments, personal-experience requirements, and rubric similarities/differences only where the official papers or marking guides support them.
4. Search for official evidence about who selects these exam topics, the intended writing competencies, and the constraints used when designing prompts. If no reliable source explains topic selection, state that clearly.
5. Where useful, compare topics with contemporaneous curriculum themes, public discussion, or events. Do not infer that an event caused a prompt unless a reliable source supports that connection.
6. Give cautious, evidence-based hypotheses about possible topic-selection principles (for example familiarity to children, balanced opposing positions, accessibility, or rotation across domains), clearly separated from verified facts.
7. Recommend a practical topic-selection checklist for future practice prompts that encourages variety, age-appropriateness, fairness to learners with different experiences, and opportunities to demonstrate the writing skills in the official rubrics. Do not predict or claim to know a future official exam topic.

Source and evidence rules:
- Prioritize official Oktatási Hivatal exam papers, marking guides, curriculum documents, and official descriptions. Use secondary sources only for context.
- Cite every factual claim with a working URL, publisher/organization, publication date (when available), and the specific page/section or retrieved passage.
- Separate (A) directly verified facts, (B) interpretations supported by multiple sources, and (C) hypotheses/speculation. Assign a confidence level and explain important limitations.
- The supplied index is a local text-extraction summary, not a complete copy of the papers. The 2008 picture-based prompts cannot be classified from the extracted text alone; flag them as requiring visual review rather than guessing.
- Scope is the A8 Hungarian-language paper set represented in the index. Do not generalize to mathematics exams, other grades, or all Hungarian admission exams without additional evidence.

Return:
1. A concise executive summary.
2. A year/variant table with theme category, prompt format, recurring-pattern notes, source citations, and confidence.
3. A short list of verified topic-selection rules or an explicit statement that no such official rules were found.
4. A separate list of cautious hypotheses and evidence needed to test them.
5. The proposed topic-selection checklist and any important fairness/accessibility cautions.
Write in English, retaining Hungarian prompt titles where useful.
```

---

## Review of RAG-Proposed Practice Topics

The following ten topics came from an external RAG-generated proposal. They are candidate practice prompts for the Writing Workshop, **not official exam questions, verified predictions, or evidence of future-topic probability**. The cross-references below compare them with the local A8 Task 10 index.

| # | Candidate topic | Closest reviewed exam analogue | Planning decision / caution |
|---:|---|---|---|
| 1 | Digital versus printed textbooks | `A8_2022_1_fl.txt` (printed textbooks); also related to `A8_2015_1_fl.txt` (handwriting in a digital world). | Good practice candidate for comparison, reasons, and paragraph transitions. Treat as a related/repeated theme, not a novel topic. |
| 2 | School cafeteria choice versus healthy-only rules | No close match in the reviewed index. | Useful new school-life prompt. Keep the wording neutral and avoid body-shaming, health claims that need specialist knowledge, or assuming all learners buy food at school. |
| 3 | Group project versus individual work | Directly related to `A8_2022_2_fl.txt` (group versus individual schoolwork); `A8_2021_2_fl.txt` is only a looser structural analogy (team versus individual sports). | Strong focused-practice candidate for cooperation, responsibility, and contrast. Do not describe it as a new topic when comparing it with the 2022 paper. |
| 4 | Cash versus card or smartphone payment | No close match in the reviewed index. | Potentially useful everyday-reasoning prompt, but avoid assuming that a learner has a bank card, smartphone wallet, or personal spending money. A hypothetical scenario should be enough. |
| 5 | AI use in homework | Related to `A8_2015_2_fl.txt` (whether homework is necessary) and `A8_2015_1_fl.txt` (technology and handwriting), but AI use itself is a new angle. | Current-affairs practice candidate. Explain the scenario in the prompt so students need not have used AI. Accept different positions; assess reasons and prompt requirements, not a preferred view of AI. |
| 6 | Audiobooks versus conventional reading | Related to `A8_2007_2_fl.txt` (internet and books), `A8_2013_2_fl.txt` (attitudes toward reading), and `A8_2014_2_fl.txt` (film versus book). | Good comparison/contrast practice. Permit listening, reading, or accessibility-based perspectives without treating one mode as the only “real” reading experience. |
| 7 | Nature outing versus city leisure | Related to `A8_2017_2_fl.txt` (school-break activities) and `A8_2024_1_fl.txt` (class trips). | A reasonable choice-and-reasons task, but trips, museums, shopping, and entertainment may not be equally accessible. Do not require personal travel experience; hypothetical or observed examples should count. |
| 8 | Talent shows versus long-term practice | Related to `A8_2018_2_fl.txt` (talent competitions), but the proposed contrast with years of private practice is a new framing. | Useful for a higher-level argument drill. Allow nuance and avoid assuming that television exposure and sustained practice are mutually exclusive. |
| 9 | Traditional companion pet versus a lower-maintenance/exotic pet | Related to `A8_2016_1_fl.txt` (whether animals should be kept in apartments), but not the same comparison. | Use only as a hypothetical family decision. Do not assume the learner owns or has cared for a pet; keep animal-care claims accurate and non-prescriptive. |
| 10 | Fixed allowance versus money earned through chores or grades | No close match in the reviewed index. `A8_2012_2_fl.txt` is about a memorable gift and `A8_2019_1_fl.txt` compares childhood with adulthood; neither is a direct analogue. | Defer or substantially reframe: family income, allowance, chores, and grades can be sensitive or unequal. If retained, use a fictional scenario and never require personal financial disclosure. |

### Assessment of the RAG claims

- The local index supports the cautious observation that argumentative/opinion writing is a recurring Task 10 format in the sampled A8 papers from 2013 onward. It does **not** establish that every prompt requires balanced arguments on both sides: some ask for two arguments each way, while others ask for three arguments supporting the learner's chosen position.
- The RAG proposal's 10–12 sentence limit is a useful practice setting for recent examples, not a universal rule. Older Task 10s include 3–4 sentence functional writing, 10–15-sentence compositions, and narratives with specific constraints.
- “High probability” and “authenticity” are not supported by evidence in the supplied proposal. Do not label these ten topics as likely exam questions unless a separate, cited study can justify that claim. Use them as a varied practice bank.
- The recommendation to enforce an “objective, balanced tone” should not become a scoring rule. Official guides say scores must not depend on the learner's opinion, and task requirements vary. Grade the quality and completeness of the requested reasoning; do not reward a particular position or demand both sides unless the prompt asks for them.
- Claims that a topic is universally accessible need scrutiny. The proposed cashless-payment, outdoor/city-trip, pet, and allowance topics can assume unequal access or private experience. Use hypothetical cases, accept well-reasoned alternatives, and never require sensitive disclosures.

### Suggested use in the first topic bank

Use several kinds of prompts rather than ten near-identical two-sided essays:

1. Start with a close historical analogue, such as group versus individual schoolwork, for a controlled skill drill.
2. Pair it with a related but changed topic, such as audiobooks versus reading, to check transfer rather than memorization.
3. Add a new but low-assumption school scenario, such as cafeteria choices, after an educator reviews its wording.
4. Keep AI homework as an optional contemporary topic with a short, neutral scenario supplied to every learner.
5. Defer allowance as written, and offer nature/city, payment, and pet topics only with the fairness safeguards above.

Every generated candidate must be labelled **practice material**, tagged by genre and focus skill, and kept distinct from imported official exams. Use the source exam's exact rubric only when practising that exam; otherwise use a clearly labelled practice rubric that does not claim official scoring.

### Archived RAG proposal — original prompt wording preserved

The following archive preserves the proposed categories, thematic pivots, core binaries, Hungarian student prompt wording, and tutor blueprints so they can be reused and revised later. The proposed prompts are reproduced as supplied; they have **not** been edited into exam-ready prompts or educator-reviewed. They are practice candidates, not official Oktatási Hivatal wording.

#### Category A: School & Education

##### 1. A digitális versus hagyományos tankönyvek (*Digital vs. Traditional Textbooks*)

**Thematic Pivot:** Modern Technology vs. Traditional Formats (similar to the 2015 handwriting vs. typing and 2014 book vs. film prompts).

**The Core Binary:** Reading and learning from a physical, printed textbook versus studying from an interactive digital device or tablet.

**Student Prompt (Hungarian):**

> Egyre több iskolában merül fel a kérdés: váltsák-e fel a digitális tananyagok és táblagépek a hagyományos, nyomtatott tankönyveket? Fogalmazd meg a véleményedet a kérdésben! Írj egy rövid, összefüggő szöveget, amelyben mellette és ellene is felhozol érveket!

**Tutor Blueprint & Constraints:** Requires a 3-part structure (Intro, Body, Conclusion). Must explicitly list at least 2 advantages and 2 disadvantages (e.g., weight of schoolbags vs. screen fatigue/distraction). Limit: 10–12 sentences.

##### 2. Az iskolai büfék kínálata (*The School Cafeteria Selection*)

**Thematic Pivot:** Individual Choice vs. Institutional Rules (echoes the 2018 school uniform debate).

**The Core Binary:** Allowing students to buy whatever snacks they prefer versus restricting school cafeterias to strictly healthy, low-sugar options.

**Student Prompt (Hungarian):**

> Sokan úgy gondolják, hogy az iskolai büfékben csak egészséges ételeket és italokat szabadna árulni, míg mások szerint a diákoknak joguk van eldönteni, mit szeretnének tízóraira enni. Fejtsd ki a véleményedet ebben a témában!

**Tutor Blueprint & Constraints:** Tests structural comparison. The student must balance public health arguments against personal autonomy and student satisfaction. Limit: 10–12 sentences.

##### 3. Csoportos vagy egyéni projektmunka (*Group Project vs. Individual Work*)

**Thematic Pivot:** Individual vs. Group Dynamics (directly mirrors the structural contrast of the 2021 Team vs. Individual sports prompt).

**The Core Binary:** Preparing a graded school assignment alone versus collaborating in a group of 3-4 classmates.

**Student Prompt (Hungarian):**

> „Együtt könnyebb, vagy egyedül hatékonyabb?” Az iskolai feladatok során gyakran kell választani a csoportos projektmunka és az egyéni felkészülés között. Melyik munkaformát tartod hasznosabbnak? Érvelj mindkét lehetőség mellett és ellen!

**Tutor Blueprint & Constraints:** Focuses on interpersonal dynamics and task management. Grading matrix should check for precise vocabulary regarding cooperation and individual accountability. Limit: 10–12 sentences.

#### Category B: Technology & Media

##### 4. Készpénz vagy bankkártya/okostelefon? (*Cash vs. Card/Smartphone?*)

**Thematic Pivot:** Technological transition in daily life (similar to 2013 social networks and 2015 digital world prompts).

**The Core Binary:** Using physical paper money/coins versus utilizing digital bank cards or smartphone wallets for everyday teenage spending.

**Student Prompt (Hungarian):**

> Napjainkban egyre elterjedtebb a készpénzmentes fizetés. Egyesek szerint a zsebpénzt is célszerűbb bankkártyán vagy telefonos alkalmazásban tárolni, mások a fizikai pénz használatát tartják biztonságosabbnak egy diák számára. Érvelj mindkét álláspont mellett!

**Tutor Blueprint & Constraints:** Tests abstract financial/practical reasoning suitable for a 14-year-old. Must use at least 3 distinct arguments in total. Limit: 10–12 sentences.

##### 5. Mesterséges intelligencia a házi feladatban (*AI in Homework*)

**Thematic Pivot:** Emerging technology vs. Academic integrity (a highly realistic update to the 2015 "Is homework necessary?" prompt).

**The Core Binary:** Utilizing AI tools as an educational writing assistant versus banning them to protect independent, organic student learning.

**Student Prompt (Hungarian):**

> A modern technológia segítségével ma már pillanatok alatt generálhatunk szövegeket vagy megoldásokat a házi feladatokhoz. Segíti vagy inkább hátráltatja ez a diákok valódi tanulását? Fogalmazz meg érveket mindkét oldal mellett!

**Tutor Blueprint & Constraints:** High contemporary relevance. The prompt remains neutral. The grading rubric should closely monitor whether the student maintains an objective, balanced tone rather than a purely emotional one. Limit: 10–12 sentences.

#### Category C: Books, Culture & Leisure

##### 6. Hangoskönyv vagy hagyományos olvasás? (*Audiobooks vs. Traditional Reading*)

**Thematic Pivot:** Media Consumption Modes (maps neatly to the 2007, 2013, and 2014 reading-themed iterations).

**The Core Binary:** Listening to a literary work narrated via audio versus physically reading the text on a printed page.

**Student Prompt (Hungarian):**

> Sokan szívesebben hallgatnak hangoskönyveket utazás vagy pihenés közben, míg mások szerint a valódi olvasás élményét semmi sem pótolhatja. Hasonlítsd össze a két módszert, és hozz fel érveket mindkettő mellett!

**Tutor Blueprint & Constraints:** Requires precise comparative connectors (*ezzel szemben, másrészről, ugyanakkor*). The prompt checks for thematic progression across paragraphs. Limit: 10–12 sentences.

##### 7. Természetjárás vagy városi kikapcsolódás? (*Nature Hiking vs. City Entertainment*)

**Thematic Pivot:** Leisure & Lifestyle environment choices (complements the 2017 school break/excursion choices and 2020 cinema vs. home prompt).

**The Core Binary:** Spending a free weekend hiking in the quiet outdoors versus visiting a bustling city center for shopping, museums, or arcade entertainment.

**Student Prompt (Hungarian):**

> Ha szabadidőről van szó, egy osztály vagy baráti társaság gyakran válaszút elé kerül: a természetbe menjenek kirándulni, vagy egy városi programot (pl. pláza, múzeum, mozi) válasszanak? Melyiknek mik az előnyei és a hátrányai? Érvelj mindkét lehetőség mellett!

**Tutor Blueprint & Constraints:** Simple experiential baseline accessible to all learners. Ensures fairness regardless of exact socio-economic status. Limit: 10–12 sentences.

##### 8. Tehetségkutató műsorok vagy kitartó háttérmunka? (*Talent Shows vs. Long-Term Hard Work*)

**Thematic Pivot:** Pathways to artistic success (directly linked to the structural template of **2018 Variant 2**).

**The Core Binary:** Gaining rapid public recognition via television/social media talent competitions versus taking the traditional route of years of slow, untelevised practice.

**Student Prompt (Hungarian):**

> Sokan a televíziós és internetes tehetségkutatókat tartják a legjobb útnak a hírnév felé, míg mások szerint a valódi művészi siker alapja a csendes, kitartó munka. Hogyan látod ezt a kérdést? Írj érvelő szöveget mindkét álláspontot megvizsgálva!

**Tutor Blueprint & Constraints:** Requires conceptual analysis of abstract values (fame, effort, authenticity). Ideal for testing higher-tier vocabulary criteria. Limit: 10–12 sentences.

#### Category D: Lifestyle & Personal Development

##### 9. Otthoni kisállat: kutya/macska vagy egzotikus állat? (*Pets: Traditional vs. Exotic*)

**Thematic Pivot:** Domestic/Family responsibilities (builds upon the **2016 Variant 1** prompt regarding keeping animals in an apartment).

**The Core Binary:** Choosing a high-maintenance, companion-based traditional pet (dog/cat) versus a low-interaction, contained terrarium pet (fish/reptile).

**Student Prompt (Hungarian):**

> Egy kisállat befogadása nagy felelősség. Mi alapján döntsön egy család: egy mindennapi törődést igénylő társat (pl. kutyát) válasszon, vagy egy kevesebb időt igénylő, lakásban tartható állatot (pl. halat, hüllőt)? Érvelj mindkét döntés mellett!

**Tutor Blueprint & Constraints:** Evaluates causal thinking and realistic budgeting of time/effort. Must include structural transitions indicating constraint or concession. Limit: 10–12 sentences.

##### 10. Zsebpénz: fix összeg vagy munkáért járó jutalom? (*Allowance: Fixed Amount vs. Earned Reward*)

**Thematic Pivot:** Autonomy vs. Accountability (echoes the developmental dynamics found in the 2012 gift and 2019 adult vs. child prompts).

**The Core Binary:** Receiving a guaranteed weekly/monthly allowance automatically versus earning it as an explicitly calculated reward for doing household chores.

**Student Prompt (Hungarian):**

> Vannak szülők, akik alanyi jogon, fix összeget adnak zsebpénzként a gyermeküknek, mások viszont elvárják, hogy a diák otthoni munkával vagy jó tanulással keresse meg azt. Melyik módszerrel értesz egyet? Írj összefüggő szöveget, amelyben mindkét oldal mellett érvelsz!

**Tutor Blueprint & Constraints:** Explores moral and familial reasoning. Highly universal baseline for an 8th-grade student. Requires at least 3 logical arguments. Limit: 10–12 sentences.

### Editorial checks before reuse

Preserving the draft verbatim keeps the source prompt wording available, but does not endorse every instruction in it. Before turning a candidate into a learner-facing activity:

- Add an explicit sentence range and any required evidence (for example a personal experience) to the **student prompt** if those are intended requirements; several original prompts mention a limit only in the tutor blueprint.
- Resolve conflicting instructions. For example, “both sides” may mean reasons for each alternative, while “advantages and disadvantages” may mean pros and cons of each; state the intended structure and rubric explicitly.
- Treat “objective, balanced tone” and “higher-tier vocabulary” as draft teaching ideas, not exam marking rules. Do not reward a particular viewpoint or unnecessarily penalize age-appropriate language.
- Apply the fairness cautions in the assessment table. Do not describe a scenario as universally accessible without review; allow hypothetical reasoning and avoid requiring private family, financial, travel, or pet experience.
- Keep any rewritten prompt as a separately versioned derivative so this original wording and its provenance remain retrievable.

---

## Implementation Details

Follows [swe.md](../swe.md): high cohesion/low coupling, SSOT, explicit types, KISS/YAGNI, spike-before-scale, TDD (red-green-refactor, mocked LLM), quality gate (`python tools/quality_gate_report.py`, ruff, CC ≤ 10). Names follow the existing Hungarian-domain/English-technical mix of [db.py](../../src/felvi_games/db.py) and [models.py](../../src/felvi_games/models.py). Datetime handling follows [user-story-datetime-policy.md](./user-story-datetime-policy.md): UTC persisted (`utc_*`), local time derived for display only.

### Module layout (new code, one responsibility each)

| Module | Responsibility | Requirement |
|---|---|---|
| `writing_models.py` | Frozen dataclasses/enums: `WritingTask`, `ReviewGuide`, `Criterion`, `WritingSession`, `TutorMessage`, `DraftRevision`, `CriterionFeedback`, `WritingStage`, `FocusSkill`, `Genre`, `GuideOrigin` (`OFFICIAL`/`PRACTICE`) | all |
| `writing_rules.py` | Pure functions: sentence counter (title excluded per guide), under-minimum rule, point-bound clamping, active-time accumulation | WR-03, WR-06 |
| `writing_review.py` | LLM criterion review → validated structured result; applies `writing_rules`; uncertainty flag | WR-05 |
| `writing_tutor.py` | Tutor system prompt, stage state machine, message building; no UI/DB imports | WR-04 |
| `writing_repo.py` | Persistence (tasks, guides, sessions, messages, drafts, feedback, skill progress) | WR-07 |
| `writing_ui.py` | Streamlit workspace, saved-session review page, main-page entry helpers | WR-08 |
| `writing_import.py` | Task 10 extraction from `_fl`/`_ut` text + guide structuring; practice-topic loader | WR-01 |

`app.py` only gains routing and two buttons; logic stays out of it (it is already large).

### Data model (Alembic migration + `_ensure_*` pattern as in `db.py`)

- `writing_tasks`: id, source (`exam`/`practice`), exam_year, variant, task_no, genre, prompt_text (verbatim), constraints_json (sentence min/max, arguments, personal experience), suggested_minutes (nullable, shown as guidance only), provenance (file names / RAG archive id), parent_task_id (derived rewrites keep original retrievable), version.
- `review_guides`: id, task_id, origin (`official`/`practice`), version, max_points, assessable_max, criteria_json (name, max, level descriptors, rules such as zero-below-4-sentences, `assessable` flag for appearance), educator_approved (bool), approved_by, utc_approved_at.
- `writing_sessions`: id, user_id, task_id, guide_id, mode (`guided`/`simulation`), stage, focus_skill, status (`active`/`paused`/`submitted`/`closed`), utc_started_at, utc_ended_at, active_seconds, confidence_before/after.
- `writing_time_segments`: session_id, utc_start, utc_end (pause/resume; active_seconds = sum; SSOT for time).
- `tutor_messages`: session_id, seq, role (`learner`/`tutor`/`system`), content, kind (`chat`/`example`/`hint`), utc_created_at. `example` kind is excluded from scoring.
- `draft_revisions`: session_id, rev_no, text (never overwritten), sentence_count, is_submission, utc_saved_at.
- `criterion_feedback`: revision_id, guide_id, criterion, score (nullable = not assessed), max, comment, uncertain (bool), model, prompt_version.
- `writing_skill_progress`: user_id, focus_skill, stage, successes, last_confidence, utc_updated_at (derived/cacheable from sessions; recompute possible).

Indexes: `(user_id, utc_started_at)` on sessions, `(session_id, seq)` on messages. For local development, sessions have no automatic expiry as requested. Do not enable shared or remote use until deletion, access control, parent/teacher visibility, and applicable privacy safeguards are defined.

### Import and content pipeline

1. `pdf_parser.py`: remove the "skip composition tasks" instruction in `_SYSTEM_PROMPT`; route `feladat_tipus == "fogalmazas"` items to `writing_import.py` instead of `FeladatRepository` short-answer storage (keeps `check_answer` path untouched).
2. `writing_import.py` reads Task 10 from `_fl` and the matching Item 10 block of `_ut`, producing task + official guide with the verbatim prompt; unit-tested against fixtures copied from the files cited in the traceability table (2026_1, 2026_2, 2025_2, 2019_2, 2009_1, 2006_1).
3. Practice topics: load the 10 archived RAG topics from a versioned data file (`data/writing/practice_topics.json`) keeping original wording; a generation script drafts a `practice` guide per topic, marked `educator_approved=false`. Unapproved guides are usable only behind a "pilot" setting, always labelled practice.

### Tutor prompt and workflow

- System prompt (Hungarian, versioned `tutor_prompt_v1`): supportive, age-appropriate; one short question or step at a time; never writes the learner's composition; examples are short, on a different topic or a fragment, and tagged `example`; praises concrete things first; does not judge the learner's opinion; reminds that time is shown for information only.
- Inputs: task prompt, guide criteria, stage, focus skill, current draft, last N messages (token-bounded), learner confidence.
- Stage state machine (`writing_tutor.py`): `understand_task → choose_stance → plan_arguments → write_part → revise → full_composition → reflect`; the focus skill restricts the criteria the tutor discusses. Learner can jump or repeat any stage (no lock).
- Simulation mode: tutor and feedback disabled until submit; then the review runs and the tutor may discuss results.
- Reuse the OpenAI client setup from `ai.py` (`LLM_*` env vars); chat loop pattern from [teacher_chainlit_app.py](../../src/felvi_games/teacher_chainlit_app.py) minus tool calling initially (YAGNI).

### Review service

- Deterministic first: `writing_rules` computes sentence count and rule-based zeroing/clamping; the LLM returns JSON per criterion (`score`, `comment`, `evidence_quote`, `uncertain`); schema-validated, scores clamped to guide maxima, retried once on invalid JSON.
- Total = sum of assessable criteria; appearance stored as `NULL` (not assessed) for typed work; practice guides labelled "AI estimate".
- Prompt version and model are stored with every feedback row for later calibration against the educator benchmark.

### UI

- Main page (`_render_valasztas`): add "✍️ Fogalmazásműhely" and "📖 Írásnaplóm" (saved sessions) buttons that set `_active_page` to `writing` / `writing_history`; `main` routes accordingly. Existing flow unchanged.
- Writing page: task prompt panel (with provenance and guide label), draft `st.text_area` (tall, live sentence counter), chat panel (`st.chat_message`/`st.chat_input`), elapsed-time display (`st.fragment(run_every=…)` refresh), pause/resume, submit, confidence prompt.
- History page: list by date/task/mode, open read-only transcript, revisions with per-criterion comparison, resume paused session.
- Time: displayed as mm:ss, suggested minutes shown as guidance; no auto-submit, no disabled inputs on overrun.
- Adult review: expose a read-only session summary through `teacher_chat.build_teacher_chat_context` as a later slice.

### Delivery slices

| Slice | Scope | Done when |
|---|---|---|
| 0 Spike | Run review prompt on 3 official tasks + 3 hand-written responses; check JSON stability and score plausibility | Findings recorded; go/no-go |
| 1 Foundation | Models, rules, migration, repo, importer for official Task 10 + guides | Imported tasks match cited files; rules tests green |
| 2 Tutor + sessions | Tutor prompt, stage machine, writing page, time tracking, session save/resume, main-page buttons | Learner completes and reopens a guided session |
| 3 Review + history | Criterion review, revision comparison, history page, simulation mode | Official-guide scoring tests green; simulation hides feedback |
| 4 Progression + topic bank | Focus skills, progress, practice topics with approved guides | Educator-approved practice guides in use |

### Tests (TDD, LLM mocked)

- `writing_rules`: sentence counts (3/4/5, 9/10, title excluded), under-4 zeroing only for the 2026 MNy2 guide, clamping, active-time sum with pauses.
- `writing_import`: fixture-based parsing of each cited exam file; verbatim prompt preserved; no cross-variant constraint leakage.
- `writing_review`: invalid JSON retry, out-of-range clamp, `NULL` appearance, uncertainty propagation.
- `writing_tutor`: prompt contains guide/stage; simulation mode blocks hints; `example` messages unscored.
- Repo: session create → pause → resume → reload with transcript, revisions, time intact; UTC stored.
- CLI/UI smoke through existing `felvi` entry point per swe.md; manual check of timer non-blocking at and beyond suggested time.

### Definition of Done

Acceptance criteria met for the slice; tests and `ruff` pass; quality gate `PASS` without regression; migration applied on a copy of the existing DB; `progress_report.md` and `development_history.md` updated; educator sign-off recorded for any learner-facing practice guide.

### Risks

| Risk | Mitigation |
|---|---|
| AI scores inconsistent or too generous | Deterministic rules first, uncertainty flag, benchmark gates, formative labelling |
| Tutor drifts into writing the essay | Prompt rule + output check for long continuous prose; tests |
| Unapproved practice guides mistaken as official | Origin label in DB and UI; approval flag gate |
| Child data retention/privacy | Local prototype only, no automatic expiry per user decision; block production/shared use until deletion, access, visibility, and applicable privacy safeguards are defined |
| `app.py` growth | Keep logic in `writing_*` modules; only routing there |
| Token cost of long chats | Bounded history, cheap model for chat vs review model (`_CHEAP_MODEL`) |
