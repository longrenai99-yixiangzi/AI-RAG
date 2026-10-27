Option Explicit
Dim shell, files, repo, role, command, result
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
repo = files.GetParentFolderName(files.GetParentFolderName(WScript.ScriptFullName))
role = WScript.Arguments(0)
If role <> "knowledge" And role <> "viewer" And role <> "tls" Then WScript.Quit 2
command = Chr(34) & repo & "\.venv\Scripts\python.exe" & Chr(34) & " " & Chr(34) & repo & "\scripts\run_persistent_service.py" & Chr(34) & " " & role
result = shell.Run(command, 0, True)
WScript.Quit result
