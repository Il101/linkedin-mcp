"""LinkedIn MCP Server — FastMCP with Streamable HTTP transport"""

import asyncio
import os

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from .linkedin import LinkedInClient

# ---------------------------------------------------------------------------
# Secret path — security through URL obscurity.
# MCP_SECRET_PATH env var makes the endpoint /mcp/{secret} instead of /mcp,
# so the URL itself is the credential — compatible with claude.ai connectors
# which cannot set custom Authorization headers.
# ---------------------------------------------------------------------------
_secret = os.getenv("MCP_SECRET_PATH", "")
_mcp_path = f"/mcp/{_secret}" if _secret else "/mcp"


# ---------------------------------------------------------------------------
# FastMCP app
# ---------------------------------------------------------------------------
mcp = FastMCP(
    "linkedin-mcp",
    instructions="Publish, inspect, and delete LinkedIn posts on behalf of the authenticated user.",
    streamable_http_path=_mcp_path,
    host="0.0.0.0",
    stateless_http=True,
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

    try:
        async with LinkedInClient() as client:
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
    try:
        async with LinkedInClient() as client:
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

    try:
        async with LinkedInClient() as client:
            result = await client.delete_post(post_id)
            return f"Post deleted successfully. Deleted ID: {result['deleted_id']}"
    except Exception as e:
        raise RuntimeError(f"LinkedIn API error while deleting post: {e}") from e


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------
@mcp.prompt()
async def linkedin_post_creator(topic: str = "your expertise") -> str:
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
        port = int(os.getenv("PORT", 8000))
        if _secret:
            print(f"MCP endpoint: {_mcp_path}")
        else:
            print("WARNING: MCP_SECRET_PATH is not set — /mcp endpoint is public")
        uvicorn.run(mcp.streamable_http_app(), host="0.0.0.0", port=port)
    else:
        asyncio.run(mcp.run_stdio_async())


if __name__ == "__main__":
    main()
