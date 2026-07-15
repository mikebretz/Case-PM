' Case PM - Internet Tunnel (double-click THIS file)
' Opens a command window that STAYS OPEN so you can read messages and see your link.

Option Explicit
Dim fso, shell, folder, bat
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
bat = folder & "\START-INTERNET-TUNNEL.bat"

If Not fso.FileExists(bat) Then
    MsgBox "Cannot find START-INTERNET-TUNNEL.bat in:" & vbCrLf & folder, vbCritical, "Case PM Tunnel"
    WScript.Quit 1
End If

shell.CurrentDirectory = folder
shell.Run "cmd.exe /k call """ & bat & """ KEEPOPEN", 1, False
