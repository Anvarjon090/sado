"""Sado's starter voices: the gallery pack the Voices page offers on an empty
library (owner request, 2026-11-10).

Local-first contract: the card is static text and the manifest + clips are
fetched only inside ``POST /community/packs/{pack_id}/install``, which the
Download button calls. These tests pin the source order, the install result
shape and the failure handling without touching the network: the manifest
loader and the per-item materializer are replaced.
"""
from __future__ import annotations

import sys

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


@pytest.fixture
def community(monkeypatch, tmp_path):
    monkeypatch.setenv("OMNIVOICE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("OMNIVOICE_GALLERY_SOURCES", raising=False)
    for mod in list(sys.modules):
        if mod in ("core", "services", "api") or mod.startswith(("core.", "services.", "api.")):
            del sys.modules[mod]
    from api.routers import community as module

    return module


def _client(module) -> TestClient:
    app = FastAPI()
    app.include_router(module.router)
    return TestClient(app, client=("127.0.0.1", 12345))


def _fake_gallery(module, monkeypatch, *, offline=False, packs=None, items=None):
    items = items if items is not None else [
        {"id": "sado_nilufar", "name": "Nilufar"},
        {"id": "sado_bobur", "name": "Bobur"},
        {"id": "sado_qodir", "name": "Qodir"},
    ]
    packs = packs if packs is not None else [
        {"id": module.STARTER_PACK_ID, "name": "Sado standart ovozlari",
         "item_ids": ["sado_nilufar", "sado_bobur", "sado_qodir", "sado_missing"]},
    ]
    monkeypatch.setattr(module, "_load", lambda refresh: (module.configured_sources(), items, packs, offline))


def test_sado_gallery_is_the_first_default_source(community):
    assert community.configured_sources()[0] == "Anvarjon090/sado-gallery"
    assert "debpalash/omnivoice-gallery" in community.configured_sources()


def test_install_adds_every_item_and_reports_the_ones_it_could_not(community, monkeypatch):
    _fake_gallery(community, monkeypatch)
    used: list[str] = []

    async def fake_use(item_id, name):
        # The real endpoint's `name` default is a FastAPI `Query` object, so a
        # direct call must pass None itself or `.strip()` blows up (seen live).
        assert name is None
        used.append(item_id)
        if item_id == "sado_bobur":
            raise HTTPException(status_code=503, detail="Couldn't add this voice right now.")
        return {"profile_id": "p-" + item_id, "name": item_id.split("_")[1].title()}

    monkeypatch.setattr(community, "community_use", fake_use)
    response = _client(community).post(f"/community/packs/{community.STARTER_PACK_ID}/install")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pack_id"] == community.STARTER_PACK_ID
    assert body["installed"] == [
        {"item_id": "sado_nilufar", "profile_id": "p-sado_nilufar", "name": "Nilufar"},
        {"item_id": "sado_qodir", "profile_id": "p-sado_qodir", "name": "Qodir"},
    ]
    assert [f["item_id"] for f in body["failed"]] == ["sado_bobur", "sado_missing"]
    # One bad clip never stops the rest, and unknown ids are never fetched.
    assert used == ["sado_nilufar", "sado_bobur", "sado_qodir"]


def test_unknown_pack_is_404_and_offline_gallery_is_503(community, monkeypatch):
    _fake_gallery(community, monkeypatch)
    assert _client(community).post("/community/packs/nope/install").status_code == 404
    assert _client(community).post("/community/packs/../etc/install").status_code == 404
    _fake_gallery(community, monkeypatch, offline=True, packs=[])
    response = _client(community).post(f"/community/packs/{community.STARTER_PACK_ID}/install")
    assert response.status_code == 503
    assert "not reachable" in response.json()["detail"]
