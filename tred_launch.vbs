Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c cd /d ""E:\Pliki\Projects\Tred"" && python main.py >> ""E:\Pliki\Projects\Tred\tred.log"" 2>&1", 0, False
