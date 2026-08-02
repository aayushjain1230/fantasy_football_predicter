from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


APP_VERSION = "0.6.0"
ROOT_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class SettingInfo:
    name: str
    classification: str
    required: bool = False
    secret: bool = False
    local_only: bool = False
    cloud_safe: bool = True


SETTINGS_REGISTRY = [
    SettingInfo("APP_ENV", "Public", cloud_safe=True),
    SettingInfo("FOURTH_DOWN_DEMO_MODE", "Public", cloud_safe=True),
    SettingInfo("CURRENT_NFL_SEASON", "Public", cloud_safe=True),
    SettingInfo("DATABASE_URL", "Local-only", local_only=True, cloud_safe=False),
    SettingInfo("MULTI_USER_MODE", "Public", cloud_safe=True),
    SettingInfo("MAX_REQUEST_BYTES", "Public", cloud_safe=True),
    SettingInfo("ALLOWED_ORIGINS", "Public", cloud_safe=True),
    SettingInfo("ODDS_API_KEY", "Optional secret", secret=True, cloud_safe=True),
    SettingInfo("ENABLE_MARKET_ADJUSTMENTS", "Public", cloud_safe=True),
    SettingInfo("OPENWEATHER_API_KEY", "Optional secret", secret=True, cloud_safe=True),
    SettingInfo("DIGEST_WEBHOOK_URL", "Optional secret", secret=True, cloud_safe=True),
    SettingInfo("ESPN_S2", "Local-only secret", secret=True, local_only=True, cloud_safe=False),
    SettingInfo("ESPN_SWID", "Local-only secret", secret=True, local_only=True, cloud_safe=False),
]


@dataclass(frozen=True)
class AppConfig:
    environment: str = "local"
    demo_mode_enabled: bool = True
    current_nfl_season: int = 2026
    deployment_mode: str = "streamlit"
    database_url: str = "sqlite:///./fourth_down.db"
    multi_user_mode: bool = False
    max_request_bytes: int = 1_048_576
    allowed_origins: tuple[str, ...] = ("http://localhost:3000", "http://127.0.0.1:3000")
    odds_api_key: str | None = None
    enable_market_adjustments: bool = False
    openweather_api_key: str | None = None
    digest_webhook_url: str | None = None
    espn_s2: str | None = None
    espn_swid: str | None = None
    model_artifact_dir: Path = ROOT_DIR / "models" / "projections" / "latest"
    draft_artifact_dir: Path = ROOT_DIR / "models" / "draft" / "latest"
    data_dir: Path = ROOT_DIR / "data"
    simulation_default: int = 1000
    simulation_max: int = 5000
    provider_timeout_seconds: float = 15.0
    provider_retries: int = 1
    player_search_limit: int = 50

    @property
    def cloud_mode(self) -> bool:
        return self.environment.lower() in {"streamlit", "cloud", "production"}


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(value: str | None, default: int, low: int, high: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except ValueError:
        parsed = default
    return max(low, min(high, parsed))


def load_config(overrides: Mapping[str, str] | None = None) -> AppConfig:
    values = {**os.environ, **(dict(overrides) if overrides else {})}
    origins = tuple(x.strip().rstrip("/") for x in values.get("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if x.strip())
    return AppConfig(
        environment=values.get("APP_ENV", values.get("FOURTH_DOWN_ENV", "local")),
        demo_mode_enabled=_bool(values.get("FOURTH_DOWN_DEMO_MODE"), True),
        current_nfl_season=_int(values.get("CURRENT_NFL_SEASON"), 2026, 2020, 2035),
        deployment_mode=values.get("DEPLOYMENT_MODE", "streamlit"),
        database_url=values.get("DATABASE_URL", "sqlite:///./fourth_down.db"),
        multi_user_mode=_bool(values.get("MULTI_USER_MODE"), False),
        max_request_bytes=_int(values.get("MAX_REQUEST_BYTES"), 1_048_576, 16_384, 8_388_608),
        allowed_origins=origins or ("http://localhost:3000", "http://127.0.0.1:3000"),
        odds_api_key=values.get("ODDS_API_KEY") or None,
        enable_market_adjustments=_bool(values.get("ENABLE_MARKET_ADJUSTMENTS"), False),
        openweather_api_key=values.get("OPENWEATHER_API_KEY") or None,
        digest_webhook_url=values.get("DIGEST_WEBHOOK_URL") or None,
        espn_s2=values.get("ESPN_S2") or None,
        espn_swid=values.get("ESPN_SWID") or None,
    )


def validate_config(config: AppConfig) -> list[str]:
    warnings: list[str] = []
    if config.multi_user_mode and config.database_url.startswith("sqlite:///"):
        warnings.append("MULTI_USER_MODE cannot rely on SQLite; local persistence is disabled for cloud multi-user guarantees.")
    if config.cloud_mode and (config.espn_s2 or config.espn_swid):
        warnings.append("ESPN cookies are local-only and should not be configured in shared Streamlit cloud deployments.")
    if not config.model_artifact_dir.exists():
        warnings.append("Projection artifacts are unavailable; projections will use labeled fallback.")
    if not config.draft_artifact_dir.exists():
        warnings.append("Draft artifacts are unavailable; draft intelligence will be disabled or fallback-labeled.")
    return warnings


def config_summary(config: AppConfig | None = None) -> list[dict[str, object]]:
    config = config or load_config()
    present = {
        "APP_ENV": config.environment,
        "FOURTH_DOWN_DEMO_MODE": config.demo_mode_enabled,
        "CURRENT_NFL_SEASON": config.current_nfl_season,
        "DATABASE_URL": bool(config.database_url),
        "MULTI_USER_MODE": config.multi_user_mode,
        "MAX_REQUEST_BYTES": config.max_request_bytes,
        "ALLOWED_ORIGINS": len(config.allowed_origins),
        "ODDS_API_KEY": bool(config.odds_api_key),
        "ENABLE_MARKET_ADJUSTMENTS": config.enable_market_adjustments,
        "OPENWEATHER_API_KEY": bool(config.openweather_api_key),
        "DIGEST_WEBHOOK_URL": bool(config.digest_webhook_url),
        "ESPN_S2": bool(config.espn_s2),
        "ESPN_SWID": bool(config.espn_swid),
    }
    rows = []
    for item in SETTINGS_REGISTRY:
        rows.append(
            {
                "Setting": "Local ESPN cookie" if item.name in {"ESPN_S2", "ESPN_SWID"} else item.name,
                "Classification": item.classification,
                "Required": item.required,
                "Secret": item.secret,
                "Local only": item.local_only,
                "Cloud safe": item.cloud_safe,
                "Configured": bool(present.get(item.name)),
            }
        )
    return rows


CONFIG = load_config()
