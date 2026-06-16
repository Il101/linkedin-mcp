"""Tests for LinkedInClient — network calls stubbed with httpx.MockTransport."""

import json
import urllib.parse

import httpx
import pytest

from linkedin_mcp.linkedin import LinkedInClient


def _make_client(handler) -> LinkedInClient:
    """Build a LinkedInClient whose internal httpx client uses a mock transport."""
    client = LinkedInClient(access_token="test-token")
    client._client = httpx.AsyncClient(
        headers=client._client.headers,
        transport=httpx.MockTransport(handler),
    )
    return client


def test_requires_token(monkeypatch):
    monkeypatch.delenv("LINKEDIN_ACCESS_TOKEN", raising=False)
    with pytest.raises(ValueError, match="LINKEDIN_ACCESS_TOKEN"):
        LinkedInClient()


def test_token_from_env(monkeypatch):
    monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "env-token")
    client = LinkedInClient()
    assert client.access_token == "env-token"


async def test_get_profile():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/userinfo"
        assert request.headers["Authorization"] == "Bearer test-token"
        return httpx.Response(200, json={"sub": "abc123", "name": "Ada", "email": "a@b.c"})

    async with _make_client(handler) as client:
        profile = await client.get_profile()
    assert profile["sub"] == "abc123"


async def test_get_user_urn():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"sub": "abc123"})

    async with _make_client(handler) as client:
        urn = await client.get_user_urn()
    assert urn == "urn:li:person:abc123"


async def test_create_post_builds_payload_and_url():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/userinfo"):
            return httpx.Response(200, json={"sub": "abc123"})
        # ugcPosts
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            201, headers={"x-restli-id": "urn:li:ugcPost:999"}, json={}
        )

    async with _make_client(handler) as client:
        result = await client.create_post("Hello world", "CONNECTIONS")

    assert result["id"] == "urn:li:ugcPost:999"
    assert result["url"] == "https://www.linkedin.com/feed/update/urn:li:ugcPost:999"
    payload = captured["payload"]
    assert payload["author"] == "urn:li:person:abc123"
    assert payload["lifecycleState"] == "PUBLISHED"
    assert (
        payload["specificContent"]["com.linkedin.ugc.ShareContent"]["shareCommentary"][
            "text"
        ]
        == "Hello world"
    )
    assert (
        payload["visibility"]["com.linkedin.ugc.MemberNetworkVisibility"]
        == "CONNECTIONS"
    )


async def test_create_post_missing_header_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/userinfo"):
            return httpx.Response(200, json={"sub": "abc123"})
        return httpx.Response(201, json={})  # no x-restli-id

    async with _make_client(handler) as client:
        with pytest.raises(RuntimeError, match="did not return a post ID"):
            await client.create_post("Hello")


async def test_delete_post_encodes_urn():
    urn = "urn:li:ugcPost:999"
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        # raw_path preserves percent-encoding (request.url.path decodes it back).
        captured["raw_path"] = request.url.raw_path.decode()
        return httpx.Response(200, json={})

    async with _make_client(handler) as client:
        result = await client.delete_post(urn)

    assert result["deleted_id"] == urn
    # The URN colons must be percent-encoded into the path segment.
    assert urllib.parse.quote(urn, safe="") in captured["raw_path"]


async def test_http_error_propagates():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "unauthorized"})

    async with _make_client(handler) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await client.get_profile()
