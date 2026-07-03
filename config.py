import json
import os

from dotenv import load_dotenv

load_dotenv()


def require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value == "":
        raise RuntimeError(f"Missing {name} environment variable.")
    return value


def get_guild_config(guild_id: int | None = None) -> tuple[int, int]:
    fallback_setup_channel_id = int(os.getenv("SETUP_CHANNEL_ID", "0"))
    fallback_radio_category_id = int(os.getenv("RADIO_CATEGORY_ID", "0"))

    if guild_id is None:
        if fallback_setup_channel_id == 0 or fallback_radio_category_id == 0:
            raise RuntimeError("Missing SETUP_CHANNEL_ID or RADIO_CATEGORY_ID environment variable.")
        return fallback_setup_channel_id, fallback_radio_category_id

    guild_configs_raw = os.getenv("GUILD_CONFIGS", "").strip()
    if not guild_configs_raw:
        if fallback_setup_channel_id == 0 or fallback_radio_category_id == 0:
            raise RuntimeError("Missing GUILD_CONFIGS or fallback SETUP_CHANNEL_ID/RADIO_CATEGORY_ID environment variables.")
        return fallback_setup_channel_id, fallback_radio_category_id

    try:
        guild_configs = json.loads(guild_configs_raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GUILD_CONFIGS must be valid JSON.") from exc

    if not isinstance(guild_configs, dict):
        raise RuntimeError("GUILD_CONFIGS must be a JSON object keyed by guild id.")

    guild_key = str(guild_id)
    guild_config = guild_configs.get(guild_key)

    if not isinstance(guild_config, dict):
        if fallback_setup_channel_id == 0 or fallback_radio_category_id == 0:
            raise RuntimeError(f"No config found for guild {guild_id} and no fallback channel IDs were provided.")
        return fallback_setup_channel_id, fallback_radio_category_id

    setup_channel_id = guild_config.get("setup_channel_id")
    radio_category_id = guild_config.get("radio_category_id")

    if setup_channel_id is None or radio_category_id is None:
        raise RuntimeError(f"Guild config for {guild_id} must include both setup_channel_id and radio_category_id.")

    return int(setup_channel_id), int(radio_category_id)


TOKEN = require_env("DISCORD_TOKEN")
DELETE_DELAY_SECONDS = int(os.getenv("DELETE_DELAY_SECONDS", "30"))
