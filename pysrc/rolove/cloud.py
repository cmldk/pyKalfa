"""
pyKalfa / Rolove - LAZ nokta bulutu

Polycam'in georef OLMAYAN LAS/LAZ ciktisi yerel metre cercevesindedir ve
GLB ile ayni eksenleri kullanir. Georef surumu derece cinsinden boylam /
enlem tasir; yanlislikla verilirse acik bir hatayla reddedilir.

Bellek icin noktalar float32 tutulur (10 M nokta ~ 120 MB); yerel
cercevede +-20 m icin hassasiyet ~1e-6 m mertebesindedir.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


class GeorefError(ValueError):
    pass


def _read(path):
    import laspy
    try:
        backend = laspy.LazBackend.LazrsParallel
        if backend.is_available():
            return laspy.read(str(path), laz_backend=backend)
    except AttributeError:
        pass
    return laspy.read(str(path))


def load_laz(path: Path) -> np.ndarray:
    las = _read(path)
    x = np.asarray(las.x, dtype=np.float64)
    y = np.asarray(las.y, dtype=np.float64)
    if len(x) and np.all(np.abs(x) <= 180) and np.all(np.abs(y) <= 90) \
            and np.ptp(x) < 0.01 and np.ptp(y) < 0.01:
        raise GeorefError(
            "Bu LAZ georef (derece koordinatli) gorunuyor: {}. Polycam'den "
            "georef kapali LAS export'u alin.".format(Path(path).name))
    z = np.asarray(las.z, dtype=np.float64)
    return np.stack([x, y, z], axis=1).astype(np.float32)


def in_band(points: np.ndarray, zmin: float, zmax: float) -> np.ndarray:
    z = points[:, 2]
    return (z >= zmin) & (z <= zmax)
