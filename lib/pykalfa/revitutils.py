# -*- coding: utf-8 -*-
"""Revit API'siyle calisirken tekrar eden kucuk yardimcilar.

Islevden bagimsiz, "her butonun er gec ihtiyac duyacagi" seyler burada
toplanir: eleman adi okuma, uyari yutucu, aktif view kontrolu.
"""

import math

from Autodesk.Revit.DB import (
    Element,
    FailureProcessingResult,
    FailureResolutionType,
    FailureSeverity,
    IFailuresPreprocessor,
    ViewType,
)
from pyrevit import forms

# DetailLine/FilledRegion gibi view'e bagli (view-specific) elemanlar bir
# sketch plane'e ihtiyac duyar; bu view turlerinde calisirlar.
DRAFTABLE_VIEW_TYPES = (
    ViewType.FloorPlan,
    ViewType.CeilingPlan,
    ViewType.EngineeringPlan,
    ViewType.AreaPlan,
    ViewType.Detail,
    ViewType.DraftingView,
    ViewType.Section,
    ViewType.Elevation,
)


class WarningSwallower(IFailuresPreprocessor):
    """Commit sirasinda cikan UYARILARI (hata degil) sessizce siler.

    Cok sayida kucuk/bitisik eleman olusturunca Revit "duplicate/short
    curve" gibi uyarilar gosterebiliyor; bu modal diyaloglar otomasyon
    akisinda beklenmedik kararsizliga yol acabiliyor. Gercek HATA'lar
    (FailureSeverity.Error ve uzeri) dokunulmadan Revit'in varsayilan
    davranisina birakilir.
    """

    def PreprocessFailures(self, failures_accessor):
        for failure in failures_accessor.GetFailureMessages():
            if failure.GetSeverity() == FailureSeverity.Warning:
                failures_accessor.DeleteWarning(failure)
        return FailureProcessingResult.Continue


class WarningSwallowerUnjoin(IFailuresPreprocessor):
    """WarningSwallower + "Can't keep elements joined" hatalarini otomatik
    "Unjoin Elements" ile cozer.

    Revit, uclari degen DetailCurve'leri kendiliginden birbirine baglar
    (join). Cok sayida ardisik (ozellikle neredeyse duz devam eden) cizgide
    bazi baglar korunamaz ve commit sirasinda HATA seviyesinde "Can't keep
    elements joined" cikar; kullanici diyalogda "Unjoin Elements"e basmak
    zorunda kalir. Bu cozum (FailureResolutionType.DetachElements) cizgilerin
    geometrisini degistirmez, yalniz aralarindaki otomatik bagi kaldirir.
    Burada ayni cozum kod tarafindan uygulanir.

    Yalniz DetachElements cozumu SUNAN hatalara dokunulur; diger hatalar
    Revit'in varsayilan davranisina birakilir (WarningSwallower gibi)."""

    def PreprocessFailures(self, failures_accessor):
        resolved = False
        for failure in failures_accessor.GetFailureMessages():
            severity = failure.GetSeverity()
            if severity == FailureSeverity.Warning:
                failures_accessor.DeleteWarning(failure)
            elif severity == FailureSeverity.Error and failure.HasResolutionOfType(
                    FailureResolutionType.DetachElements):
                failure.SetCurrentResolutionType(FailureResolutionType.DetachElements)
                failures_accessor.ResolveFailure(failure)
                resolved = True
        if resolved:
            return FailureProcessingResult.ProceedWithCommit
        return FailureProcessingResult.Continue


def elem_name(el):
    """Element.Name bazi siniflarda (ör. FilledRegionType) IronPython'da
    dogrudan ozellik olarak degil, explicit interface implementasyonu
    olarak gelir ve `el.Name` AttributeError firlatir. Standart pyRevit
    workaround'u: `Element.Name` descriptor'ini elle cagirmak."""
    try:
        return el.Name
    except AttributeError:
        return Element.Name.__get__(el)


def require_draftable_view(view, message=None):
    """Aktif view'de view'e bagli eleman cizilemiyorsa kullaniciyi
    uyarip scripti sonlandirir."""
    if view.ViewType in DRAFTABLE_VIEW_TYPES:
        return
    forms.alert(
        message
        or (
            "Aktif view bir plan/detay/kesit/cephe view'i olmali "
            "(view'e bagli elemanlar bir sketch plane'e ihtiyac duyar). "
            "Once uygun bir view acip tekrar calistirin."
        ),
        exitscript=True,
    )


def view_elevation(view):
    """View'in bagli oldugu seviyenin yuksekligi (yoksa 0.0).

    Olusturulan 2B elemanlarin Z'si icin kullanilir."""
    return view.GenLevel.Elevation if view.GenLevel else 0.0


def distance(p1, p2):
    """Iki (x, y) noktasi arasindaki duzlemsel mesafe."""
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])
