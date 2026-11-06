"""
pyKalfa / Rolove - Polycam kat plani CSV raporu

Satir bicimi: `Floor,Room,Description,Value`. Oda bazinda tavan
yuksekligi (tek deger ya da egik tavanlarda `0.7 - 2.4` araligi),
kapi/pencere olculeri (`G x Y`, konumsuz) ve alanlar okunur. Bilinmeyen
satirlar yok sayilir.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

_FLOOR_RE = re.compile(r"^Floor\s+(\d+)$")
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


@dataclass
class RoomReport:
    floor: int
    name: str
    ceiling_min: float | None = None
    ceiling_max: float | None = None
    doors: list = field(default_factory=list)
    windows: list = field(default_factory=list)
    area: float | None = None


@dataclass
class Report:
    rooms: dict
    livable_area_by_floor: dict
    wall_thickness_setting: float | None


def _numbers(text):
    return [float(x) for x in _NUM_RE.findall(text or "")]


def _pair(text):
    nums = _numbers(text)
    return (nums[0], nums[1]) if len(nums) >= 2 else None


def read_report(path: Path) -> Report:
    rooms = {}
    livable = {}
    thickness = None
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            floor_txt = (row.get("Floor") or "").strip()
            room = (row.get("Room") or "").strip()
            desc = (row.get("Description") or "").strip()
            value = row.get("Value") or ""

            if floor_txt == "All" and desc.startswith("Wall thickness"):
                nums = _numbers(value)
                thickness = nums[0] if nums else None
                continue
            m = _FLOOR_RE.match(floor_txt)
            if not m:
                continue
            floor = int(m.group(1))
            if room == "Entire Floor":
                if desc.startswith("Total livable floor area"):
                    nums = _numbers(value)
                    if nums:
                        livable[floor] = nums[0]
                continue

            rr = rooms.setdefault((floor, room), RoomReport(floor, room))
            if desc.startswith("Ceiling height"):
                nums = _numbers(value)
                if nums:
                    rr.ceiling_min, rr.ceiling_max = min(nums), max(nums)
            elif desc.startswith("Door dimensions"):
                pair = _pair(value)
                if pair:
                    rr.doors.append(pair)
            elif desc.startswith("Window dimensions"):
                pair = _pair(value)
                if pair:
                    rr.windows.append(pair)
            elif desc.startswith("Floor area"):
                nums = _numbers(value)
                if nums:
                    rr.area = nums[0]
    return Report(rooms, livable, thickness)
