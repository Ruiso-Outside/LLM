; Atalhos com o icone do LLM Local.
; O executavel e o do Electron sem modificacoes (para manter a reputacao no
; Controle Inteligente de Aplicativos do Windows), entao o icone vem do .ico.
!macro customInstall
  IfFileExists "$DESKTOP\LLM Local.lnk" 0 +2
    CreateShortCut "$DESKTOP\LLM Local.lnk" "$INSTDIR\LLM Local.exe" "" "$INSTDIR\resources\app\icon.ico" 0
  IfFileExists "$SMPROGRAMS\LLM Local.lnk" 0 +2
    CreateShortCut "$SMPROGRAMS\LLM Local.lnk" "$INSTDIR\LLM Local.exe" "" "$INSTDIR\resources\app\icon.ico" 0
!macroend
