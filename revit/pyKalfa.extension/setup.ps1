# pyKalfa - kurulum scripti
# Sanal ortami (env/) olusturur ve requirements.txt'deki paketleri kurar.
# Bu script pyKalfa.extension klasorunde durur; env/requirements.txt
# de ayni klasorde oldugu icin kok olarak bu klasor kullanilir.

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = $scriptDir
Set-Location $root

function Wait-BeforeExit {
    param([int]$Code)
    Write-Host ""
    try {
        Read-Host "Kapatmak icin Enter'a basin" | Out-Null
    } catch {
        Start-Sleep -Seconds 5
    }
    exit $Code
}

try {
    # Sistemde calisan bir Python bulmaya calis (once "py", sonra "python").
    $pyCmd = $null
    foreach ($candidate in @("py", "python")) {
        try {
            & $candidate --version *> $null
            if ($LASTEXITCODE -eq 0) { $pyCmd = $candidate; break }
        } catch {}
    }
    if (-not $pyCmd) {
        Write-Host "HATA: Sisteminizde calisan bir Python bulunamadi (PATH'te 'py'/'python' yok)."
        Write-Host "Once https://www.python.org adresinden Python 3'u kurun"
        Write-Host "('Add python.exe to PATH' kutusunu isaretlemeyi unutmayin),"
        Write-Host "sonra bu scripti tekrar calistirin."
        Wait-BeforeExit 1
    }
    Write-Host "Python bulundu: $pyCmd"

    if (Test-Path "env\Scripts\python.exe") {
        Write-Host "env/ zaten var, sanal ortam olusturma adimi atlaniyor."
    } else {
        Write-Host "Sanal ortam olusturuluyor (env/)..."
        & $pyCmd -m venv env
        if ($LASTEXITCODE -ne 0) {
            Write-Host "HATA: Sanal ortam (env/) olusturulamadi (yukaridaki hataya bakin)."
            Wait-BeforeExit 1
        }
    }

    # `pip.exe` yerine `python.exe -m pip`: pip.exe baslaticisi icinde
    # venv olusturuldugu andaki mutlak yolu tasir, klasor tasinirsa
    # yanlis ortama kurulum yapabilir. `-m pip` her zaman dogru ortami
    # hedefler.
    Write-Host "Bagimliliklar kuruluyor (requirements.txt) - bu birkac dakika surebilir..."
    & "env\Scripts\python.exe" -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "HATA: Bagimliliklar kurulamadi (yukaridaki hataya bakin)."
        Write-Host "Sik karsilasilan bir sorun: 'dosya adi cok uzun' / WinError 206 hatasi."
        Write-Host "Bu durumda KULLANIM.md'deki 'Sik Karsilasilan Durumlar' bolumune bakin"
        Write-Host "(Windows uzun yol destegini acmak veya projeyi kisa bir yola tasimak gerekir)."
        Wait-BeforeExit 1
    }

    Write-Host ""
    Write-Host "Kurulum tamamlandi."
    Write-Host "Sonraki adim: pyRevit'e 'revit' klasorunu extension olarak eklemek (bkz. KULLANIM.md)."
    Wait-BeforeExit 0
} catch {
    Write-Host ""
    Write-Host "BEKLENMEDIK HATA:"
    Write-Host $_.Exception.Message
    Wait-BeforeExit 1
}
