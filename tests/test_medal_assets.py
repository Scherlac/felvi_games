from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from felvi_games.medal_assets import (
    generate_medal_assets,
    get_medal_asset,
    medal_asset_exists,
)
from felvi_games.models import Erem


def _erem() -> Erem:
    return Erem(
        id="test_erem",
        nev="Teszt Érem",
        leiras="Leiras",
        ikon="*",
        kategoria="merfoldko",
        kep_url="https://example.com/kep.png",
        hang_url="https://example.com/hang.mp3",
        gif_url="https://example.com/gif.gif",
    )


def test_get_medal_asset_prefers_local_bytes(tmp_path: Path, monkeypatch) -> None:
    erem = _erem()

    def _asset_path(erem_id: str, kind: str) -> Path:
        return tmp_path / f"{erem_id}_{kind}.bin"

    monkeypatch.setattr("felvi_games.medal_assets.medal_asset_path", _asset_path)
    local = _asset_path(erem.id, "kep")
    local.write_bytes(b"PNG")

    value = get_medal_asset(erem, "kep")
    assert value == b"PNG"


def test_get_medal_asset_falls_back_to_url_or_none(tmp_path: Path, monkeypatch) -> None:
    erem = _erem()

    def _asset_path(erem_id: str, kind: str) -> Path:
        return tmp_path / f"{erem_id}_{kind}.bin"

    monkeypatch.setattr("felvi_games.medal_assets.medal_asset_path", _asset_path)

    assert get_medal_asset(erem, "hang") == "https://example.com/hang.mp3"
    assert get_medal_asset(erem, "unknown") is None


def test_medal_asset_exists_reports_presence(tmp_path: Path, monkeypatch) -> None:
    def _asset_path(erem_id: str, kind: str) -> Path:
        return tmp_path / f"{erem_id}_{kind}.bin"

    monkeypatch.setattr("felvi_games.medal_assets.medal_asset_path", _asset_path)

    assert medal_asset_exists("x", "kep") is False
    _asset_path("x", "kep").write_bytes(b"x")
    assert medal_asset_exists("x", "kep") is True


def test_generate_medal_assets_generates_supported_kinds(tmp_path: Path, monkeypatch) -> None:
    erem = _erem()

    def _asset_path(erem_id: str, kind: str) -> Path:
        return tmp_path / erem_id / f"{kind}.bin"

    monkeypatch.setattr("felvi_games.medal_assets.medal_asset_path", _asset_path)
    monkeypatch.setitem(
        sys.modules,
        "felvi_games.ai",
        SimpleNamespace(
            generate_medal_image=lambda nev, leiras, ikon: b"img-bytes",
            generate_medal_hang=lambda nev, leiras: b"audio-bytes",
        ),
    )

    saved = generate_medal_assets(erem, kinds=("kep", "hang", "gif"), overwrite=False)

    assert set(saved.keys()) == {"kep", "hang"}
    assert saved["kep"].read_bytes() == b"img-bytes"
    assert saved["hang"].read_bytes() == b"audio-bytes"


def test_generate_medal_assets_keeps_existing_when_no_overwrite(tmp_path: Path, monkeypatch) -> None:
    erem = _erem()

    def _asset_path(erem_id: str, kind: str) -> Path:
        return tmp_path / erem_id / f"{kind}.bin"

    monkeypatch.setattr("felvi_games.medal_assets.medal_asset_path", _asset_path)

    calls = {"img": 0, "hang": 0}
    monkeypatch.setitem(
        sys.modules,
        "felvi_games.ai",
        SimpleNamespace(
            generate_medal_image=lambda nev, leiras, ikon: calls.__setitem__("img", calls["img"] + 1) or b"new-img",
            generate_medal_hang=lambda nev, leiras: calls.__setitem__("hang", calls["hang"] + 1) or b"new-hang",
        ),
    )

    img_path = _asset_path(erem.id, "kep")
    img_path.parent.mkdir(parents=True, exist_ok=True)
    img_path.write_bytes(b"existing-img")

    saved = generate_medal_assets(erem, kinds=("kep",), overwrite=False)

    assert saved["kep"] == img_path
    assert img_path.read_bytes() == b"existing-img"
    assert calls["img"] == 0
    assert calls["hang"] == 0
