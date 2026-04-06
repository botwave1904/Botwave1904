#!/usr/bin/env python3
"""
Gatekeeper module for Botwave Empire.

- Loads subscription tiers from JSON (default: subscription_tiers.json)
- Loads per-agent configuration from trade_configs.yaml (path configurable)
- Provides Gatekeeper.require(...) decorator to guard functions
- Emits structured JSON errors to stderr for the Electron UI to interpret
- Includes a simple in-memory Rate_Limiter for APPRENTICE limits (pluggable for Redis later)
"""

from functools import wraps
import threading
import time
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

from pathlib import Path as _GKPath

def _resolve_config_path(filename):
    """Find config file relative to project root, not cwd."""
    candidates = [
        _GKPath(filename),  # cwd
        _GKPath(__file__).parent.parent / 'config' / filename,  # src/../config/
        _GKPath(__file__).parent.parent / filename,  # project root
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return filename  # fallback to original (will error with useful message)

try:
    import yaml
except Exception as e:
    raise ImportError("PyYAML is required: pip install pyyaml") from e

# Configure module-level logger (library-style)
logger = logging.getLogger("botwave.gatekeeper")
if not logger.handlers:
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    logger.addHandler(h)
logger.setLevel(logging.INFO)


class GatekeeperError(Exception):
    """Base exception for gatekeeper errors."""

    def __init__(self, code: str, message: str, action: str = None, required_tier: str = None, current_tier: str = None, extra: dict = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.action = action
        self.required_tier = required_tier
        self.current_tier = current_tier
        self.extra = extra or {}
        self.timestamp = datetime.utcnow().isoformat() + "Z"

    def to_dict(self):
        d = {
            "error": self.message,
            "error_code": self.code,
            "action": self.action or "NONE",
            "required_tier": self.required_tier or "",
            "current_tier": self.current_tier or "",
            "timestamp": self.timestamp,
            "details": self.extra
        }
        return d

    def emit_json_to_stderr(self):
        payload = self.to_dict()
        # Ensure a JSON object appears on stderr exactly once for UI consumption:
        sys.stderr.write(json.dumps(payload) + "\n")
        # Also log it so it's preserved in server logs:
        logger.warning("Gatekeeper error emitted: %s", json.dumps(payload))


class RateLimiter:
    """
    Simple in-memory Rate Limiter with weekly reset.
    - Tracks usage per license_key and feature_name.
    - Thread-safe.
    - Intended as a pluggable stub; replace storage with Redis for multi-process environments.
    """

    def __init__(self, now_fn=None):
        # { license_key: {feature: {"count": int, "window_start": timestamp}}}
        self._data = {}
        self._lock = threading.RLock()
        self._now = now_fn or (lambda: datetime.utcnow())

    def _start_of_week(self, dt):
        # ISO week start (Monday). We'll use Monday 00:00 UTC as week boundary.
        # Find Monday of current week
        monday = dt - timedelta(days=dt.weekday())
        return datetime(monday.year, monday.month, monday.day)

    def check_and_consume(self, license_key: str, feature: str, allowed: int) -> bool:
        """
        Returns True if consumed (allowed), or False if limit reached.
        """
        if allowed is None:
            return True  # no limit

        now = self._now()
        start = self._start_of_week(now)

        with self._lock:
            lic = self._data.setdefault(license_key, {})
            entry = lic.get(feature)
            if entry is None or entry["window_start"] < start:
                # reset window
                lic[feature] = {"count": 0, "window_start": start}
                entry = lic[feature]

            if entry["count"] < allowed:
                entry["count"] += 1
                logger.debug("RateLimiter: license=%s feature=%s consumed=%d/%d", license_key, feature, entry["count"], allowed)
                return True
            else:
                logger.debug("RateLimiter: license=%s feature=%s limit_reached=%d/%d", license_key, feature, entry["count"], allowed)
                return False

    def get_usage(self, license_key: str, feature: str):
        with self._lock:
            return self._data.get(license_key, {}).get(feature, {"count": 0, "window_start": None})


class Gatekeeper:
    def __init__(self, tiers_path: str = None, config_path: str = None, rate_limiter: RateLimiter = None):
        self.tiers_path = Path(tiers_path or _resolve_config_path("subscription_tiers.json"))
        self.config_path = Path(config_path or _resolve_config_path("trade_configs.yaml"))
        self._tiers = self._load_tiers()
        self.rate_limiter = rate_limiter or RateLimiter()
        # Cache for configs loaded per-path for performance; TTL could be added
        self._config_cache = {}
        self._config_mtime = None

    def _load_tiers(self):
        try:
            with open(self.tiers_path, "r", encoding="utf-8") as fh:
                tiers = json.load(fh)
            logger.debug("Loaded tiers from %s", self.tiers_path)
            return tiers
        except Exception as e:
            logger.error("Failed to load tiers file %s: %s", self.tiers_path, e)
            raise

    def _load_config(self):
        """
        Loads trade_configs.yaml which is expected to contain per-agent license info, e.g.:
        license_key: "ABC123"
        tier_level: "TRADESMAN"
        allowed_trades: ["Plumbing"]
        """
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        stat = self.config_path.stat()
        # reload if modified
        if self._config_mtime != stat.st_mtime:
            with open(self.config_path, "r", encoding="utf-8") as fh:
                cfg = yaml.safe_load(fh) or {}
            self._config_cache = cfg
            self._config_mtime = stat.st_mtime
            logger.debug("Loaded trade config from %s", self.config_path)
        return self._config_cache

    def _emit_upgrade_required(self, required_tier: str, current_tier: str, message: str, extra: dict = None):
        err = GatekeeperError(
            code="UPGRADE_REQUIRED",
            message=message,
            action="BUY_UPGRADE",
            required_tier=required_tier,
            current_tier=current_tier,
            extra=extra,
        )
        err.emit_json_to_stderr()
        return err

    def require(self, required_features=None, allowed_trades=None):
        """
        Decorator factory.

        required_features: list of capability names (strings) required by the guarded function.
          e.g. ["Multi-Trade_Oversight"] or ["botwave_gc_core.py"] or ["GC_OVERSIGHT"]

        allowed_trades: optional. If specified, the function is only allowed for those trades or
        requires the license to include them.

        The decorator will:
          - load trade_configs.yaml and validate presence of license_key and tier_level
          - enforce tier-based feature access using subscription_tiers.json
          - enforce trade-specific access for TRADESMAN (they must have the exact trade in their allowed_trades)
          - apply APPRENTICE rate limits for features with per-tier limits
        """
        required_features = required_features or []

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    cfg = self._load_config()
                    license_key = cfg.get("license_key")
                    tier_level = cfg.get("tier_level")
                    allowed_trades_cfg = cfg.get("allowed_trades", [])
                except FileNotFoundError:
                    e = GatekeeperError(code="INVALID_LICENSE", message="Missing trade_configs.yaml", action="CONTACT_SUPPORT")
                    e.emit_json_to_stderr()
                    raise

                if not license_key or not tier_level:
                    e = GatekeeperError(code="INVALID_LICENSE", message="license_key or tier_level missing", action="CONTACT_SUPPORT")
                    e.emit_json_to_stderr()
                    raise e

                tier_spec = self._tiers.get(tier_level)
                if not tier_spec:
                    e = GatekeeperError(code="UNKNOWN_TIER", message=f"Unknown tier: {tier_level}", action="CONTACT_SUPPORT")
                    e.emit_json_to_stderr()
                    raise e

                # Enforce required features
                # If required feature is a special GC oversight capability, treat specially for TRADESMAN
                for feat in required_features:
                    # First, check if the tier declares the feature
                    features = tier_spec.get("features", [])
                    # For TRADESMAN, they may have TradeModule but only for allowed trade(s)
                    if tier_level == "TRADESMAN" and "Multi-Trade_Oversight" in (feat,):
                        # TRADESMAN cannot access multi-trade oversight
                        msg = f"Tier {tier_level} cannot access {feat}; upgrade required."
                        err = self._emit_upgrade_required(required_tier="GC_ULTIMATE", current_tier=tier_level, message=msg, extra={"feature": feat})
                        raise err
                    # Generic check: if the feature isn't in the tier features then deny
                    # Special case: "TradeModule" indicates per-trade modules (Trademan can have 1 allowed trade)
                    if feat == "TradeModule":
                        if tier_level == "TRADESMAN":
                            # Ensure the called function's trade (if provided) is allowed.
                            # Caller should optionally pass 'trade_name' keyword arg or decorator was given allowed_trades
                            trade_name = kwargs.get("trade_name") or (allowed_trades[0] if allowed_trades else None)
                            if not trade_name:
                                # cannot determine which trade is requested
                                err = GatekeeperError(code="TRADE_REQUIRED", message="Trade name required for TradeModule access", action="BAD_REQUEST", current_tier=tier_level)
                                err.emit_json_to_stderr()
                                raise err
                            if trade_name not in allowed_trades_cfg:
                                # TRADESMAN trying to access a trade they don't own
                                err = GatekeeperError(code="UPGRADE_REQUIRED", message=f"License does not include trade '{trade_name}'.", action="BUY_UPGRADE", required_tier="TRADESMAN", current_tier=tier_level, extra={"requested_trade": trade_name})
                                err.emit_json_to_stderr()
                                raise err
                        else:
                            # Non-TRADESMAN who owns TradeModule: allowed if feature present
                            if "TradeModule" not in features:
                                err = GatekeeperError(code="UPGRADE_REQUIRED", message=f"Tier {tier_level} lacks TradeModule access.", action="BUY_UPGRADE", required_tier="TRADESMAN", current_tier=tier_level)
                                err.emit_json_to_stderr()
                                raise err
                    else:
                        # Normal feature presence check
                        if feat not in features:
                            # If a TRADESMAN tries to access GC oversight (alias), ensure explicit UPGRADE_REQUIRED JSON logged
                            if tier_level == "TRADESMAN" and feat in ("Multi-Trade_Oversight", "GC_OVERSIGHT", "botwave_gc_core.py"):
                                msg = f"Tier {tier_level} cannot access {feat}; upgrade required."
                                err = self._emit_upgrade_required(required_tier="GC_ULTIMATE", current_tier=tier_level, message=msg, extra={"feature": feat})
                                raise err
                            err = GatekeeperError(code="UPGRADE_REQUIRED", message=f"Tier {tier_level} missing feature {feat}", action="BUY_UPGRADE", required_tier="GC_ULTIMATE", current_tier=tier_level)
                            err.emit_json_to_stderr()
                            raise err

                # Apply rate-limits for APPRENTICE
                if tier_level == "APPRENTICE":
                    # check limits defined in tiers file
                    limits = tier_spec.get("limits", {})
                    for feat in required_features:
                        feat_limits = limits.get(feat) or {}
                        scans_per_week = feat_limits.get("scans_per_week")
                        if scans_per_week is not None:
                            allowed = scans_per_week
                            ok = self.rate_limiter.check_and_consume(license_key, feat, allowed)
                            if not ok:
                                err = GatekeeperError(code="RATE_LIMIT_EXCEEDED", message=f"Rate limit exceeded for feature {feat}", action="UPGRADE_REQUIRED", required_tier="TRADESMAN", current_tier=tier_level, extra={"feature": feat})
                                err.emit_json_to_stderr()
                                raise err

                # All checks passed; proceed
                logger.debug("Gatekeeper: access granted for license=%s tier=%s func=%s", license_key, tier_level, func.__name__)
                return func(*args, **kwargs)

            return wrapper
        return decorator


# Example convenience instance used by the rest of the app:
_default_gatekeeper = Gatekeeper()


def require(*required_features, allowed_trades=None):
    """
    Module-level decorator for convenience.
    Example:
      @require("Inspector")
      def run_inspector(...): ...
    """
    return _default_gatekeeper.require(required_features, allowed_trades=allowed_trades)


# Expose classes for unit testing and injection
__all__ = ["Gatekeeper", "GatekeeperError", "RateLimiter", "require"]