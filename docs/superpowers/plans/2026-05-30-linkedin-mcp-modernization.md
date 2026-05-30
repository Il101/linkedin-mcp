# LinkedIn MCP Modernization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the LinkedIn MCP server to use FastMCP with Streamable HTTP transport, proper ASGI Bearer-token auth middleware, tool annotations, raise-based error handling, and accurate documentation.

**Architecture:** `server.py` becomes a FastMCP app — tools registered as async decorated functions with `ToolAnnotations`, health routes via `@mcp.custom_route`, HTTP mode wraps `streamable_http_app()` in a pure ASGI auth middleware. `linkedin.py` gets a shared `httpx.AsyncClient`, returns `{id, url}` from `create_post`, and uses proper URL encoding.

**Tech Stack:** Python 3.11+, `mcp==1.27.1` (FastMCP), `httpx`, `uvicorn`, `starlette`

---

### Task 1: Rewrite LinkedInClient

**Files:**
- Modify: `src/linkedin_mcp/linkedin.py`

- [ ] **Step 1: Replace the file with the updated client**

Replace the entire content of `src/linkedin_mcp/linkedin.py` with:

```python
"""LinkedIn API Client"""

import os
import urllib.parse
import httpx
from typing import Optional


class LinkedInClient:
    """Client for LinkedIn API v2"""

    BASE_URL = "https://api.linkedin.com/v2"

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token or os.getenv("LINKEDIN_ACCESS_TOKEN")
        if not self.access_token:
            raise ValueError("LINKEDIN_ACCESS_TOKEN environment variable is required")

        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
            }
        )

    async def get_profile(self) -> dict:
        """Get current user's LinkedIn profile"""
        response = await self._client.get(f"{self.BASE_URL}/userinfo")
        response.raise_for_status()
        return response.json()

    async def get_user_urn(self) -> str:
        """Get the user's URN for posting"""
        profile = await self.get_profile()
        return f"urn:li:person:{profile['sub']}"

    async def create_post(self, text: str, visibility: str = "PUBLIC") -> dict:
        """
        Create a text post on LinkedIn.

        Args:
            text: The post content (max 3000 chars)
            visibility: PUBLIC or CONNECTIONS

        Returns:
            dict with 'id' (URN) and 'url' (full LinkedIn post URL)
        """
        user_urn = await self.get_user_urn()

        payload = {
            "author": user_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": visibility
            },
        }

        response = await self._client.post(f"{self.BASE_URL}/ugcPosts", json=payload)
        response.raise_for_status()

        urn = response.headers.get("x-restli-id", "")
        url = f"https://www.linkedin.com/feed/update/{urn}" if urn else ""
        return {"id": urn, "url": url}

    async def delete_post(self, post_id: str) -> dict:
        """
        Delete a LinkedIn post by URN.

        Args:
            post_id: The post URN (e.g., urn:li:ugcPost:123456)

        Returns:
            dict with 'deleted_id'
        """
        encoded_id = urllib.parse.quote(post_id, safe="")
        response = await self._client.delete(f"{self.BASE_URL}/ugcPosts/{encoded_id}")
        response.raise_for_status()
        return {"deleted_id": post_id}
```

- [ ] **Step 2: Verify import works**

```bash
cd "/Users/iliazarikov/Documents/Python Projects/MCP" && .venv/bin/python -c "from linkedin_mcp.linkedin import LinkedInClient; print('OK')"
```

Expected output: `OK`

- [ ] **Step 3: Commit**

```bash
cd "/Users/iliazarikov/Documents/Python Projects/MCP" && git add src/linkedin_mcp/linkedin.py && git commit -m "refactor(client): shared httpx client, return post URL, proper URL encoding"
```

---

### Task 2: Rewrite server.py with FastMCP

**Files:**
- Modify: `src/linkedin_mcp/server.py`

- [ ] **Step 1: Replace the file with the FastMCP implementation**

Replace the entire content of `src/linkedin_mcp/server.py` with:

```python
"""LinkedIn MCP Server — FastMCP with Streamable HTTP transport"""

import asyncio
import json
import os

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from .linkedin import LinkedInClient

# ---------------------------------------------------------------------------
# Auth middleware (pure ASGI — does NOT buffer response bodies)
# BaseHTTPMiddleware is intentionally avoided: it buffers the response body
# and breaks SSE streams used by Streamable HTTP.
# ---------------------------------------------------------------------------
OPEN_PATHS = {"/", "/health"}
MCP_API_KEY = os.getenv("MCP_API_KEY", "")


class BearerAuthMiddleware:
    """Pure ASGI middleware that validates Authorization: Bearer tokens."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") in OPEN_PATHS:
            await self.app(scope, receive, send)
            return

        if not MCP_API_KEY:
            # No key configured — allow all (local / stdio mode)
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        auth = headers.get(b"authorization", b"").decode()
        if auth == f"Bearer {MCP_API_KEY}":
            await self.app(scope, receive, send)
            return

        # Reject with 401
        body = json.dumps({"error": "Unauthorized"}).encode()
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body})


# ---------------------------------------------------------------------------
# FastMCP app
# ---------------------------------------------------------------------------
mcp = FastMCP(
    "linkedin-mcp",
    instructions="Publish, inspect, and delete LinkedIn posts on behalf of the authenticated user.",
)


# ---------------------------------------------------------------------------
# Health routes (registered before streamable_http_app() is called)
# ---------------------------------------------------------------------------
@mcp.custom_route("/", methods=["GET"])
async def index(request: Request) -> PlainTextResponse:
    return PlainTextResponse("LinkedIn MCP Server is running")


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> PlainTextResponse:
    return PlainTextResponse("LinkedIn MCP Server is running")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
@mcp.tool(
    title="Publish LinkedIn Post",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
async def post_to_linkedin(
    text: str,
    visibility: str = "PUBLIC",
) -> dict:
    """Publish a text post to LinkedIn.

    Use this to share professional content, insights, or updates with your network.

    Args:
        text: Post content (max 3000 characters). Can include emojis, line breaks, hashtags.
        visibility: PUBLIC (anyone on LinkedIn) or CONNECTIONS (only your connections).

    Returns:
        dict with 'id' (post URN) and 'url' (full LinkedIn post URL).
    """
    if not text:
        raise ValueError("Post text is required")
    if len(text) > 3000:
        raise ValueError(f"Post text is {len(text)} characters; maximum is 3000")
    if visibility not in ("PUBLIC", "CONNECTIONS"):
        raise ValueError("visibility must be PUBLIC or CONNECTIONS")

    client = LinkedInClient()
    try:
        return await client.create_post(text, visibility)
    except Exception as e:
        raise RuntimeError(f"LinkedIn API error while publishing post: {e}") from e


@mcp.tool(
    title="Get LinkedIn Profile",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
async def get_linkedin_profile() -> str:
    """Get the current user's LinkedIn profile information.

    Returns name, email, and LinkedIn user ID. Useful for verifying authentication
    before posting.
    """
    client = LinkedInClient()
    try:
        profile = await client.get_profile()
        return (
            f"LinkedIn Profile:\n"
            f"Name: {profile.get('name', 'N/A')}\n"
            f"Email: {profile.get('email', 'N/A')}\n"
            f"ID: {profile.get('sub', 'N/A')}"
        )
    except Exception as e:
        raise RuntimeError(f"LinkedIn API error while fetching profile: {e}") from e


@mcp.tool(
    title="Delete LinkedIn Post",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
)
async def delete_linkedin_post(post_id: str) -> str:
    """Delete a LinkedIn post by its URN. This action is irreversible.

    Args:
        post_id: The post URN (e.g., urn:li:ugcPost:7444827823619563520).
                 Obtained from the 'id' field returned by post_to_linkedin.
    """
    if not post_id:
        raise ValueError("post_id is required")
    if not post_id.startswith("urn:li:"):
        raise ValueError("post_id must be a LinkedIn URN starting with 'urn:li:'")

    client = LinkedInClient()
    try:
        result = await client.delete_post(post_id)
        return f"Post deleted successfully. Deleted ID: {result['deleted_id']}"
    except Exception as e:
        raise RuntimeError(f"LinkedIn API error while deleting post: {e}") from e


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------
@mcp.prompt()
def linkedin_post_creator(topic: str = "your expertise") -> str:
    """Guide for creating engaging LinkedIn posts.

    Args:
        topic: The topic or subject of the post.
    """
    return f"""You are helping create a LinkedIn post about {topic}.

Best practices for LinkedIn posts:
1. Start with a hook — grab attention in the first line
2. Keep it concise — 150-300 words is optimal
3. Use line breaks for readability
4. Add relevant emojis sparingly (1-3 per post)
5. Include a call-to-action if appropriate
6. Use hashtags (2-5 relevant ones)
7. Professional but conversational tone

Post structure:
- Hook (1-2 lines)
- Main content (value, story, or insight)
- Conclusion or CTA
- Hashtags

When ready, use the post_to_linkedin tool to publish."""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    import sys
    if os.getenv("RAILWAY_ENVIRONMENT") or "--http" in sys.argv:
        import uvicorn
        if not MCP_API_KEY:
            print("WARNING: MCP_API_KEY is not set — the /mcp endpoint is public")
        port = int(os.getenv("PORT", 8000))
        app = BearerAuthMiddleware(mcp.streamable_http_app())
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        asyncio.run(mcp.run_stdio_async())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify import and server construction**

```bash
cd "/Users/iliazarikov/Documents/Python Projects/MCP" && .venv/bin/python -c "
from linkedin_mcp.server import mcp, BearerAuthMiddleware
app = mcp.streamable_http_app()
print('routes:', [r.path for r in app.routes])
wrapped = BearerAuthMiddleware(app)
print('middleware wraps app OK')
"
```

Expected output:
```
routes: ['/', '/health', '/mcp']
middleware wraps app OK
```

- [ ] **Step 3: Verify tools are registered with correct annotations**

```bash
cd "/Users/iliazarikov/Documents/Python Projects/MCP" && .venv/bin/python -c "
from linkedin_mcp.server import mcp
tools = mcp._tool_manager._tools
for name, t in tools.items():
    print(f'{name}: title={t.title}, annotations={t.annotations}')
"
```

Expected output:
```
post_to_linkedin: title=Publish LinkedIn Post, annotations=title=None readOnlyHint=False ...
get_linkedin_profile: title=Get LinkedIn Profile, annotations=title=None readOnlyHint=True ...
delete_linkedin_post: title=Delete LinkedIn Post, annotations=title=None readOnlyHint=False destructiveHint=True ...
```

- [ ] **Step 4: Commit**

```bash
cd "/Users/iliazarikov/Documents/Python Projects/MCP" && git add src/linkedin_mcp/server.py && git commit -m "feat: rewrite server with FastMCP, Streamable HTTP, ASGI auth middleware, tool annotations"
```

---

### Task 3: Fix get_token.py — secrets from env

**Files:**
- Modify: `get_token.py`

- [ ] **Step 1: Replace hardcoded credentials with env reads**

Replace lines 3-5 in `get_token.py` (the CLIENT_ID / CLIENT_SECRET / REDIRECT_URI block) by replacing the entire top section of the file:

```python
import os
import urllib.parse
import urllib.request
import json
import base64
from http.server import BaseHTTPRequestHandler, HTTPServer
import webbrowser

CLIENT_ID = os.getenv("LINKEDIN_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET", "")
REDIRECT_URI = "http://localhost:8080/callback"
SCOPE = "openid profile w_member_social"

if not CLIENT_ID or not CLIENT_SECRET:
    print("ERROR: Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET in your environment before running this script.")
    raise SystemExit(1)
```

The rest of the file (the `OAuthHandler` class and `main()` function) stays unchanged.

- [ ] **Step 2: Verify the guard works**

```bash
cd "/Users/iliazarikov/Documents/Python Projects/MCP" && .venv/bin/python -c "
import subprocess, sys
result = subprocess.run([sys.executable, 'get_token.py'], capture_output=True, text=True)
print('stdout:', result.stdout)
print('returncode:', result.returncode)
"
```

Expected output:
```
stdout: ERROR: Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET in your environment before running this script.
returncode: 1
```

- [ ] **Step 3: Commit**

```bash
cd "/Users/iliazarikov/Documents/Python Projects/MCP" && git add get_token.py && git commit -m "fix(get_token): read CLIENT_ID and CLIENT_SECRET from env instead of hardcoding"
```

---

### Task 4: Update .env.example

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Replace .env.example**

Replace the entire content of `.env.example` with:

```bash
# LinkedIn API — obtain from https://www.linkedin.com/developers/apps
# Required scopes: openid, profile, w_member_social
LINKEDIN_ACCESS_TOKEN=your_linkedin_access_token_here

# MCP server auth — required for remote (Railway) deployment
# Generate: openssl rand -hex 32
# When set, all requests to /mcp must include: Authorization: Bearer <key>
MCP_API_KEY=your_secret_key_here

# Server port (Railway sets this automatically)
PORT=8000

# OAuth app credentials — only needed to run get_token.py locally
LINKEDIN_CLIENT_ID=your_app_client_id
LINKEDIN_CLIENT_SECRET=your_app_client_secret
```

- [ ] **Step 2: Commit**

```bash
cd "/Users/iliazarikov/Documents/Python Projects/MCP" && git add .env.example && git commit -m "docs(env): replace MCP_SECRET_PATH with MCP_API_KEY, add OAuth app vars"
```

---

### Task 5: Rewrite README.md

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace README.md**

Replace the entire content of `README.md` with:

```markdown
# LinkedIn MCP Server

MCP server for publishing, inspecting, and deleting LinkedIn posts via AI assistants (Claude, Cursor, Windsurf, Cline).

Uses the **Streamable HTTP** transport (MCP spec 2025-03-26) for remote deployments and **stdio** for local use with Claude Desktop.

## Tools

| Tool | What it does | Side effects |
|---|---|---|
| `post_to_linkedin` | Publish a text post (up to 3000 chars, PUBLIC or CONNECTIONS visibility) | Writes |
| `get_linkedin_profile` | Get current user's name, email, and LinkedIn ID | Read-only |
| `delete_linkedin_post` | Delete a post by URN — **irreversible** | Destructive |

## Prompt

`linkedin_post_creator` — a guided prompt for composing LinkedIn posts. Accepts an optional `topic` argument.

## Setup

### 1. Create a LinkedIn App

Go to the [LinkedIn Developer Portal](https://www.linkedin.com/developers/apps), create an app, and add these OAuth 2.0 scopes:

- `openid` — retrieve user ID
- `profile` — retrieve user name
- `w_member_social` — publish and delete posts

### 2. Install

```bash
pip install -r requirements.txt
pip install -e .
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env — fill in LINKEDIN_ACCESS_TOKEN and MCP_API_KEY
```

### 4. Get a LinkedIn access token

```bash
# Set your OAuth app credentials in the environment first:
export LINKEDIN_CLIENT_ID="your_client_id"
export LINKEDIN_CLIENT_SECRET="your_client_secret"

python get_token.py
# Follow the browser prompt — your access token will be printed
# Note: LinkedIn access tokens expire after ~60 days; rerun this script to renew
```

## Connect to AI Assistants

### Claude Desktop (stdio — local)

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "linkedin": {
      "command": "linkedin-mcp",
      "env": {
        "LINKEDIN_ACCESS_TOKEN": "your_token"
      }
    }
  }
}
```

### Claude Code / Cursor / Windsurf (remote via Railway)

Add a remote MCP server:

```
URL: https://your-app.railway.app/mcp
Authorization: Bearer YOUR_MCP_API_KEY
```

## Deploy on Railway

1. Create a new project on [Railway](https://railway.app) and connect this repository.
2. Set these environment variables:
   - `LINKEDIN_ACCESS_TOKEN` — your LinkedIn access token
   - `MCP_API_KEY` — a secret key protecting the `/mcp` endpoint (`openssl rand -hex 32`)
   - `PORT` — Railway sets this automatically
3. Deploy. Your server will be at `https://your-app.railway.app`.

## Security

- All requests to `/mcp` require `Authorization: Bearer <MCP_API_KEY>` when `MCP_API_KEY` is set.
- `/` and `/health` are public (no token needed).
- If `MCP_API_KEY` is not set, the server runs without auth — suitable for local use only.
- Never commit your `.env` file. It is in `.gitignore`.

## License

MIT
```

- [ ] **Step 2: Commit**

```bash
cd "/Users/iliazarikov/Documents/Python Projects/MCP" && git add README.md && git commit -m "docs(readme): rewrite for Streamable HTTP transport, Bearer auth, all 3 tools + prompt"
```

---

### Task 6: Smoke-test the server startup

**Files:** none — verification only

- [ ] **Step 1: Verify stdio mode starts cleanly**

```bash
cd "/Users/iliazarikov/Documents/Python Projects/MCP" && LINKEDIN_ACCESS_TOKEN=test_token timeout 3 .venv/bin/python -m linkedin_mcp.server 2>&1 || true
```

Expected: process starts (stdio waits for input), timeout kills it after 3 seconds with no import or startup errors.

- [ ] **Step 2: Verify HTTP mode starts and health endpoint responds**

Run in background, test, then kill:

```bash
cd "/Users/iliazarikov/Documents/Python Projects/MCP" && LINKEDIN_ACCESS_TOKEN=test_token PORT=18765 .venv/bin/python -m linkedin_mcp.server --http &
SERVER_PID=$!
sleep 2
curl -s http://localhost:18765/health
echo ""
curl -s -o /dev/null -w "health status: %{http_code}\n" http://localhost:18765/health
curl -s -o /dev/null -w "/mcp no auth status: %{http_code}\n" http://localhost:18765/mcp
curl -s -o /dev/null -w "/mcp with wrong token status: %{http_code}\n" -H "Authorization: Bearer wrong" http://localhost:18765/mcp
kill $SERVER_PID 2>/dev/null
```

Expected output:
```
LinkedIn MCP Server is running
health status: 200
/mcp no auth status: 200    # MCP_API_KEY not set → auth skipped, passthrough to MCP handler (may return 4xx from MCP itself, that's fine)
/mcp with wrong token status: 200   # same reason
```

> Note: when `MCP_API_KEY` is not set, middleware skips auth entirely — so `/mcp` falls through to FastMCP which may return 4xx for a non-MCP-protocol GET. That's expected. Set `MCP_API_KEY=testkey` in the env to test 401 rejection.

- [ ] **Step 3: Verify 401 when MCP_API_KEY is set**

```bash
cd "/Users/iliazarikov/Documents/Python Projects/MCP" && LINKEDIN_ACCESS_TOKEN=test_token MCP_API_KEY=mysecret PORT=18766 .venv/bin/python -m linkedin_mcp.server --http &
SERVER_PID=$!
sleep 2
curl -s -o /dev/null -w "no auth: %{http_code}\n" http://localhost:18766/mcp
curl -s -o /dev/null -w "wrong token: %{http_code}\n" -H "Authorization: Bearer wrong" http://localhost:18766/mcp
curl -s -o /dev/null -w "correct token: %{http_code}\n" -H "Authorization: Bearer mysecret" http://localhost:18766/mcp
curl -s -o /dev/null -w "health (open): %{http_code}\n" http://localhost:18766/health
kill $SERVER_PID 2>/dev/null
```

Expected output:
```
no auth: 401
wrong token: 401
correct token: 200
health (open): 200
```

- [ ] **Step 4: Commit verification note**

```bash
cd "/Users/iliazarikov/Documents/Python Projects/MCP" && git commit --allow-empty -m "chore: smoke-tested Streamable HTTP, ASGI auth middleware, and stdio mode"
```
