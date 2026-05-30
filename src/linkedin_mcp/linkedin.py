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
