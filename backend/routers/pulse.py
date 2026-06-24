from fastapi import APIRouter
import pandas as pd
from backend.config import get_settings

router = APIRouter(prefix="/api/pulse", tags=["Pulse Data"])

@router.get("/311")
def get_311_pulse_data(town_slug: str = "arlington-ma"):
    # In a real app, read from parquet. For this MVP, we return structured data
    # that mimics what the UI expects, to prevent breaking the charts if the parquet is missing columns.
    return {
        "kpi": {
            "total_open": 142,
            "avg_resolution_days": 3.2,
            "sentiment": "Frustrated",
            "resolved_this_week": 89
        },
        "hotspots": [
            {"title": "Noise Complaints", "location": "Capitol Square", "probability": "85%", "color": "bg-red-500"},
            {"title": "Pothole Damage", "location": "Appleton St", "probability": "72%", "color": "bg-amber-500"}
        ],
        "recent_complaints": [
            {"id": 1, "type": "Pothole", "location": "Mass Ave & Pleasant St", "status": "Open", "time": "2 hours ago", "sentiment": "Angry"},
            {"id": 2, "type": "Noise", "location": "Broadway & Medford St", "status": "In Progress", "time": "5 hours ago", "sentiment": "Frustrated"},
            {"id": 3, "type": "Trash", "location": "Lake St & Cross St", "status": "Open", "time": "1 day ago", "sentiment": "Neutral"}
        ]
    }

@router.get("/community")
def get_community_pulse_data(town_slug: str = "arlington-ma"):
    return {
        "live_activities": [
            {"id": 1, "name": "Arlington Farmers Market", "location": "Russell Common", "status": "Live Now", "busyness": 85, "trend": "increasing", "type": "market", "description": "Seasonal farm stand with high foot traffic."},
            {"id": 2, "name": "Town Day Preparations", "location": "Mass Ave (Center)", "status": "Upcoming", "busyness": 40, "trend": "stable", "type": "event", "description": "Roadway preparation. Expect partial closures."},
            {"id": 3, "name": "Spy Pond Park", "location": "Spy Pond", "status": "Active", "busyness": 65, "trend": "decreasing", "type": "park", "description": "Public park and recreation area."}
        ]
    }
