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

# --- Hizalama (align.py): DXF kati -> tarama ------------------------------
ALIGN_SLICE = (1.0, 1.6)      # dosemeden bu yukseklikler arasi yatay dilim
ALIGN_SLICES = ((1.0, 1.6), (0.4, 0.65))  # denenecek dilimler (ikincisi: cati kati)
ALIGN_GRID_M = 0.05           # rasterleme / dilim tekillestirme hucresi
ALIGN_ICP_ITERS = 15
ALIGN_ICP_MAX_DIST = 0.15     # ICP eslesme yaricapi (ust sinir)
ALIGN_ICP_MIN_DIST = 0.03     # kirpilmis ICP yaricapinin alt siniri
ALIGN_INLIER_M = 0.05         # RMS'e giren "duvar noktasi" uzakligi
ALIGN_INLIER_MIN = 0.12       # dilim noktalarinin en az bu orani duvar yuzunde olmali
                              # (ornek veri: kat 0.16-0.47; rastgele bulut ~0.06)
ALIGN_MAX_REFINE_DEG = 3.0    # kaba adaydan sonra izin verilen ek donus
ALIGN_RMS_MAX = 0.03          # bunun ustu: kat modele basilmaz
ALIGN_SUPPORT_MIN = 0.5       # yuz orneklerinin destekli orani alt siniri
SUPPORT_DIST_M = 0.05         # duvar yuzunun disinda destek sayilan pay
SUPPORT_BIN_M = 0.10          # destek olcumunde duvar boyunca kutu boyu
ALIGN_PREFER_MARGIN = 0.10    # tercih edilen yon, destekte bu kadar geride kalabilir

# --- Duvar iyilestirme (refine.py): yuz uydurma, ic/dis, kalinlik --------
FACE_BAND_M = 0.12            # nokta izgara indeksinin hucre boyu
FACE_SEARCH_M = 0.30          # DXF yuzunun iki yaninda gercek yuzun aranacagi pay
FACE_FIT_M = 0.03             # bulunan tepe etrafinda dogru uydurma bandi
FACE_HIST_BIN_M = 0.01        # dik uzaklik histogram kutusu
FACE_CELL_M = 0.05            # yuz uzerinde (boy x yukseklik) tekillestirme hucresi
FACE_END_MARGIN_M = 0.15      # duvar uclarinda dik duvar noktalarini disarida birakir
FACE_EDGE_RATIO = 0.30        # yuz tepesi, seritteki en guclu tepenin en az bu orani
FACE_VOID_SEARCH_M = 0.10     # ic duvar govdesi (bos bant) DXF ekseninin t/2+bu payinda aranir
FACE_VOID_RATIO = 0.30        # bos bant: en guclu tepenin en cok bu orani (kapi bosluklari
                              # govdeye nokta dusurur; ornek veride 0.0-0.27)
FACE_PARALLEL_DEG = 2.0       # ic duvarin iki yuzu paralel sayilma siniri (ornek: 1.1-1.8)
FACE_Z_MARGIN_M = 0.30        # doseme ustu / tavan alti disarida birakilan pay
FACE_MIN_POINTS = 200         # "yuz goruldu" icin en az nokta
FACE_MIN_COVERAGE = 0.30      # "yuz goruldu" icin 5 cm kutularda doluluk orani
FACE_TRIM = 0.20              # en kotu bu oran atilip yeniden uydurulur
MAX_SHIFT_M = 0.10            # bundan buyuk oteleme duzeltilmez (DXF kalir, uyari)
MAX_ROT_DEG = 2.0             # bundan buyuk donus duzeltilmez
THICKNESS_RANGE_M = (0.05, 0.60)
PARALLEL_DEG = 1.0            # iki yuz paralel sayilma siniri
SIDE_PROBE_M = 0.20           # ic/dis yoklamasi: yuzun bu kadar otesi
SIDE_PROBE_FRACTIONS = (0.25, 0.50, 0.75)
CORNER_SNAP_M = 0.15          # uclari bu mesafede olan duvarlar birlestirilir
DEFAULT_WALL_HEIGHT_M = 2.50

# --- Aciklik (openings.py) ------------------------------------------------
HOST_TOL_M = 0.05             # aciklik merkezi, duvar ekseninden en cok t/2 + bu
CSV_WIDTH_TOL_M = 0.10        # CSV kaydi bu genislik farkinda eslesir
OPENING_PROBE_M = 0.20        # komsu oda yoklamasi: yuzun bu kadar otesi
DEFAULT_DOOR_HEIGHT_M = 2.10
DEFAULT_WINDOW_HEIGHT_M = 1.20
DEFAULT_WINDOW_SILL_M = 0.90
DEFAULT_OPENING_HEIGHT_M = 2.10


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
