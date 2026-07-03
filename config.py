import json
import os

from dotenv import load_dotenv

load_dotenv()


def require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value == "":
        raise RuntimeError(f"Missing {name} environment variable.")
    return value


def parse_guild_configs(raw: str) -> dict[str, dict[str, int]]:
    if raw == "":
        return {}

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"GUILD_CONFIGS must be valid JSON: {exc.msg}") from exc

    if not isinstance(parsed, dict):
        raise RuntimeError("GUILD_CONFIGS must be a JSON object keyed by guild id.")

    return parsed


def get_fallback_channel_ids() -> tuple[int, int]:
    setup_channel_id = int(os.getenv("SETUP_CHANNEL_ID", "0"))
    radio_category_id = int(os.getenv("RADIO_CATEGORY_ID", "0"))
    return setup_channel_id, radio_category_id


def get_guild_config(guild_id: int | None = None) -> tuple[int, int]:
    setup_channel_id, radio_category_id = get_fallback_channel_ids()

    if guild_id is None:
        if setup_channel_id == 0 or radio_category_id == 0:
            raise RuntimeError("Missing SETUP_CHANNEL_ID or RADIO_CATEGORY_ID environment variable.")
        return setup_channel_id, radio_category_id

    raw = os.getenv("GUILD_CONFIGS", "").strip()
    if not raw:
        if setup_channel_id == 0 or radio_category_id == 0:
            raise RuntimeError("Missing GUILD_CONFIGS or fallback SETUP_CHANNEL_ID/RADIO_CATEGORY_ID environment variables.")
        return setup_channel_id, radio_category_id

    guild_configs = parse_guild_configs(raw)
    guild_key = str(guild_id)
    if guild_key not in guild_configs:
        if setup_channel_id == 0 or radio_category_id == 0:
            raise RuntimeError(f"No GUILD_CONFIGS entry for guild {guild_id} and no fallback channel IDs were provided.")
        return setup_channel_id, radio_category_id

    guild_config = guild_configs[guild_key]
    if not isinstance(guild_config, dict):
        raise RuntimeError(f"GUILD_CONFIGS[{guild_key}] must be an object with setup_channel_id and radio_category_id.")

    if "setup_channel_id" not in guild_config or "radio_category_id" not in guild_config:
        raise RuntimeError(f"GUILD_CONFIGS[{guild_key}] must include both setup_channel_id and radio_category_id.")

    try:
        report_setup_channel_id = int(guild_config["setup_channel_id"])
        report_radio_category_id = int(guild_config["radio_category_id"])
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"GUILD_CONFIGS[{guild_key}] channel IDs must be integers.") from exc

    return report_setup_channel_id, report_radio_category_id


TOKEN = require_env("DISCORD_TOKEN")
DELETE_DELAY_SECONDS = int(os.getenv("DELETE_DELAY_SECONDS", "30"))
