' Запуск бота без чёрного окна консоли (команды + автоотчёт 11:30)
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = root & "\.venv\Scripts\pythonw.exe"
bot = root & "\bot.py"
sh.CurrentDirectory = root
sh.Run """" & pythonw & """ """ & bot & """", 0, False
