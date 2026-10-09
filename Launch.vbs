' NSDDD v4.0 — Windows launcher
' Double-click this file to start the search interface.
' Prefers the Python selected by the installer, then local .venv, then system launchers.

Option Explicit

Dim WshShell, FSO, ScriptDir
Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
ScriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = ScriptDir

Function Q(ByVal s)
    Q = Chr(34) & s & Chr(34)
End Function

Function TryRun(ByVal command)
    On Error Resume Next
    Dim rc
    rc = WshShell.Run(command, 0, True)
    If Err.Number <> 0 Then
        Err.Clear
        TryRun = False
        Exit Function
    End If
    TryRun = (rc = 0)
End Function

Function ReadInstallPython()
    On Error Resume Next
    Dim configPath, text, stream, re, matches, py
    configPath = ScriptDir & "\install_config.json"
    If Not FSO.FileExists(configPath) Then
        ReadInstallPython = ""
        Exit Function
    End If

    Set stream = FSO.OpenTextFile(configPath, 1)
    text = stream.ReadAll
    stream.Close

    Set re = New RegExp
    re.Pattern = """python""\s*:\s*""([^""]+)"""
    re.Global = False
    re.IgnoreCase = True

    If Not re.Test(text) Then
        ReadInstallPython = ""
        Exit Function
    End If

    Set matches = re.Execute(text)
    py = matches(0).SubMatches(0)
    py = Replace(py, "\\", "\")
    ReadInstallPython = py
End Function

Function PythonwFromPython(ByVal py)
    Dim lowerPy
    lowerPy = LCase(py)
    If Right(lowerPy, 11) = "\python.exe" Then
        PythonwFromPython = Left(py, Len(py) - 11) & "\pythonw.exe"
    Else
        PythonwFromPython = ""
    End If
End Function

Sub TryPythonPath(ByVal py)
    Dim pyw
    If py = "" Then Exit Sub
    pyw = PythonwFromPython(py)
    If pyw <> "" And FSO.FileExists(pyw) Then
        If TryRun(Q(pyw) & " " & Q(ScriptDir & "\launch.py") & " --detach") Then WScript.Quit 0
    End If
    If FSO.FileExists(py) Then
        If TryRun(Q(py) & " " & Q(ScriptDir & "\launch.py") & " --detach") Then WScript.Quit 0
    End If
End Sub

Call TryPythonPath(ReadInstallPython())
Call TryPythonPath(ScriptDir & "\.venv\Scripts\python.exe")
Call TryPythonPath(ScriptDir & "\venv\Scripts\python.exe")

If TryRun("pyw -3 " & Q(ScriptDir & "\launch.py") & " --detach") Then WScript.Quit 0
If TryRun("py -3 " & Q(ScriptDir & "\launch.py") & " --detach") Then WScript.Quit 0
If TryRun("pythonw " & Q(ScriptDir & "\launch.py") & " --detach") Then WScript.Quit 0
If TryRun("python " & Q(ScriptDir & "\launch.py") & " --detach") Then WScript.Quit 0

MsgBox "Could not start NSDDD. Run install.py again, or open Command Prompt in this folder and run: python .\launch.py", vbCritical, "NSDDD launcher"
