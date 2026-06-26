"""LangChain 1.0 tool for getting current date and time.

This tool provides the current date and time information to help the agent
answer time-related questions and filter information by date periods.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from langchain.tools import ToolRuntime, tool
from pydantic import BaseModel, Field

from kg_engine.config.settings import settings
from kg_engine.utils.context_tracker import AgentContext

logger = logging.getLogger(__name__)


def _get_current_datetime_dict(
    timezone: str | None = None,
) -> dict:
    """Get current datetime as structured dictionary.

    This helper function is used by both the get_current_datetime tool and the system prompt
    to ensure consistent datetime data across the application.

    Args:
        timezone: Optional IANA timezone name. If None, uses default from settings.

    Returns:
        Dictionary with structured datetime information.
    """
    # Determine timezone
    tz_str = timezone or settings.default_timezone
    try:
        tz = ZoneInfo(tz_str)
    except Exception:
        logger.warning("Invalid timezone %s, falling back to %s", tz_str, settings.default_timezone)
        tz = ZoneInfo(settings.default_timezone)
        tz_str = settings.default_timezone

    # Get current datetime in specified timezone
    now = datetime.now(tz)

    # Build structured response
    month_names = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]
    weekday_names = [
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
    ]

    result = {
        "iso_format": now.isoformat(),
        "timezone": tz_str,
        "timestamp": int(now.timestamp()),
        "month_name": month_names[now.month - 1],
        "weekday": weekday_names[now.weekday()],
    }

    return result


class GetDateTimeSchema(BaseModel):
    """
    Schema for getting current date and time information.

    This schema defines the input parameters for the get_current_datetime tool.
    Field descriptions are written for LLM understanding and MCP server compatibility.
    """

    timezone: str | None = Field(
        default=None,
        description="Optional timezone identifier (IANA timezone name, e.g., 'Europe/Moscow', "
        "'UTC', 'America/New_York'). If not specified, uses the default timezone "
        "from system settings. Use this to get time in a specific timezone. "
    )


@tool("get_current_datetime", args_schema=GetDateTimeSchema)
def get_current_datetime(
    timezone: str | None = None,
    runtime: ToolRuntime[AgentContext, None] | None = None,
) -> str:
    """Get the current date and time information.


    **Use when:**
    - User asks about current date, time, day of week, or month
    - User asks about time periods (e.g., "December release", "this month's updates/articles")
    - Need to filter or search information by periods, date ranges, or determine if a date is past/present/future
    - User asks "when" questions requiring current time context
    - Need to determine temporal context.

    **Examples:**
    - "что в декабрьском выпуске" → Get current date to determine if December is past/present/future, then search KB for release notes
    - "Что изменилось в этом месяце?" → Get current month, then search KB for recent documentation updates and feature announcements
    - "Когда был последний релиз?" → Get current date to compare with release dates found in KB articles

    **Timezone handling:**
    - By default, returns time in the default timezone from system settings
    - Specify a different timezone or UTC if the user asks for time in a specific location

    Returns:
        JSON with date/time information:
        {
          "iso_format": "2024-12-09T15:30:45+03:00",
          "timezone": "Europe/Moscow",
          "timestamp": 1702121445,
          "month_name": "December",
          "weekday": "Monday"
        }

    """
    try:
        # Build structured response using shared helper (handles timezone validation internally)
        result = _get_current_datetime_dict(timezone=timezone)
        return json.dumps(result, ensure_ascii=False, separators=(',', ':'))

    except Exception as exc:  # noqa: BLE001
        logger.error("Error getting current datetime: %s", exc, exc_info=True)
        return json.dumps(
            {
                "error": f"Failed to get current datetime: {str(exc)}",
                "datetime": None,
            },
            ensure_ascii=False,
        )

