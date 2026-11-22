"""Exact order statistics for a trend interval or an unfinished breath cycle."""

from collections import defaultdict
import json
import sqlite3
from statistics import median

from .monitoring import TrendSample
from ..domain import DataQuality


class TrendWindow:
    """Keep short windows in memory and spill long ones to a private temp database."""

    memory_limit = 1500
    _quality_order = (DataQuality.VALID, DataQuality.DEGRADED, DataQuality.STALE,
                      DataQuality.UNAVAILABLE)

    def __init__(self):
        self._db = None
        self.clear()

    def clear(self):
        if self._db is not None:
            self._db.close()
            self._db = None
        self._columns = defaultdict(list)
        self._counts = defaultdict(int)
        self._roi_rows = []
        self._widths = set()
        self._reasons = {}
        self.metric_names = set()
        self.first = self.last = None
        self.count = 0

    def __len__(self):
        return self.count

    def _spill(self):
        db = sqlite3.connect("", check_same_thread=False)  # SQLite deletes this private database on close.
        try:
            db.execute("CREATE TABLE samples (name TEXT, value REAL)")
            db.execute("CREATE TABLE regions (roi_json TEXT)")
            db.executemany("INSERT INTO samples VALUES (?, ?)",
                           ((key, value) for key, values in self._columns.items() for value in values))
            db.executemany("INSERT INTO regions VALUES (?)",
                           ((json.dumps(row),) for row in self._roi_rows))
            db.execute("CREATE INDEX sorted_samples ON samples(name, value)")
        except BaseException:
            db.close()
            raise
        self._db = db
        self._counts.update((key, len(values)) for key, values in self._columns.items())
        self._columns.clear()
        self._roi_rows.clear()

    @staticmethod
    def _side_values(row, bands):
        for name, region in (("right", row[:bands]), ("left", row[bands:])):
            if bands and all(value is not None for value in region):
                yield name, sum(float(value) for value in region)

    def append(self, frame: TrendSample):
        if self.count == self.memory_limit:
            self._spill()
        row = frame.roi_values
        values = list(self._side_values(row, len(row) // 2))
        values.extend((f"roi:{i}", float(v)) for i, v in enumerate(row) if v is not None)
        values.extend((f"metric:{name}", float(v)) for name, v in frame.metric_values if v is not None)
        if frame.global_value is not None:
            values.append(("global", float(frame.global_value)))
        if self._db is None:
            self._roi_rows.append(row)
            for name, value in values:
                self._columns[name].append(value)
        else:
            # Keep the counters and the temporary tables consistent if disk writes fail.
            self._db.execute("SAVEPOINT sample")
            try:
                self._db.executemany("INSERT INTO samples VALUES (?, ?)", values)
                self._db.execute("INSERT INTO regions VALUES (?)", (json.dumps(row),))
                self._db.execute("RELEASE sample")
            except sqlite3.Error:
                self._db.execute("ROLLBACK TO sample")
                self._db.execute("RELEASE sample")
                raise
            for name, _ in values:
                self._counts[name] += 1
        if self.first is None:
            self.first = frame
        self.last = frame
        self.count += 1
        self._widths.add(len(row))
        self.metric_names.update(name for name, _ in frame.metric_values)
        if frame.quality_reason != "insufficient_data":
            if frame.quality_reason or frame.quality not in self._reasons:
                self._reasons[frame.quality] = frame.quality_reason or None

    def quality(self):
        reasons = self._reasons.copy()
        if self.last.quality_reason == "insufficient_data":
            reasons[self.last.quality] = self.last.quality_reason
        worst = next(q for q in reversed(self._quality_order) if q in reasons)
        return worst, reasons[worst]

    @property
    def roi_count(self):
        return max(self._widths, default=0)

    def side_medians(self):
        if len(self._widths) == 1:
            return self.median("right"), self.median("left")
        # Older/narrower frames must use the final window's regional split.
        bands = self.roi_count // 2
        if self._db is None:
            values = defaultdict(list)
            for row in self._roi_rows:
                for side, value in self._side_values(row, bands):
                    values[side].append(value)
            return tuple(median(values[side]) if values[side] else None for side in ("right", "left"))
        # SQLite sorts the exceptional mixed-width series using its temp storage.
        result = []
        for side in ("right", "left"):
            self._db.create_function(
                "side_sum", 1, lambda data: dict(self._side_values(json.loads(data), bands)).get(side)
            )
            count = self._db.execute("SELECT COUNT(side_sum(roi_json)) FROM regions").fetchone()[0]
            rows = self._db.execute(
                "SELECT side_sum(roi_json) AS v FROM regions WHERE v IS NOT NULL "
                "ORDER BY v LIMIT ? OFFSET ?", (2 - count % 2, max(0, (count - 1) // 2)),
            )
            result.append(median(row[0] for row in rows) if count else None)
        return tuple(result)

    def median(self, name):
        if self._db is None:
            values = self._columns.get(name)
            return median(values) if values else None
        count = self._counts[name]
        if not count:
            return None
        rows = self._db.execute(
            "SELECT value FROM samples WHERE name = ? ORDER BY value LIMIT ? OFFSET ?",
            (name, 2 - count % 2, (count - 1) // 2),
        )
        return median(row[0] for row in rows)

    def mean_global(self):
        if self._db is None:
            values = self._columns.get("global")
            return sum(values) / len(values) if values else None
        count = self._counts["global"]
        if not count:
            return None
        rows = self._db.execute(
            "SELECT value FROM samples WHERE name = 'global' ORDER BY rowid"
        )
        return sum(row[0] for row in rows) / count
