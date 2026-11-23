' Roda o rodar_vigia.cmd com a janela OCULTA e ESPERA terminar (a tarefa do Agendador fica "em execução" enquanto a vigia viver).
' Argumentos: 1 = python; 2 (opcional) = --executar.
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
Q = Chr(34)
raiz = fso.GetParentFolderName(WScript.ScriptFullName)
py = ""
modo = ""
If WScript.Arguments.Count > 0 Then py = WScript.Arguments(0)
If WScript.Arguments.Count > 1 Then modo = WScript.Arguments(1)
cmd = "cmd.exe /c " & Q & Q & raiz & "\rodar_vigia.cmd" & Q & " " & Q & py & Q & " " & modo & Q
WScript.Quit sh.Run(cmd, 0, True)
