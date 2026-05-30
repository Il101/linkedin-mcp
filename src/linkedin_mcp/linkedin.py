"""LinkedIn API Client"""

import os
import httpx
from typing import Optional


class LinkedInClient:
    """Client for LinkedIn API v2"""
    
    BASE_URL = "https://api.linkedin.com/v2"
    
    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token or os.getenv("LINKEDIN_ACCESS_TOKEN")
        if not self.access_token:
            raise ValueError("LINKEDIN_ACCESS_TOKEN is required")
        
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }
    
    async def get_profile(self) -> dict:
        """Get current user's LinkedIn profile"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/userinfo",
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()
    
    async def get_user_urn(self) -> str:
        """Get the user's URN for posting"""
        profile = await self.get_profile()
        return f"urn:li:person:{profile['sub']}"
    
    async def create_post(
        self,
        text: str,
        visibility: str = "PUBLIC",
    ) -> dict:
        """
        Create a text post on LinkedIn
        
        Args:
            text: The post content
            visibility: PUBLIC, CONNECTIONS, or LOGGED_IN
        
        Returns:
            Response from LinkedIn API
        """
        user_urn = await self.get_user_urn()
        
        payload = {
            "author": user_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": text
                    },
                    "shareMediaCategory": "NONE"
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": visibility
            }
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/ugcPosts",
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
            return {"success": True, "id": response.headers.get("x-restli-id", "unknown")}
    
    async def delete_post(self, post_id: str) -> dict:
        """
        Delete a LinkedIn post
        
        Args:
            post_id: The post URN (e.g., urn:li:share:123456 or urn:li:ugcPost:123456)
        
        Returns:
            Success status
        """
        # URL encode the URN
        encoded_id = post_id.replace(":", "%3A")
        
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{self.BASE_URL}/ugcPosts/{encoded_id}",
                headers=self.headers,
            )
            response.raise_for_status()
            return {"success": True, "deleted_id": post_id}
