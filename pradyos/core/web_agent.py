from __future__ import annotations

import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pradyos.core.guardrail import GuardrailGate
    from pradyos.core.snapshot_store import SnapshotStore


@dataclass
class WebResult:
    url: str
    status_code: int
    body_text: str
    content_type: str
    fetched_at: float
    error: str

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "status_code": self.status_code,
            "body_text": self.body_text,
            "content_type": self.content_type,
            "fetched_at": self.fetched_at,
            "error": self.error,
        }


class _LinkParser(HTMLParser):
    """Collect href values from <a> tags."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "a":
            return
        for k, v in attrs:
            if k.lower() == "href" and v:
                self.links.append(v)


class WebAgent:
    def __init__(
        self,
        guardrail_gate: GuardrailGate | None = None,
        snapshot_store: SnapshotStore | None = None,
        max_age: int = 3600,
        timeout: int = 10,
    ) -> None:
        self._gate = guardrail_gate
        self._store = snapshot_store
        self._max_age = max_age
        self._timeout = timeout
        self._lock = threading.Lock()
        self._cache_ns = "web_cache"

    # ── guardrail helper ─────────────────────────────────────────────────────

    def _check_guardrail(
        self,
        action: str,
        risk_level: str,
        context: dict,
    ) -> tuple[bool, str]:
        """Return (approved, reason). True/'' if no gate or auto-approved."""
        if self._gate is None:
            return True, ""

        # Preferred: gate.evaluate(action, risk_level, context) → object with .decision/.reason
        if hasattr(self._gate, "evaluate"):
            try:
                result = self._gate.evaluate(action=action, risk_level=risk_level, context=context)
                if hasattr(result, "decision"):
                    return result.decision == "approved", getattr(result, "reason", "") or ""
                if isinstance(result, dict):
                    return result.get("decision") == "approved", result.get("reason", "") or ""
                return bool(result), ""
            except Exception as exc:
                return False, str(exc)

        # Fallback: real Phase 43 GuardrailGate uses .submit() + AUTO_APPROVE_LEVELS
        if hasattr(self._gate, "submit"):
            try:
                from pradyos.core.guardrail import RiskLevel

                risk_enum = RiskLevel(risk_level)
                reason = None if risk_enum.value in ("safe", "low") else f"web_agent: {action}"
                self._gate.submit(
                    action=action,
                    risk_level=risk_enum,
                    payload=context,
                    reason=reason,
                )
                auto_levels = getattr(self._gate, "AUTO_APPROVE_LEVELS", set())
                if risk_enum in auto_levels:
                    return True, ""
                return False, f"action queued for {risk_level} approval"
            except Exception as exc:
                return False, str(exc)

        return True, ""

    # ── fetch ────────────────────────────────────────────────────────────────

    def fetch(self, url: str) -> WebResult:
        # 1. Cache check
        now = time.time()
        if self._store is not None:
            try:
                snap = self._store.get(self._cache_ns, url)
                if snap is not None:
                    saved_at = float(snap.data.get("fetched_at", 0))
                    if (now - saved_at) < self._max_age:
                        return WebResult(**snap.data)
            except Exception:
                pass

        # 2. Guardrail check
        approved, reason = self._check_guardrail(
            action="web_fetch", risk_level="low", context={"url": url}
        )
        if not approved:
            return WebResult(
                url=url,
                status_code=0,
                body_text="",
                content_type="",
                fetched_at=time.time(),
                error=f"blocked by guardrail: {reason}",
            )

        # 3. Perform HTTP fetch
        result = self._raw_fetch(url)

        # 4. Save to cache
        if self._store is not None:
            try:
                with self._lock:
                    self._store.save(self._cache_ns, url, result.to_dict())
            except Exception:
                pass

        return result

    def _raw_fetch(self, url: str) -> WebResult:
        fetched_at = time.time()
        try:
            with urllib.request.urlopen(url, timeout=self._timeout) as resp:
                raw = resp.read()
                status = getattr(resp, "status", 200)
                ctype = resp.headers.get("Content-Type", "") if hasattr(resp, "headers") else ""
            body = (
                raw.decode("utf-8", errors="replace")
                if isinstance(raw, bytes | bytearray)
                else str(raw)
            )
            return WebResult(
                url=url,
                status_code=int(status),
                body_text=body,
                content_type=ctype,
                fetched_at=fetched_at,
                error="",
            )
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            except Exception:
                pass
            return WebResult(
                url=url,
                status_code=exc.code,
                body_text=body,
                content_type="",
                fetched_at=fetched_at,
                error=str(exc),
            )
        except Exception as exc:
            return WebResult(
                url=url,
                status_code=0,
                body_text="",
                content_type="",
                fetched_at=fetched_at,
                error=str(exc),
            )

    # ── search ───────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        engine_url: str | None = None,
        max_results: int = 5,
    ) -> list[WebResult]:
        # 1. Guardrail check
        approved, reason = self._check_guardrail(
            action="web_search", risk_level="medium", context={"query": query}
        )
        if not approved:
            return [
                WebResult(
                    url="",
                    status_code=0,
                    body_text="",
                    content_type="",
                    fetched_at=time.time(),
                    error=f"blocked by guardrail: {reason}",
                )
            ]

        # 2. Build engine URL
        if engine_url is None:
            engine_url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(query)

        # 3. Fetch search page (skip inner guardrail — already cleared)
        page = self._raw_fetch(engine_url)
        if page.status_code != 200 or page.error:
            return [page]

        # 4. Parse links
        parser = _LinkParser()
        try:
            parser.feed(page.body_text)
        except Exception:
            pass

        engine_host = urllib.parse.urlparse(engine_url).netloc.lower()
        seen: set[str] = set()
        candidate_urls: list[str] = []
        for href in parser.links:
            absolute = self._extract_absolute_url(href)
            if not absolute:
                continue
            host = urllib.parse.urlparse(absolute).netloc.lower()
            if not host or host == engine_host:
                continue
            if absolute in seen:
                continue
            seen.add(absolute)
            candidate_urls.append(absolute)
            if len(candidate_urls) >= max_results:
                break

        # 5. Fetch each result (use cache-aware fetch)
        return [self.fetch(u) for u in candidate_urls]

    @staticmethod
    def _extract_absolute_url(href: str) -> str | None:
        """Pull an absolute http(s) URL out of an href. DDG wraps in /l/?uddg=..."""
        if not href:
            return None
        # DuckDuckGo redirect: /l/?uddg=<url-encoded-target>
        if href.startswith("/") or href.startswith("//"):
            # Try to parse uddg= param
            parsed = urllib.parse.urlparse(href)
            qs = urllib.parse.parse_qs(parsed.query)
            for key in ("uddg", "u"):
                if key in qs and qs[key]:
                    candidate = qs[key][0]
                    if candidate.startswith(("http://", "https://")):
                        return candidate
            return None
        if href.startswith(("http://", "https://")):
            return href
        return None

    # ── status ───────────────────────────────────────────────────────────────

    def status(self) -> dict:
        return {
            "cache_enabled": self._store is not None,
            "guardrail_enabled": self._gate is not None,
            "max_age": self._max_age,
            "timeout": self._timeout,
        }
