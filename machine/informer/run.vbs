' run.vbs - launch the informer without a console window (task TG-Informer). ASCII only: VBScript chokes on UTF-8 BOM.
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File ""C:\ProgramData\tg-informer\informer.ps1""", 0, False
