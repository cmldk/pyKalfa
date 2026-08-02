# -*- coding: utf-8 -*-
"""Alt-surec (exe) calistirma -- butun islevlerin ortak kullandigi katman.

Revit'in IronPython 2.7 motorunda cv2/numpy gibi CPython paketleri
calismaz; bu yuzden agir isler `env/` sanal ortamindaki CPython'a
alt-surec olarak devredilir. Kurulum (pip) da ayni yoldan yapilir.
"""

import clr

clr.AddReference("System")
from System.Diagnostics import Process, ProcessStartInfo  # noqa: E402

from pyrevit import script  # noqa: E402

logger = script.get_logger()


def run_process(file_name, args, cwd=None, on_line=None,
                on_poll=None, poll_interval_ms=200):
    """Herhangi bir exe'yi (arg listesiyle, tirnaklanmis) alt-surec olarak
    calistirir; (exit_code, birlesik_cikti) dondurur. `file_name` PATH'te
    bir isim (ör. "python") veya tam yol olabilir.

    stdout/stderr, `BeginOutputReadLine`/`BeginErrorReadLine` ile SATIR
    SATIR ve ESZAMANSIZ (asenkron) okunur -- `ReadToEnd()` ile once
    stdout'un tamamen bitmesini beklemek, buyuk ciktida (ör. pip'in
    torch/easyocr indirirken bastigi uzun loglar) stderr'in isletim
    sistemi tampon (pipe buffer) boyutunu asmasi durumunda alt-sureci
    stderr'i okuyacak kimse olmadan bloke edip KILITLEYEBILIYOR
    (deadlock). Satir satir/eszamanli okuma bu riski ortadan kaldirir.

    `on_line(line)` verilirse her yeni satir geldiginde cagirilir (ör.
    durumu kaydetmek veya loglamak icin). **Dikkat:** bu geri cagirim
    .NET'in okuma iş parcaciklarindan gelir, ana (UI) iş parcacigindan
    DEGIL. WPF tabanli pyRevit pencereleri (ör. `forms.ProgressBar`)
    baska bir iş parcacigindan guncellenirse kararsizlik olusabilir; bu
    yuzden `on_line` icinde sadece veri saklayin, ekrani `on_poll` ile
    guncelleyin.

    `on_poll()` verilirse, alt-surec beklenirken `poll_interval_ms`
    araliklarla **ana iş parcacigindan** cagirilir -- arayuz guncellemesi
    icin dogru yer burasidir.

    `PYTHONUTF8=1` her zaman ayarlanir: Turkce (cp1254) gibi Windows
    konsol kod sayfalarinda, alt-surecte calisan bazi pip paketleri
    (ör. easyocr'in model indirme ilerleme cubugu, Unicode blok karakteri
    basmaya calisirken) `UnicodeEncodeError` ile cokebiliyor. UTF-8 modu
    bunu konsol kod sayfasindan bagimsiz hale getirir."""
    psi = ProcessStartInfo()
    psi.FileName = file_name
    psi.Arguments = " ".join('"{}"'.format(a) for a in args)
    psi.UseShellExecute = False
    psi.RedirectStandardOutput = True
    psi.RedirectStandardError = True
    psi.CreateNoWindow = True
    psi.EnvironmentVariables["PYTHONUTF8"] = "1"
    if cwd:
        psi.WorkingDirectory = cwd

    collected_lines = []

    def _handle_line(sender, e):
        if e.Data is not None:
            collected_lines.append(e.Data)
            if on_line:
                try:
                    on_line(e.Data)
                except Exception as ex:
                    logger.debug("on_line callback hatasi: {}".format(ex))

    proc = Process()
    proc.StartInfo = psi
    proc.OutputDataReceived += _handle_line
    proc.ErrorDataReceived += _handle_line
    proc.Start()
    proc.BeginOutputReadLine()
    proc.BeginErrorReadLine()
    if on_poll:
        # Zaman asimili WaitForExit(ms) `False` donerse surec hala
        # calisiyor demektir; her turda arayuze soz hakki veriyoruz.
        while not proc.WaitForExit(poll_interval_ms):
            try:
                on_poll()
            except Exception as ex:
                logger.debug("on_poll callback hatasi: {}".format(ex))
    # Parametresiz WaitForExit, eszamansiz cikti okuyucularinin da
    # bitmesini garantiler (zaman asimili surum bunu garanti etmez);
    # son satirlar kaybolmasin diye her durumda cagirilir.
    proc.WaitForExit()
    return proc.ExitCode, "\n".join(collected_lines)


def run_python(script_path, args=None, on_line=None, on_poll=None):
    """`env/` sanal ortamindaki CPython ile bir `pysrc/...` scriptini
    calistirir; (exit_code, birlesik_cikti) dondurur.

    Ortamin kurulu oldugu varsayilir -- buton, kullanici girdisi
    istemeden once `bootstrap.ensure_env()` cagirmalidir."""
    from pykalfa import paths

    full_args = [script_path]
    full_args.extend(args or [])
    return run_process(
        paths.python_exe(), full_args, on_line=on_line, on_poll=on_poll
    )
