import os
import httpx
import base64
import logging
import random

logger = logging.getLogger(__name__)

ZOOM_ACCOUNT_ID = os.getenv("ZOOM_ACCOUNT_ID")
ZOOM_CLIENT_ID = os.getenv("ZOOM_CLIENT_ID")
ZOOM_CLIENT_SECRET = os.getenv("ZOOM_CLIENT_SECRET")

async def get_zoom_access_token() -> str:
    """Get Server-to-Server OAuth Access Token."""
    url = f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={ZOOM_ACCOUNT_ID}"
    auth_str = f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}"
    b64_auth = base64.b64encode(auth_str.encode()).decode()

    headers = {
        "Authorization": f"Basic {b64_auth}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers)
        if response.status_code != 200:
            logger.error(f"Failed to get zoom token: {response.text}")
            return None
        return response.json().get("access_token")

async def create_zoom_meeting(topic: str, start_time: str, duration_mins: int = 60) -> dict:
    """
    Create a scheduled Zoom meeting via API.
    start_time format: 'YYYY-MM-DDTHH:MM:SSZ'
    """
    token = await get_zoom_access_token()
    if not token:
        logger.error("Could not obtain Zoom token!")
        return {}
    
    # We will use 'me' to create meeting for the app's owner, or an email if passed
    url = "https://api.zoom.us/v2/users/me/meetings"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Generate 6-digit passcode
    passcode = str(random.randint(100000, 999999))
    
    payload = {
        "topic": topic,
        "type": 2,  # Scheduled meeting
        "start_time": start_time,
        "duration": duration_mins,
        "password": passcode,
        "settings": {
            "join_before_host": True,
            "jbh_time": 0,
            "host_video": True,
            "participant_video": True,
            "mute_upon_entry": False,
            "waiting_room": False
        }
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload)
        if response.status_code not in (200, 201):
            logger.error(f"Failed to create zoom meeting: {response.text}")
            return {}
        
        data = response.json()
        return {
            "join_url": data.get("join_url"),
            "password": data.get("password"),
            "meeting_id": data.get("id"),
            "host_key": None # Since Server-to-Server doesn't always retrieve host_key directly without extra scopes
        }

async def end_zoom_meeting(meeting_id: str) -> bool:
    """End a Zoom meeting explicitly to permanently disable the join link."""
    token = await get_zoom_access_token()
    if not token:
        return False
    
    # 1. Force End to kick existing users
    end_url = f"https://api.zoom.us/v2/meetings/{meeting_id}/status"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {"action": "end"}
    
    async with httpx.AsyncClient() as client:
        # Put may fail if the meeting hasn't started, which is fine
        await client.put(end_url, headers=headers, json=payload)
        
        # 2. Delete the meeting
        del_url = f"https://api.zoom.us/v2/meetings/{meeting_id}"
        del_headers = {
            "Authorization": f"Bearer {token}"
        }
        response = await client.delete(del_url, headers=del_headers)
        if response.status_code == 204:
            logger.info(f"Successfully ended and deleted Zoom meeting {meeting_id}")
            return True
        logger.error(f"Failed to delete zoom meeting {meeting_id}: {response.text}")
        return False