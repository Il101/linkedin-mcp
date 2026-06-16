"""Tests for the MCP tool layer — input validation and success paths.

The LinkedIn network client is replaced with a fake, so these tests exercise
the tool logic (validation, error wrapping, response shaping) in isolation.
"""

import pytest

from linkedin_mcp import server


class _FakeClient:
    """Async-context-manager stand-in for LinkedInClient."""

    def __init__(self, *, profile=None, post=None, raise_exc=None):
        self._profile = profile or {"name": "Ada", "email": "a@b.c", "sub": "abc123"}
        self._post = post or {
            "id": "urn:li:ugcPost:1",
            "url": "https://www.linkedin.com/feed/update/urn:li:ugcPost:1",
        }
        self._raise = raise_exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def create_post(self, text, visibility):
        if self._raise:
            raise self._raise
        return self._post

    async def get_profile(self):
        if self._raise:
            raise self._raise
        return self._profile

    async def delete_post(self, post_id):
        if self._raise:
            raise self._raise
        return {"deleted_id": post_id}


def _patch_client(monkeypatch, **kwargs):
    monkeypatch.setattr(server, "LinkedInClient", lambda: _FakeClient(**kwargs))


# --- post_to_linkedin validation ------------------------------------------

async def test_post_empty_text_raises():
    with pytest.raises(ValueError, match="required"):
        await server.post_to_linkedin("")


async def test_post_too_long_raises():
    with pytest.raises(ValueError, match="maximum is 3000"):
        await server.post_to_linkedin("x" * 3001)


async def test_post_bad_visibility_raises():
    with pytest.raises(ValueError, match="PUBLIC or CONNECTIONS"):
        await server.post_to_linkedin("hi", visibility="SECRET")


async def test_post_success(monkeypatch):
    _patch_client(monkeypatch)
    result = await server.post_to_linkedin("Hello", "PUBLIC")
    assert result["id"] == "urn:li:ugcPost:1"
    assert result["url"].endswith("urn:li:ugcPost:1")


async def test_post_api_error_wrapped(monkeypatch):
    _patch_client(monkeypatch, raise_exc=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="LinkedIn API error while publishing"):
        await server.post_to_linkedin("Hello")


# --- get_linkedin_profile --------------------------------------------------

async def test_get_profile_success(monkeypatch):
    _patch_client(monkeypatch)
    out = await server.get_linkedin_profile()
    assert "Ada" in out and "a@b.c" in out and "abc123" in out


async def test_get_profile_error_wrapped(monkeypatch):
    _patch_client(monkeypatch, raise_exc=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="while fetching profile"):
        await server.get_linkedin_profile()


# --- delete_linkedin_post --------------------------------------------------

async def test_delete_empty_raises():
    with pytest.raises(ValueError, match="required"):
        await server.delete_linkedin_post("")


async def test_delete_bad_urn_raises():
    with pytest.raises(ValueError, match="urn:li:"):
        await server.delete_linkedin_post("not-a-urn")


async def test_delete_success(monkeypatch):
    _patch_client(monkeypatch)
    out = await server.delete_linkedin_post("urn:li:ugcPost:1")
    assert "urn:li:ugcPost:1" in out


# --- registration sanity check --------------------------------------------

async def test_tools_registered():
    tools = await server.mcp.list_tools()
    names = {t.name for t in tools}
    assert {"post_to_linkedin", "get_linkedin_profile", "delete_linkedin_post"} <= names
