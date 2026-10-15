# 19 Depuração e erros comuns (UE5)

## Erro: unresolved external symbol (LNK2019 / LNK2001)
Causas mais comuns: módulo faltando no Build.cs (ex.: usar UEnhancedInputComponent sem "EnhancedInput", UUserWidget sem "UMG", AI sem "AIModule", Niagara sem "Niagara", GAS sem "GameplayAbilities"); função declarada no header e não implementada no .cpp (inclusive _Implementation de RPCs e BlueprintNativeEvent, ou _Validate com WithValidation); classe de outro módulo sem a macro de exportação (MODULO_API); assinatura diferente entre declaração e definição (const, parâmetros). Depois de corrigir o Build.cs, regenere os arquivos do projeto.

## Erro: cannot open include file / arquivo .generated.h
"Cannot open include file": caminho de include errado (a UE5 usa caminhos relativos às pastas Public dos módulos: #include "GameFramework/Character.h", #include "Components/BoxComponent.h") ou módulo faltando no Build.cs. "#include found after .generated.h file": o .generated.h precisa ser o último include do header. "Missing '*.generated.h'": adicione o include com o nome exato do arquivo. Depois de renomear arquivos, apague Intermediate e regenere o projeto.

## Erro: GENERATED_BODY, UCLASS e UHT
"Expected a class, struct or enum after UCLASS": macro mal posicionada. "Class must have GENERATED_BODY()": falta a macro. Erros de UHT apontam o arquivo e a linha antes da compilação C++: tipos não suportados em UPROPERTY (ponteiros para structs, std::vector, TMap aninhado), UFUNCTION com parâmetros não refletidos, enum Blueprint que não é uint8, prefixo de classe errado (classe UObject sem U, Actor sem A), especificadores conflitantes (BlueprintReadWrite em propriedade privada sem AllowPrivateAccess).

## Erro: incomplete type / forward declaration
"Use of undefined type" ou "incomplete type": a classe foi só pré-declarada (class UStaticMeshComponent;) e você usa membros dela; inclua o header no .cpp. Boa prática: nos headers, pré-declare (forward declare) e use TObjectPtr/ponteiros; nos .cpp, inclua os headers completos. Isso reduz o tempo de compilação.

## Crash: Access violation / ponteiro nulo
"Exception thrown: read access violation ... was nullptr" ou EXCEPTION_ACCESS_VIOLATION reading address 0x0000000000000000: uso de ponteiro nulo. Verifique com if (Ptr) / IsValid(Ptr), confira a inicialização (componentes criados no construtor; referências preenchidas no editor; GetWorld() nulo em CDOs), ordem de inicialização (BeginPlay de outro ator ainda não rodou) e objetos destruídos. Endereços como 0xFFFFFFFFFFFFFFFF ou valores aleatórios indicam ponteiro pendente: faltou UPROPERTY num ponteiro para UObject (coletado pelo GC) ou uso após Destroy.

## Crash: Assertion failed (check / ensure)
"Assertion failed: Expr [File:Line]": um check da engine ou seu falhou. Leia a expressão e a pilha (call stack) no relatório de crash ou no log: ela mostra a função do seu código que levou ao problema. Exemplos comuns: IsValid(Object) em spawn com classe nula (TSubclassOf não configurado no Blueprint), índices fora do intervalo em TArray ("Array index out of bounds": use IsValidIndex), CreateDefaultSubobject fora do construtor, NewObject com Outer inválido.

## Crash: depurar com o Visual Studio
Compile Development Editor ou DebugGame Editor, rode o editor pelo IDE (F5) e reproduza: o depurador para na linha do crash com variáveis e pilha. DebugGame desliga otimizações do seu código (variáveis visíveis; Development pode mostrar "variable optimized away"). Para crashes do jogo empacotado, mantenha os arquivos .pdb da mesma build e abra o minidump (UEMinidump.dmp em Saved/Crashes) no Visual Studio. Para Blueprints, breakpoints com F9 no grafo.

## Logs: onde olhar
Saved/Logs/Projeto.log (editor e PIE), Saved/Crashes/ (relatórios e minidumps), logs do jogo empacotado em <Pacote>/Projeto/Saved/Logs (Development) ou na pasta do usuário. Aumente o detalhe por categoria: log LogNet Verbose no console, ou -LogCmds="LogNet Verbose" na linha de comando, ou na seção [Core.Log] do DefaultEngine.ini. Categorias úteis: LogTemp, LogNet, LogBlueprintUserMessages, LogStreaming, LogAbilitySystem, LogAI, LogPhysics, LogShaderCompilers.

## Blueprint corrompido ou que não abre após mudar C++
Causas: classe pai C++ mudou de forma incompatível (propriedade removida ou renomeada, componente renomeado). Soluções: Core Redirects para renomeações; reverter a mudança e migrar com calma; File > Refresh All Nodes e Reparent Blueprint; em último caso, restaurar do controle de versão. Componentes criados em C++ renomeados podem ficar duplicados ou "fantasmas" no Blueprint: mantenha os nomes de CreateDefaultSubobject estáveis. Evite Live Coding para mudanças em headers.

## Propriedade do Blueprint não atualiza ao mudar o valor padrão em C++
O valor salvo no Blueprint ou na instância do nível sobrescreve o padrão do C++ depois que alguém o editou (mostra a seta amarela de reset). Clique em reset para voltar ao padrão do C++, ou mude no Blueprint. Atribuições no construtor C++ só valem para valores não sobrescritos. Ligações de delegates feitas no construtor podem se perder na serialização: ligue no BeginPlay ou PostInitializeComponents.

## Problemas de compilação estranhos: limpeza
Feche o editor e o IDE, apague Binaries, Intermediate e (se necessário) DerivedDataCache e .vs do projeto e dos plugins do projeto, gere os arquivos do projeto de novo e compile. Resolve muitos erros após trocar de branch, renomear arquivos ou atualizar a engine. Verifique também se o projeto aponta para a versão certa da engine.

## Problemas no PIE que não acontecem no pacote (e vice-versa)
PIE roda tudo no mesmo processo e com assets já carregados no editor; o pacote carrega do zero, mais rápido e em outra ordem. Diferenças típicas: referências nulas no BeginPlay no pacote (ordem de inicialização), assets não cozidos, código Editor Only (WITH_EDITOR) e comandos de console desativados em Shipping. Teste com Standalone Game (no menu do Play) e com builds Development empacotadas regularmente, não só no fim do projeto.

## Ferramentas de depuração em jogo
Console: showdebug (informações do jogador e câmera), showdebug abilitysystem (GAS), showdebug enhancedinput, show collision, stat fps/unit, ToggleDebugCamera, slomo, pause, DisplayAll Classe Propriedade (mostra uma propriedade de todos os atores de uma classe), obj list. Gameplay Debugger (apóstrofo), Visual Logger, Rewind Debugger (grava animação e estado para revisar quadro a quadro), Chaos Visual Debugger (física).

## Erros comuns de rede (resumo)
RPC Server sem dono (não chega); propriedade alterada no cliente; ator replicado spawnado no cliente; OnRep esperado no servidor; código de UI rodando no servidor dedicado (crash por falta de viewport); uso de GetPlayerController(0) em contexto de servidor. Detalhes no arquivo 07.
