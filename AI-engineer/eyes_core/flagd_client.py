"""Client for the flagd-ui REST management interface."""
from __future__ import annotations

import httpx
from .config import FLAGD_UI_BASE

class FlagdClient:
    def __init__(self, base_url: str | None = None, timeout: float = 10.0):
        self.base = (base_url or FLAGD_UI_BASE).rstrip("/")
        self.timeout = timeout

    def _c(self) -> httpx.Client:
        return httpx.Client(base_url=self.base, timeout=self.timeout)

    def health(self) -> bool:
        try:
            with self._c() as c:
                r = c.get("/api/read")
                return r.status_code == 200
        except Exception:
            return False

    def read(self) -> dict:
        with self._c() as c:
            r = c.get("/api/read")
            r.raise_for_status()
            return r.json()

    def write(self, data: dict) -> None:
        with self._c() as c:
            r = c.post("/api/write", json={"data": data})
            r.raise_for_status()

    def get_flags(self) -> dict:
        return self.read().get("flags", {})

    def get_flag(self, key: str) -> dict | None:
        return self.get_flags().get(key)

    def set_variant(self, key: str, variant: str) -> tuple[str | None, dict]:
        """Read full config, set one flag's defaultVariant (and targeting if applicable), write back.
        Returns (previous_variant, full_config)."""
        cfg = self.read()
        flags = cfg.get("flags", {})
        if key not in flags:
            raise ValueError(f"Unknown flag: {key}")
        f = flags[key]
        variants = f.get("variants", {})
        if variant not in variants:
            raise ValueError(f"Invalid variant '{variant}' for {key}. Valid: {list(variants)}")
        # compute previous
        prev = f.get("defaultVariant")
        targeting = f.get("targeting")
        if isinstance(targeting, dict) and isinstance(targeting.get("if"), list) and len(targeting["if"]) >= 3:
            # productCatalogFailure style: set the "on" branch value
            # We set defaultVariant and also the targeting if-branch value to variant
            try:
                targeting["if"][1] = variant
            except Exception:
                pass
            prev_target = None
        # update defaultVariant
        f["defaultVariant"] = variant
        cfg["flags"][key] = f
        self.write(cfg)
        return prev, cfg

    def reset_flag(self, key: str, variant: str) -> None:
        self.set_variant(key, variant)
