"""
pyKalfa / Rolove - butun esikler ve varsayilanlar tek yerde.

Butun uzunluklar METRE. Revit'e giden JSON feet'tir; donusum yalniz
`prepare_rolove_input` icinde, `FT` ile yapilir. Buradaki her sabit
`rolove_input.json` icinde "params" olarak da yazilir (hangi ayarla
uretildigi sonradan gorulebilsin).
"""

from __future__ import annotations

import math

FT = 1.0 / 0.3048

# Kullanici kurali: olculer en yakin 0 veya 5 cm'ye yuvarlanir.
DIM_STEP_M = 0.05
# Kat kotlari 1 cm'ye yuvarlanir (konum, olcu degil).
LEVEL_STEP_M = 0.01

# Ayni duvarin iki kopyasini elemek icin uc nokta toleransi.
DUPLICATE_TOL_M = 0.005

# --- Kat kotlari (levels.py): GLB kat mesh'inden ---------------------------
LEVEL_BIN_M = 0.02            # Z histogram kutusu
LEVEL_NORMAL_MIN = 0.9        # |nz| bunun ustu = yatay yuzey
LEVEL_MIN_HEIGHT_M = 1.0      # tavan, dosemenin en az bu kadar ustunde


def _round_step(value, step):
    return round(math.floor(value / step + 0.5) * step, 6)


def round_dim(m: float) -> float:
    """Olcu yuvarlama: en yakin 0.05 m (0/5 cm)."""
    return _round_step(m, DIM_STEP_M)


def round_level(m: float) -> float:
    """Kat kotu yuvarlama: 0.01 m."""
    return _round_step(m, LEVEL_STEP_M)


def as_params() -> dict:
    """JSON'a yazilacak buyuk harfli sabitler."""
    return {k: v for k, v in globals().items() if k.isupper()}
