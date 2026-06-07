import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
MEDIA_DIR = ROOT / "media"
CONFIG_PATH = ROOT / "config.json"
EXAMPLE_CONFIG_PATH = ROOT / "config.example.json"


def load_config():
    path = CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_CONFIG_PATH
    with path.open("r", encoding="utf-8") as f:
        config = json.load(f)
    config.setdefault("hashtags", [])
    config.setdefault("instagram", {})
    config.setdefault("auto_publish", {})
    apply_env(config)
    return config


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def apply_env(config):
    config["tabelog_reviewer_url"] = os.getenv(
        "TABELOG_REVIEWER_URL",
        os.getenv("TABELLOG_REVIEWER_URL", config.get("tabelog_reviewer_url", "")),
    )
    config["public_base_url"] = os.getenv("PUBLIC_BASE_URL", config.get("public_base_url", ""))
    config["storage_bucket"] = os.getenv("STORAGE_BUCKET", config.get("storage_bucket", ""))
    config["sync_token"] = os.getenv("SYNC_TOKEN", config.get("sync_token", ""))

    instagram = config.setdefault("instagram", {})
    instagram["graph_version"] = os.getenv("IG_GRAPH_VERSION", instagram.get("graph_version", "v24.0"))
    instagram["ig_user_id"] = os.getenv("IG_USER_ID", instagram.get("ig_user_id", ""))
    instagram["access_token"] = os.getenv("IG_ACCESS_TOKEN", instagram.get("access_token", ""))

    threads = config.setdefault("threads", {})
    threads["graph_base_url"] = os.getenv(
        "THREADS_GRAPH_BASE_URL",
        threads.get("graph_base_url", "https://graph.threads.net/v1.0"),
    )
    threads["user_id"] = os.getenv("THREADS_USER_ID", threads.get("user_id", ""))
    threads["access_token"] = os.getenv("THREADS_ACCESS_TOKEN", threads.get("access_token", ""))
    threads["instagram_profile_url"] = os.getenv(
        "THREADS_INSTAGRAM_PROFILE_URL",
        threads.get("instagram_profile_url", "https://www.instagram.com/mogmogtro112233/"),
    )
    threads["posts_per_day"] = int(os.getenv("THREADS_POSTS_PER_DAY", threads.get("posts_per_day", 10)))
    threads["auto_publish"] = env_bool("THREADS_AUTO_PUBLISH", threads.get("auto_publish", False))
    threads["auto_reply"] = env_bool("THREADS_AUTO_REPLY", threads.get("auto_reply", False))

    auto_publish = config.setdefault("auto_publish", {})
    auto_publish["feed"] = env_bool("AUTO_PUBLISH_FEED", auto_publish.get("feed", False))
    auto_publish["reel"] = env_bool("AUTO_PUBLISH_REEL", auto_publish.get("reel", False))
    auto_publish["story"] = env_bool("AUTO_PUBLISH_STORY", auto_publish.get("story", False))


def ensure_dirs():
    DATA_DIR.mkdir(exist_ok=True)
    MEDIA_DIR.mkdir(exist_ok=True)
