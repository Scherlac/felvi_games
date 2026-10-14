"""Streamlit writing-practice workspace."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict

import streamlit as st
from openai import APIError

from felvi_games.ai import coach_writing_chat, review_writing_submission
from felvi_games.writing_repo import WritingPracticeRepository, WritingPracticeSession, WritingTutorMessage
from felvi_games.writing_review import ReviewCriterion, ReviewGuide, WritingReview, WritingReviewError
from felvi_games.writing_tasks import (
    WritingPracticeTask,
    estimate_sentence_count,
    load_reference_writing_task,
)

logger = logging.getLogger(__name__)

_SESSION_STATE_KEY = "_writing_practice_session_id"
_TUTOR_ERROR_STATE_PREFIX = "_writing_tutor_error_"


def _format_elapsed(seconds: int) -> str:
    minutes, remainder = divmod(max(0, seconds), 60)
    return f"{minutes:02d}:{remainder:02d}"


def _review_json(review: WritingReview, learner_sentence_count: int) -> str:
    return json.dumps(
        {
            "guide_id": review.guide_id,
            "total_score": review.total_score,
            "assessable_max_score": review.assessable_max_score,
            "learner_sentence_count": learner_sentence_count,
            "criteria": [asdict(criterion) for criterion in review.criteria],
        },
        ensure_ascii=False,
    )


def _render_timer(repository: WritingPracticeRepository, writing_session: WritingPracticeSession) -> None:
    if writing_session.status != "active":
        st.metric("Aktív gyakorlási idő", _format_elapsed(writing_session.active_seconds))
        return

    fragment = getattr(st, "fragment", None)
    if fragment is None:
        st.metric(
            "Aktív gyakorlási idő",
            _format_elapsed(
                repository.checkpoint_active_time(
                    writing_session.id,
                    writing_session.felhasznalo_nev,
                )
            ),
        )
        st.caption("A számláló az oldal frissítésekor frissül.")
        return

    @fragment(run_every="1s")
    def render_live_timer() -> None:
        elapsed = repository.checkpoint_active_time(
            writing_session.id,
            writing_session.felhasznalo_nev,
        )
        st.metric("Aktív gyakorlási idő", _format_elapsed(elapsed))

    render_live_timer()


def _render_review(feedback_json: str | None) -> None:
    if not feedback_json:
        st.info("Ehhez a változathoz még nem készült értékelés.")
        return
    result = json.loads(feedback_json)
    st.subheader("Gyakorló értékelés — nem hivatalos vizsgaeredmény")
    sentence_count = result.get("learner_sentence_count")
    if isinstance(sentence_count, int) and not isinstance(sentence_count, bool):
        st.caption(f"Tanuló által megadott mondatszám (cím nélkül): {sentence_count}")
    st.metric(
        "Értékelhető szempontok összesen",
        f"{result['total_score']} / {result['assessable_max_score']}",
    )
    for criterion in result["criteria"]:
        with st.container(border=True):
            if criterion["score"] is None:
                st.markdown(f"**{criterion['criterion_id']} — nem értékelhető gépelt szövegből**")
            else:
                st.markdown(
                    f"**{criterion['criterion_id']} — "
                    f"{criterion['score']} / {criterion['max_points']} pont**"
                )
            st.write(criterion["feedback"])
            if criterion["evidence_quote"]:
                st.caption(f"Idézett bizonyíték: {criterion['evidence_quote']}")
            if criterion["uncertain"]:
                st.warning("Az értékelés bizonytalan.")
            if criterion["was_clamped"]:
                st.warning("A modell pontszáma kívül esett a megengedett tartományon; korlátozva lett.")


def _open_session(session_id: int) -> None:
    st.session_state[_SESSION_STATE_KEY] = session_id


def _refresh_sentence_count(session_id: int) -> None:
    draft = st.session_state.get(f"writing_draft_{session_id}", "")
    st.session_state[f"writing_sentence_count_{session_id}"] = estimate_sentence_count(draft)


def _guide_from_session(writing_session: WritingPracticeSession) -> ReviewGuide:
    snapshot = json.loads(writing_session.guide_json)
    return ReviewGuide(
        guide_id=snapshot["guide_id"],
        name=snapshot["name"],
        criteria=tuple(ReviewCriterion(**item) for item in snapshot["criteria"]),
    )


def _save_current_draft(
    repository: WritingPracticeRepository,
    writing_session: WritingPracticeSession,
) -> None:
    draft = st.session_state.get(f"writing_draft_{writing_session.id}")
    if writing_session.status == "active" and isinstance(draft, str):
        repository.save_revision(
            writing_session.id,
            writing_session.felhasznalo_nev,
            draft,
        )


def _request_tutor_reply(
    repository: WritingPracticeRepository,
    writing_session: WritingPracticeSession,
    guide: ReviewGuide,
) -> str | None:
    messages = repository.list_messages(
        writing_session.id,
        writing_session.felhasznalo_nev,
    )
    if not messages or messages[-1].role != "user":
        raise ValueError("No unanswered learner message is available.")

    draft = st.session_state.get(f"writing_draft_{writing_session.id}", "")
    sentence_count = st.session_state.get(f"writing_sentence_count_{writing_session.id}")
    if isinstance(sentence_count, bool) or not isinstance(sentence_count, int):
        sentence_count = None
    history = [
        {"role": message.role, "content": message.content}
        for message in messages[:-1][-8:]
    ]
    try:
        reply = coach_writing_chat(
            writing_session.task_prompt,
            draft if isinstance(draft, str) else "",
            guide,
            history,
            messages[-1].content,
            sentence_count=sentence_count,
        )
    except (APIError, RuntimeError, ValueError) as error:
        logger.exception("Writing tutor request failed")
        return str(error)

    repository.save_chat_message(
        writing_session.id,
        writing_session.felhasznalo_nev,
        "assistant",
        reply,
    )
    return None


def _render_tutor_chat(
    repository: WritingPracticeRepository,
    writing_session: WritingPracticeSession,
    guide: ReviewGuide,
) -> None:
    st.subheader("Tutorbeszélgetés")
    messages: list[WritingTutorMessage] = repository.list_messages(
        writing_session.id,
        writing_session.felhasznalo_nev,
    )
    error_state_key = f"{_TUTOR_ERROR_STATE_PREFIX}{writing_session.id}"
    previous_error = st.session_state.pop(error_state_key, None)
    if previous_error:
        st.error(f"A tutor válasza nem érkezett meg: {previous_error}")
    for message in messages:
        with st.chat_message(message.role):
            st.write(message.content)

    if writing_session.status != "active":
        return

    if messages and messages[-1].role == "user":
        if st.button("Tutor válaszának újrapróbálása", key=f"writing_tutor_retry_{writing_session.id}"):
            error = _request_tutor_reply(repository, writing_session, guide)
            if error:
                st.session_state[error_state_key] = error
            else:
                st.session_state.pop(error_state_key, None)
            st.rerun()

    with st.form(key=f"writing_tutor_form_{writing_session.id}", clear_on_submit=True):
        learner_message = st.text_area(
            "Mit szeretnél megbeszélni a tutorral?",
            max_chars=2000,
            key=f"writing_tutor_input_{writing_session.id}",
            height=90,
        )
        send_message = st.form_submit_button(
            "Üzenet küldése",
            key=f"writing_tutor_send_{writing_session.id}",
        )

    if send_message:
        if not learner_message.strip():
            st.warning("Írj egy rövid kérdést vagy mondd el, melyik részen dolgoznál.")
            return
        repository.save_chat_message(
            writing_session.id,
            writing_session.felhasznalo_nev,
            "user",
            learner_message,
        )
        error = _request_tutor_reply(repository, writing_session, guide)
        if error:
            st.session_state[error_state_key] = error
        else:
            st.session_state.pop(error_state_key, None)
        st.rerun()


def render_writing_practice_page(
    felhasznalo_nev: str,
    repository: WritingPracticeRepository | None = None,
) -> None:
    """Render a writing-practice session with the verified exam task."""
    if not felhasznalo_nev:
        st.error("A gyakorláshoz előbb válassz profilt.")
        return

    repository = repository or WritingPracticeRepository()
    st.title("Fogalmazásműhely")
    st.warning(
        "A feladat, vázlat és tutorbeszélgetés a beállított, jóváhagyott AI-szolgáltatóhoz kerül. "
        "A munkamenet helyben, automatikus lejárat nélkül mentődik. A profilnév nem hozzáférés-védelem; "
        "használd kizárólag az engedélyezett környezetben."
    )
    try:
        task: WritingPracticeTask | None = load_reference_writing_task()
        task_load_error = None
    except (OSError, ValueError) as error:
        logger.exception("Could not load the reference writing task")
        task = None
        task_load_error = str(error)

    if st.button("← Vissza a főoldalra", key="writing_practice_back"):
        active_session_id = st.session_state.get(_SESSION_STATE_KEY)
        if active_session_id is not None:
            active_session = repository.get_session(active_session_id, felhasznalo_nev)
            if active_session is not None:
                _save_current_draft(repository, active_session)
        st.session_state["_active_page"] = "game"
        st.session_state.pop(_SESSION_STATE_KEY, None)
        st.rerun()

    sessions = repository.list_sessions(felhasznalo_nev)
    if sessions:
        st.subheader("Mentett írásgyakorlások")
        for saved_session in sessions:
            saved_metadata = json.loads(saved_session.task_metadata_json)
            task_title = saved_metadata.get("title", saved_session.task_id)
            label = (
                f"#{saved_session.id} · {task_title} · {saved_session.status} · "
                f"{saved_session.utc_started_at.astimezone().strftime('%Y-%m-%d %H:%M')}"
            )
            st.button(
                label,
                key=f"writing_practice_open_{saved_session.id}",
                on_click=_open_session,
                args=(saved_session.id,),
            )

    session_id = st.session_state.get(_SESSION_STATE_KEY)
    if session_id is None:
        if task_load_error:
            st.error(f"A hivatalos írásfeladat nem tölthető be: {task_load_error}")
        if task is not None:
            st.subheader(task.title)
            st.caption(
                f"Hivatalos vizsgafeladat · {task.source_reference} · "
                f"{task.min_sentences}–{task.max_sentences} mondat · "
                f"javasolt idő: {task.suggested_time_min}–{task.suggested_time_max} perc"
            )
            st.write(task.prompt)
            st.caption(f"Értékelési útmutató: {task.guide.name}")
            if st.button(
                "Új írásgyakorlás indítása",
                type="primary",
                key="writing_practice_start",
            ):
                writing_session = repository.create_session(felhasznalo_nev, task)
                st.session_state[_SESSION_STATE_KEY] = writing_session.id
                st.rerun()
        st.info("Válassz egy mentett írásgyakorlást, vagy indíts újat.")
        return

    writing_session = repository.get_session(session_id, felhasznalo_nev)
    if writing_session is None:
        st.session_state.pop(_SESSION_STATE_KEY, None)
        st.warning("A mentett írásgyakorlás nem található ennél a profilnál.")
        return

    task_metadata = json.loads(writing_session.task_metadata_json)
    st.subheader(task_metadata.get("title", writing_session.task_id))
    st.caption(
        f"{task_metadata.get('source_reference', 'Korábbi írásfeladat')} · "
        f"{task_metadata.get('min_sentences', '—')}–{task_metadata.get('max_sentences', '—')} mondat"
    )
    st.write(writing_session.task_prompt)
    if task_metadata.get("suggested_time_min") is not None:
        st.caption(
            f"Javasolt idő: {task_metadata['suggested_time_min']}–"
            f"{task_metadata['suggested_time_max']} perc; a gyakorlás időkorlát nélkül folytatható."
        )

    guide = _guide_from_session(writing_session)
    revisions = repository.list_revisions(session_id, felhasznalo_nev)
    initial_draft = revisions[-1].draft_text if revisions else ""
    sentence_count_key = f"writing_sentence_count_{session_id}"
    if sentence_count_key not in st.session_state:
        saved_sentence_count = None
        if revisions and revisions[-1].feedback_json:
            saved_sentence_count = json.loads(revisions[-1].feedback_json).get(
                "learner_sentence_count"
            )
        st.session_state[sentence_count_key] = (
            saved_sentence_count
            if isinstance(saved_sentence_count, int) and not isinstance(saved_sentence_count, bool)
            else estimate_sentence_count(initial_draft)
        )
    draft_text = st.text_area(
        "Saját fogalmazásod (mentéskor új, változatlan előzmény jön létre)",
        value=initial_draft,
        key=f"writing_draft_{session_id}",
        height=280,
        max_chars=12000,
        disabled=writing_session.status != "active",
        on_change=_refresh_sentence_count,
        args=(session_id,),
    )
    sentence_count = st.number_input(
        "Mondatszám (a cím nélkül; ellenőrizd és szükség esetén javítsd)",
        min_value=0,
        max_value=2000,
        step=1,
        key=sentence_count_key,
        disabled=writing_session.status != "active",
    )
    _render_timer(repository, writing_session)
    st.caption("Az idő tájékoztató jellegű: nem korlátoz, nem küld be automatikusan.")

    if writing_session.status == "active":
        save_col, pause_col, submit_col = st.columns(3)
        with save_col:
            if st.button("Vázlat mentése", key=f"writing_practice_save_{session_id}"):
                repository.save_revision(session_id, felhasznalo_nev, draft_text)
                st.success("A vázlat mentve.")
        with pause_col:
            if st.button("Szüneteltetés", key=f"writing_practice_pause_{session_id}"):
                repository.save_revision(session_id, felhasznalo_nev, draft_text)
                repository.pause_session(session_id, felhasznalo_nev)
                st.rerun()
        with submit_col:
            if st.button("Beküldés és értékelés", type="primary", key=f"writing_practice_submit_{session_id}"):
                if not draft_text.strip():
                    st.warning("Beküldés előtt írj legalább egy mondatot.")
                    return
                revision = repository.save_revision(session_id, felhasznalo_nev, draft_text)
                try:
                    with st.spinner("Az AI értékeli a beküldött fogalmazást..."):
                        minimum_sentence_count = task_metadata.get("min_sentences_for_any_points")
                        review = review_writing_submission(
                            writing_session.task_prompt,
                            draft_text,
                            guide,
                            sentence_count=(
                                int(sentence_count)
                                if isinstance(minimum_sentence_count, int)
                                else None
                            ),
                            min_sentences_for_any_points=(
                                minimum_sentence_count
                                if isinstance(minimum_sentence_count, int)
                                else None
                            ),
                        )
                except (APIError, WritingReviewError) as error:
                    logger.exception("Writing review request failed")
                    st.error(
                        "Az AI-értékelés nem sikerült. A vázlatot elmentettük; "
                        f"próbáld újra később. Részlet: {error}"
                    )
                    return
                repository.save_review(
                    session_id,
                    revision.id,
                    felhasznalo_nev,
                    _review_json(review, int(sentence_count)),
                )
                repository.submit_session(session_id, felhasznalo_nev)
                st.rerun()
    elif writing_session.status == "paused":
        if st.button("Folytatás", key=f"writing_practice_resume_{session_id}"):
            repository.resume_session(session_id, felhasznalo_nev)
            st.rerun()
    elif writing_session.status == "submitted":
        if task is not None:
            if st.button("Új írásgyakorlás indítása", key=f"writing_practice_new_{session_id}"):
                new_session = repository.create_session(felhasznalo_nev, task)
                st.session_state[_SESSION_STATE_KEY] = new_session.id
                st.rerun()
        elif task_load_error:
            st.error(f"Új írásfeladat nem tölthető be: {task_load_error}")

    _render_tutor_chat(repository, writing_session, guide)

    revisions = repository.list_revisions(session_id, felhasznalo_nev)
    if revisions:
        st.subheader("Mentett változatok")
        for revision in revisions:
            with st.expander(f"{revision.revision_no}. változat"):
                st.write(revision.draft_text)
                _render_review(revision.feedback_json)
