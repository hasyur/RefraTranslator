Option Explicit

Dim shell
Dim fileSystem
Dim projectRoot
Dim batchPath
Dim logPath
Dim command
Dim index
Dim exitCode

Set shell = CreateObject("WScript.Shell")
Set fileSystem = CreateObject("Scripting.FileSystemObject")

projectRoot = fileSystem.GetParentFolderName(WScript.ScriptFullName)
batchPath = fileSystem.BuildPath(projectRoot, "start_gui.bat")
logPath = fileSystem.BuildPath(fileSystem.BuildPath(projectRoot, "output"), "launcher.log")

shell.CurrentDirectory = projectRoot
shell.Environment("PROCESS")("REFRA_LAUNCH_HIDDEN") = "1"

command = Quote(shell.ExpandEnvironmentStrings("%ComSpec%")) & _
    " /d /s /c " & Chr(34) & Quote(batchPath)
For index = 0 To WScript.Arguments.Count - 1
    command = command & " " & Quote(WScript.Arguments(index))
Next
command = command & Chr(34)

exitCode = shell.Run(command, 0, True)
If exitCode <> 0 Then
    MsgBox _
        "RefraTranslator could not start (exit code " & exitCode & ")." & vbCrLf & _
        "Check the diagnostic log:" & vbCrLf & logPath & vbCrLf & vbCrLf & _
        "If the log does not exist, run install.bat first.", _
        vbCritical + vbOKOnly, _
        "RefraTranslator"
End If

WScript.Quit exitCode

Function Quote(value)
    Quote = Chr(34) & Replace(CStr(value), Chr(34), Chr(34) & Chr(34)) & Chr(34)
End Function
