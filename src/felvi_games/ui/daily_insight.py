"""Daily insight Streamlit component."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import streamlit as st
from sqlalchemy.orm import Session

from felvi_games.db import EremRecord
from felvi_games.medal_assets import get_medal_asset

if TYPE_CHECKING:
    from felvi_games.db import FeladatRepository


def render_daily_insight(insight_data: dict[str, Any], repo: FeladatRepository) -> None:
    """Display the AI-generated daily progress insight."""
    greeting = insight_data.get("greeting", "")
    if greeting:
        st.markdown(f"### {greeting}")

    awardable_now = insight_data.get("awardable_now", [])
    would_repeat_now = insight_data.get("would_repeat_now", [])
    if awardable_now:
        st.markdown("#### ⚡ Most megszerezhető:")
        for erem in awardable_now:
            st.success(
                f"{erem.get('ikon', '🏅')} **{erem.get('nev', 'Ismeretlen érem')}**",
                icon=None,
            )
        st.markdown("---")

    if would_repeat_now:
        st.markdown("#### 🔁 Ismételhető érmek most teljesülnek:")
        st.caption("Ezeket már egyszer megszerezted, de a feltétel most újra teljesült.")
        for erem in would_repeat_now:
            name = erem.get("nev", "Ismételhető érem")
            icon = erem.get("ikon", "🏅")
            desc = str(erem.get("leiras", "") or "").strip()
            line = f"{icon} **{name}** — most újra megszerezhető"
            if desc:
                line += f"  \\n{desc}"
            st.info(line, icon="🔁")
        st.markdown("---")

    challenges = insight_data.get("active_challenges", [])
    if challenges:
        st.markdown("#### 🏆 Aktív kihívásaid:")
        for challenge in challenges:
            current = challenge.get("current")
            target = challenge.get("target")
            if challenge["teljesul"]:
                st.success(f"{challenge['ikon']} **{challenge['nev']}** — ✅ Teljesítetted!", icon=None)
            elif current is not None and target is not None and target > 0:
                percent = min(int(current / target * 100), 100)
                progress = f"  {current}/{target} ({percent}%)"
                st.info(
                    f"{challenge['ikon']} **{challenge['nev']}**  {progress}\n\n{challenge['leiras']}",
                    icon="⏳",
                )
                st.progress(percent / 100)
            else:
                st.info(f"{challenge['ikon']} **{challenge['nev']}**\n\n{challenge['leiras']}", icon="⏳")
        st.markdown("---")

    close_medals = insight_data.get("close_medals", [])
    if close_medals:
        st.markdown("#### 🎯 Hamarosan megszerezheted:")
        for medal in close_medals:
            percent = int(medal["progress"] * 100)
            bar = "█" * (percent // 10) + "░" * (10 - percent // 10)
            st.markdown(f"{medal['ikon']} **{medal['nev']}** `{bar}` {percent}%")
            st.caption(medal["hint"])

    teaser = insight_data.get("teaser_medal")
    if teaser:
        st.markdown("---")
        new_flag = " 🆕" if insight_data.get("new_medal_created") else ""
        st.markdown(f"#### ⭐ Következő cél{new_flag}")
        st.markdown(f"{teaser['ikon']} **{teaser['nev']}**")
        st.caption(teaser["leiras"])
        if teaser.get("id"):
            with Session(repo._engine) as session:
                rec = session.get(EremRecord, teaser["id"])
            if rec:
                asset = get_medal_asset(rec.to_domain(), "kep")
                if asset:
                    st.image(asset if isinstance(asset, bytes) else asset, width=160)

    if st.button("💪 Rajta, nézzük!", use_container_width=True, type="primary"):
        st.rerun()
