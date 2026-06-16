# LinkedIn MCP Server

MCP server for publishing, inspecting, and deleting LinkedIn posts via AI assistants (Claude, Cursor, Windsurf, Cline).

Uses the **Streamable HTTP** transport (MCP spec 2025-03-26) for remote deployments and **stdio** for local use with Claude Desktop.

## What this demonstrates

- A FastMCP server exposing **typed tools** with proper [tool annotations](https://modelcontextprotocol.io/docs/concepts/tools) (`readOnlyHint`, `destructiveHint`, `openWorldHint`).
- **Two transports** from one codebase: Streamable HTTP (remote) and stdio (Claude Desktop).
- An async `httpx` client for the LinkedIn API v2 with input validation and clean error handling.
- A one-command deploy to Railway via Docker.

## Tools

| Tool | What it does | Side effects |
|---|---|---|
| `post_to_linkedin` | Publish a text post (up to 3000 chars, `PUBLIC` or `CONNECTIONS` visibility) | Writes |
| `get_linkedin_profile` | Get current user's name, email, and LinkedIn ID | Read-only |
| `delete_linkedin_post` | Delete a post by URN — **irreversible** | Destructive |

## Prompt

`linkedin_post_creator` — a guided prompt for composing LinkedIn posts. Accepts an optional `topic` argument.

## Setup

Requires **Python 3.10+**.

### 1. Create a LinkedIn App

Go to the [LinkedIn Developer Portal](https://www.linkedin.com/developers/apps), create an app, and add these OAuth 2.0 scopes:

- `openid` — retrieve user ID
- `profile` — retrieve user name
- `w_member_social` — publish and delete posts

Add `http://localhost:8000/callback` as an authorized redirect URL (used by `get_token.py`).

### 2. Install

```bash
pip install -e .
```

### 3. Get a LinkedIn access token

```bash
# Set your OAuth app credentials in the environment first:
export LINKEDIN_CLIENT_ID="your_client_id"
export LINKEDIN_CLIENT_SECRET="your_client_secret"

python get_token.py
# Follow the browser prompt — your access token will be printed.
# Note: LinkedIn access tokens expire after ~60 days; rerun this script to renew.
```

### 4. Configure environment

```bash
cp .env.example .env
# Edit .env — fill in LINKEDIN_ACCESS_TOKEN (and MCP_SECRET_PATH for remote deploys)
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

Add a remote MCP server pointing at the secret endpoint:

```
URL: https://your-app.railway.app/mcp/<MCP_SECRET_PATH>
```

No custom headers are required — the secret is embedded in the URL itself, which keeps it compatible with connectors (e.g. claude.ai) that cannot set an `Authorization` header.

## Deploy on Railway

1. Create a new project on [Railway](https://railway.app) and connect this repository.
2. Set these environment variables:
   - `LINKEDIN_ACCESS_TOKEN` — your LinkedIn access token
   - `MCP_SECRET_PATH` — a secret path segment protecting the endpoint (`openssl rand -hex 32`)
   - `PORT` — Railway sets this automatically
3. Deploy. Your MCP endpoint will be `https://your-app.railway.app/mcp/<MCP_SECRET_PATH>`.

## Security

- The MCP endpoint is served at `/mcp/<MCP_SECRET_PATH>` — the secret path acts as the credential ("security through URL obscurity"). Treat the full URL as a secret.
- `/` and `/health` are public (no secret needed) so platform health checks work.
- If `MCP_SECRET_PATH` is **not** set, the endpoint is the bare `/mcp` and is **public** — suitable for local/stdio use only. The server prints a warning on startup in this case.
- Always serve remote deployments over HTTPS (Railway does this by default).
- Never commit your `.env` file. It is in `.gitignore`.

## License

MIT
