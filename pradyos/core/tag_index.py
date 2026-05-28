from __future__ import annotations

import threading


class TagIndex:
    """Multi-value tag store: each tag points to a set of item IDs."""

    def __init__(self) -> None:
        self._tags: dict[str, set[str]] = {}
        self._lock = threading.Lock()

    # ── mutation ─────────────────────────────────────────────────────────────

    def tag(self, item_id: str, *tags: str) -> None:
        with self._lock:
            for t in tags:
                self._tags.setdefault(t, set()).add(item_id)

    def untag(self, item_id: str, *tags: str) -> None:
        with self._lock:
            for t in tags:
                bucket = self._tags.get(t)
                if bucket is None:
                    continue
                bucket.discard(item_id)
                if not bucket:
                    del self._tags[t]

    def delete_item(self, item_id: str) -> bool:
        with self._lock:
            found = False
            empties: list[str] = []
            for t, bucket in self._tags.items():
                if item_id in bucket:
                    bucket.discard(item_id)
                    found = True
                    if not bucket:
                        empties.append(t)
            for t in empties:
                del self._tags[t]
            return found

    # ── lookup ───────────────────────────────────────────────────────────────

    def items(self, tag: str) -> list[str]:
        with self._lock:
            bucket = self._tags.get(tag)
            return sorted(bucket) if bucket else []

    def tags(self, item_id: str) -> list[str]:
        with self._lock:
            return sorted(
                t for t, bucket in self._tags.items() if item_id in bucket
            )

    def search(self, *tags: str, mode: str = "all") -> list[str]:
        if not tags:
            return []
        with self._lock:
            sets = [self._tags.get(t, set()) for t in tags]
        if mode == "all":
            # Intersection — start with the first set
            result: set[str] = set(sets[0])
            for s in sets[1:]:
                result &= s
        else:  # "any"
            result = set()
            for s in sets:
                result |= s
        return sorted(result)

    # ── introspection ────────────────────────────────────────────────────────

    def list_tags(self) -> list[dict]:
        with self._lock:
            entries = [
                {"tag": t, "count": len(bucket)}
                for t, bucket in self._tags.items()
            ]
        return sorted(entries, key=lambda e: e["tag"])

    def count(self, tag: str | None = None) -> int:
        with self._lock:
            if tag is not None:
                bucket = self._tags.get(tag)
                return len(bucket) if bucket else 0
            # Total unique items across all tag sets.
            all_items: set[str] = set()
            for bucket in self._tags.values():
                all_items |= bucket
            return len(all_items)
