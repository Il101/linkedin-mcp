# LinkedIn MCP — Modernization Design

**Date:** 2026-05-30  
**Status:** Approved  

## Goal

Bring the LinkedIn MCP server up to modern MCP standards: Streamable HTTP transport (spec 2025-03-26), proper Bearer-token authentication on all endpoints, tool annotations, structured error handling, and accurate documentation.

## Architecture

```
src/linkedin_mcp/
├── server.py     — FastMCP app, auth middleware, tool/prompt registration
└── linkedin.py   — LinkedInClient: shared httpx client, returns post URL
get_token.py      — OAuth helper, reads CLIENT_ID/SECRET from env
.env.example      — updated env vars
README.md         — rewritten for new transport and auth model
```

**Transport:** Streamable HTTP via `FastMCP`. Single endpoint `/mcp`. Clients POST requests and receive SSE streams in response. No separate `/sse` + `/messages` split. Stdio mode retained for Claude Desktop.

**Launch logic:**
- `RAILWAY_ENVIRONMENT` set or `--http` flag → `app = mcp.streamable_http_app()`, wrap in auth ASGI middleware, run with `uvicorn.run(app, host, port)`
- otherwise → stdio via `asyncio.run(mcp.run_stdio_async())`
- health routes registered with `@mcp.custom_route("/", ...)` and `@mcp.custom_route("/health", ...)` so they exist on the HTTP app
- `streamable_http_path` stays at default `/mcp`; `stateless_http` left default (stateful sessions)

## Authentication

A **pure ASGI middleware** (not `BaseHTTPMiddleware`) checks `Authorization: Bearer <MCP_API_KEY>` on every HTTP request before passing to the app.

> Rationale: Streamable HTTP returns responses as SSE streams. `BaseHTTPMiddleware` buffers response bodies and is known to break streaming responses in Starlette. A thin ASGI middleware inspects `scope["headers"]` and either forwards to the app or sends a `401` directly — it never touches the response stream.

- `/` and `/health` — open (no token required), registered via `@mcp.custom_route`
- all other paths — require valid Bearer token, return `401 {"error": "Unauthorized"}` otherwise
- `MCP_API_KEY` env var; if not set, auth is skipped (local/stdio use only, warning printed on startup)
- non-HTTP scopes (`lifespan`, `websocket`) pass through untouched

FastMCP's built-in `token_verifier`/`auth` is OAuth-2.0-Resource-Server oriented (validates tokens against an authorization server) — overkill for a single shared key, so we use the custom ASGI middleware instead.

## Environment Variables

| Variable | Purpose | Required |
|---|---|---|
| `LINKEDIN_ACCESS_TOKEN` | LinkedIn API access token | yes |
| `MCP_API_KEY` | Bearer token for MCP clients | for remote deploy |
| `PORT` | HTTP port (Railway sets automatically) | no (default 8000) |
| `LINKEDIN_CLIENT_ID` | OAuth app ID (get_token.py only) | no |
| `LINKEDIN_CLIENT_SECRET` | OAuth app secret (get_token.py only) | no |

`MCP_SECRET_PATH` is removed — replaced by `MCP_API_KEY`.

## Tools

### `post_to_linkedin`
- **title:** Publish LinkedIn Post
- **annotations:** `readOnlyHint: false`, `destructiveHint: false`
- **input:** `text` (string, required, max 3000 chars), `visibility` (enum PUBLIC|CONNECTIONS, default PUBLIC)
- **output:** `{id: string, url: string}` — `url` = `https://www.linkedin.com/feed/update/{urn}`
- **errors:** raises `ValueError` on empty text, length violation, or API failure

### `get_linkedin_profile`
- **title:** Get LinkedIn Profile
- **annotations:** `readOnlyHint: true`, `destructiveHint: false`
- **input:** none
- **output:** text with name, email, LinkedIn ID
- **errors:** raises on API failure

### `delete_linkedin_post`
- **title:** Delete LinkedIn Post
- **annotations:** `readOnlyHint: false`, `destructiveHint: true`
- **input:** `post_id` (string, required, must start with `urn:li:`)
- **output:** confirmation text with deleted ID
- **errors:** raises on invalid URN format or API failure

## Prompt

`linkedin_post_creator` — unchanged, correct as-is.

## Error Handling

FastMCP converts raised exceptions to `isError: true` responses automatically. No more `return [TextContent("Error: ...")]` — just `raise ValueError("message")`. Raw httpx details stay in server logs only.

## LinkedInClient changes

- Shared `httpx.AsyncClient` per instance (not recreated per call)
- `create_post` returns `{id, url}` where `url` is the full LinkedIn post URL
- Remove `LOGGED_IN` from docstring (not exposed in schema)
- URL encoding for `delete_post` uses `urllib.parse.quote` instead of manual `.replace`

## get_token.py

`CLIENT_ID` and `CLIENT_SECRET` read from `os.getenv("LINKEDIN_CLIENT_ID")` and `os.getenv("LINKEDIN_CLIENT_SECRET")`. Script prints a clear error if either is missing.

## Client Configuration

**Claude Desktop (stdio):**
```json
{
  "mcpServers": {
    "linkedin": {
      "command": "linkedin-mcp",
      "env": {"LINKEDIN_ACCESS_TOKEN": "your_token"}
    }
  }
}
```

**Remote MCP client (HTTP/Streamable):**
```
URL: https://your-app.railway.app/mcp
Authorization: Bearer <MCP_API_KEY>
```

## Out of Scope

- Token refresh / LinkedIn OAuth refresh flow (token lifetime ~60 days, documented in README)
- Image/video post support
- Rate limiting middleware
- Tests (separate concern)
