# 06 Blueprints e integração com C++ (UE5)

## Blueprints: quando usar Blueprint e quando usar C++
C++: sistemas centrais, código chamado com muita frequência, matemática pesada, rede detalhada (RPCs, previsão), estruturas de dados, APIs da engine não expostas, código compartilhado entre muitos assets. Blueprint: conteúdo e ajustes (valores, referências a assets, efeitos), lógica específica de um nível ou de um item, prototipagem, eventos de animação e UI simples. Padrão recomendado: classe base em C++ com propriedades e funções expostas, e uma classe filha Blueprint que configura assets e reage a eventos (BlueprintImplementableEvent).

## Blueprints: tipos
Blueprint Class (classe filha de um ator, componente, pawn etc.), Level Blueprint (um por mapa, só para lógica específica daquele nível), Blueprint Interface, Blueprint Function Library (funções estáticas globais), Blueprint Macro Library, Widget Blueprint, Animation Blueprint, Editor Utility Blueprint/Widget (ferramentas de editor).

## Blueprints: Event Graph, funções, macros e eventos
Event Graph: eventos (BeginPlay, Tick, input, colisão) e nós com tempo (Delay, Timeline). Function: reutilizável, com entradas e saídas, sem Delay/Timeline; Pure (sem execução) para cálculos. Macro: copiada onde é usada, permite vários pinos de execução e Delay, mas é local ao Blueprint ou a uma Macro Library. Custom Event: evento com nome, aceita Delay e pode ser RPC. Construction Script: roda no editor ao colocar ou mexer no ator.

## Blueprints: comunicação
Cast (referência direta a uma classe conhecida; cria dependência hard que carrega a outra classe na memória), Blueprint Interface (várias classes implementam a mesma mensagem; quem chama não precisa saber o tipo nem fazer cast), Event Dispatcher (um emissor avisa vários ouvintes que se inscreveram com Bind). Um para um com tipo conhecido: cast com moderação; vários tipos respondendo à mesma ação (interagir, receber dano): interface; um para muitos (vida mudou, porta abriu): dispatcher.

## Blueprints: erro "Accessed None"
Significa usar uma referência vazia (None): a variável nunca foi preenchida, o objeto foi destruído, um Cast falhou e o resultado foi usado, a ordem de inicialização (o outro ator ainda não existia no BeginPlay) ou o objeto só existe no servidor. Corrija com Is Valid (ou Convert to Validated Get), tratando o pino Cast Failed, e conferindo onde a variável é preenchida. O Output Log mostra o Blueprint, o nó e a variável.

## C++ para Blueprint: expor funções e variáveis
UPROPERTY com BlueprintReadOnly/BlueprintReadWrite expõe variáveis; UFUNCTION(BlueprintCallable) expõe funções com execução, BlueprintPure sem execução. Categoria em Category="Combate". Parâmetros por referência não-const (TArray<FItem>& Out) viram pinos de saída. Para vários pinos de execução de saída a partir de um enum, use meta=(ExpandEnumAsExecs="Result") com um parâmetro de saída do tipo enum.

## C++ para Blueprint: eventos implementados no Blueprint
```cpp
UFUNCTION(BlueprintImplementableEvent, Category = "Weapon")
void OnFired(const FVector& MuzzleLocation);           // sem corpo em C++

UFUNCTION(BlueprintNativeEvent, Category = "Weapon")
float GetDamageMultiplier() const;                       // corpo padrão em C++
virtual float GetDamageMultiplier_Implementation() const { return 1.f; }
```
Chame normalmente (OnFired(Loc)); a engine roteia para o Blueprint. No Blueprint filho, BlueprintNativeEvent pode chamar a implementação do pai com o nó "Parent: GetDamageMultiplier".

## C++ para Blueprint: Blueprint Function Library
```cpp
UCLASS()
class MYGAME_API UMyMathLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintPure, Category = "MyGame|Math", meta = (WorldContext = "WorldContextObject"))
    static float DistanceToPlayer(const UObject* WorldContextObject, const AActor* Actor);
};
```
Funções estáticas ficam disponíveis em qualquer Blueprint. WorldContext preenche automaticamente o objeto de contexto para acessar o mundo.

## C++ para Blueprint: nós assíncronos (latentes)
Para nós com saídas que disparam depois (Completed, Failed), crie uma classe derivada de UBlueprintAsyncActionBase com um método estático BlueprintCallable marcado meta=(BlueprintInternalUseOnly="true"), delegates dinâmicos BlueprintAssignable como saídas e Activate() que inicia o trabalho. Chame SetReadyToDestroy() ao terminar. Alternativa mais antiga: FLatentActionInfo com FPendingLatentAction.

## Blueprints: depuração
Print String (texto na tela e no log), breakpoints com F9 (F10 avança, F11 entra), Watch this value nos pinos, seletor de instância de depuração na barra do Blueprint para ver o fluxo ao vivo, Blueprint Debugger (Tools > Debug) com pilha de chamadas, Draw Debug (linha, esfera, caixa).

## Blueprints: desempenho
Blueprints rodam numa máquina virtual: cada nó tem custo. Problemas comuns: lógica pesada no Event Tick, laços grandes (For Each sobre milhares de itens) e Get All Actors Of Class chamado com frequência. Soluções: mover laços e matemática para C++, usar timers e eventos, guardar referências em vez de procurar sempre, limitar Tick. Casts e variáveis com tipo de Blueprint criam dependências hard: use interfaces, classes base em C++ e soft references para reduzir a memória.

## Blueprints: Struct e Enum definidos em Blueprint x C++
Structs e enums criados em Blueprint são práticos, mas alterá-los (renomear campos) depois de muito uso pode quebrar referências e corromper dados de Blueprints. Para tipos usados em muitos lugares, defina em C++ (USTRUCT/UENUM BlueprintType): são mais estáveis e acessíveis dos dois lados.

## Blueprints: reparent e nativização
Para mover lógica de um Blueprint para C++: crie a classe C++ com as mesmas variáveis, faça Class Settings > Parent Class para a classe C++ (Reparent), e remova do Blueprint as variáveis duplicadas (use Core Redirects se for renomear). A antiga nativização de Blueprints foi removida na UE5; a recomendação é portar à mão os pontos críticos.

## Editor Utility Widgets e Blueprints
Ferramentas internas sem compilar plugin: Editor Utility Widget (interface no editor, aberta com Run Editor Utility Widget) e Editor Utility Blueprint (Asset Action Utility para ações em assets selecionados, Actor Action Utility para atores). Usam as Editor Scripting Utilities (renomear em lote, ajustar propriedades, criar assets). Não entram no jogo empacotado. Python também é suportado no editor com o plugin Python Editor Script Plugin.
