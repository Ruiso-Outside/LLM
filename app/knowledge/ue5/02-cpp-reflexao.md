# 02 C++ e sistema de reflexão (UE5)

## Reflexão: o que é e o Unreal Header Tool
A Unreal adiciona reflexão ao C++ com macros (UCLASS, USTRUCT, UENUM, UPROPERTY, UFUNCTION). Antes de compilar, o Unreal Header Tool (UHT) lê os headers e gera código em NomeDoArquivo.generated.h. A reflexão permite Blueprints, serialização (salvar assets), replicação, coleta de lixo, o painel Details e o editor. O include do .generated.h deve ser o ÚLTIMO include do header, e a classe precisa da macro GENERATED_BODY() na primeira linha do corpo.

## Reflexão: prefixos de tipos
A: classes derivadas de AActor (AMyCharacter). U: derivadas de UObject (UMyComponent, UMyGameInstance). F: structs e tipos comuns (FVector, FMyItemData). E: enums (EWeaponType). I: interfaces (IInteractable). T: templates (TArray, TMap, TSubclassOf). S: widgets Slate (SButton). O UHT exige esses prefixos; o nome do arquivo não leva o prefixo (MyCharacter.h define AMyCharacter).

## Reflexão: declaração de classe básica
```cpp
#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "MyPickup.generated.h"

UCLASS(Blueprintable)
class MYGAME_API AMyPickup : public AActor
{
    GENERATED_BODY()
public:
    AMyPickup();
protected:
    virtual void BeginPlay() override;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Pickup")
    TObjectPtr<UStaticMeshComponent> Mesh;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Pickup", meta = (ClampMin = "0"))
    int32 Amount = 1;
};
```
MYGAME_API é a macro de exportação do módulo (nome do módulo em maiúsculas + _API); necessária para a classe ser usada por outros módulos.

## Reflexão: especificadores de UCLASS
Blueprintable (pode ser base de Blueprint), BlueprintType (pode ser tipo de variável em Blueprint), Abstract (não pode ser instanciada nem colocada no nível), NotBlueprintable, Config=Game (propriedades com Config são lidas do .ini), DefaultToInstanced e EditInlineNew (objetos criados inline no Details), Within=Outer, MinimalAPI, Transient, meta=(BlueprintSpawnableComponent) para componentes que aparecem no botão Add de Blueprints.

## Reflexão: especificadores de UPROPERTY (edição)
- EditAnywhere: editável no padrão da classe e em cada instância no nível.
- EditDefaultsOnly: só no padrão da classe (Blueprint).
- EditInstanceOnly: só nas instâncias do nível.
- VisibleAnywhere / VisibleDefaultsOnly / VisibleInstanceOnly: aparece mas não edita (comum para componentes: o ponteiro não muda, mas as propriedades do componente ficam editáveis).
- BlueprintReadOnly / BlueprintReadWrite: acesso em Blueprints.
- Category="A|B": agrupa no Details.
- Transient: não é salvo. SaveGame: incluído na serialização de SaveGame com ArIsSaveGame.
- Replicated / ReplicatedUsing=OnRep_X: replicação.
- Config / GlobalConfig: lido do .ini.
- AdvancedDisplay: fica na seção avançada.

## Reflexão: metadados de UPROPERTY
meta=(ClampMin="0", ClampMax="100", UIMin, UIMax) limitam valores; EditCondition="bEnabled" habilita a edição só quando outra propriedade é verdadeira (EditConditionHides esconde); AllowPrivateAccess="true" expõe a Blueprints uma variável privada; ExposeOnSpawn="true" aparece no nó Spawn Actor; MakeEditWidget mostra um gizmo para FVector/FTransform na viewport; Units="cm"; GetOptions="FunctionName" cria uma lista de opções; Bitmask com BitmaskEnum para flags.

## Reflexão: especificadores de UFUNCTION
- BlueprintCallable: chamável em Blueprints (com pinos de execução).
- BlueprintPure: sem pinos de execução, não deve alterar estado.
- BlueprintImplementableEvent: declarado em C++, implementado só em Blueprint (sem corpo em C++).
- BlueprintNativeEvent: tem implementação padrão em C++ (função NomeFuncao_Implementation) que o Blueprint pode sobrescrever.
- Server / Client / NetMulticast com Reliable ou Unreliable: RPCs de rede (implementação em _Implementation, validação opcional em _Validate com WithValidation).
- Exec: comando de console em classes que suportam (PlayerController, Pawn, GameMode, CheatManager).
- CallInEditor: botão no Details que roda a função no editor.
- meta=(DisplayName, Keywords, CompactNodeTitle, DefaultToSelf, WorldContext="WorldContextObject", ExpandEnumAsExecs="Result", AdvancedDisplay, DeprecatedFunction).

## Reflexão: USTRUCT e UENUM
```cpp
USTRUCT(BlueprintType)
struct FItemData
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere, BlueprintReadWrite) FName Id;
    UPROPERTY(EditAnywhere, BlueprintReadWrite) FText DisplayName;
    UPROPERTY(EditAnywhere, BlueprintReadWrite) int32 MaxStack = 1;
};

UENUM(BlueprintType)
enum class EItemRarity : uint8
{
    Common UMETA(DisplayName = "Comum"),
    Rare,
    Epic
};
```
Structs USTRUCT não são coletadas pelo GC e são passadas por valor; UPROPERTYs dentro delas que apontam para UObjects são rastreadas. Enums expostos a Blueprint precisam ser uint8. Para structs de linha de DataTable, herde de FTableRowBase.

## Tipos: inteiros, números e texto
int32, uint8, int64, float, double (a UE5 usa double em FVector e transformações: Large World Coordinates). Texto: FString (texto mutável, manipulação), FName (identificador imutável, comparação rápida, sem distinção de maiúsculas, ótimo para ids e nomes de sockets/tags), FText (texto exibido ao jogador, localizável; use LOCTEXT/NSLOCTEXT). Conversões: FName(*Str), Name.ToString(), FText::FromString, Text.ToString(), FString::Printf(TEXT("%d"), Valor), FString::FromInt. Literais de texto sempre com TEXT("...").

## Tipos: contêineres
TArray<T> (vetor dinâmico: Add, Emplace, Remove, RemoveAt, RemoveSwap, Find, Contains, Num, IsValidIndex, Sort, laço range-for), TMap<K,V> (dicionário: Add, Find que devolve ponteiro ou nullptr, FindOrAdd, Contains, Remove), TSet<T> (conjunto). Para UPROPERTY, use TArray/TMap/TSet com tipos refletidos. TMap e TSet não podem ser replicados; TArray pode. Reserve(N) evita realocações; RemoveSwap é O(1) quando a ordem não importa.

## Ponteiros: TObjectPtr, raw, fraco e soft
- TObjectPtr<T>: padrão da UE5 para membros UPROPERTY que apontam para UObjects (no editor ajuda no rastreamento e carregamento; no jogo empacotado vira um ponteiro comum).
- Ponteiro cru T*: em variáveis locais e parâmetros.
- TWeakObjectPtr<T>: não impede a coleta de lixo; verifique IsValid()/Get() antes de usar. Bom para referências a atores que podem ser destruídos.
- TSoftObjectPtr<T> / TSoftClassPtr<T>: guarda o caminho do asset sem carregá-lo; carregue sob demanda.
- TSubclassOf<T>: referência a uma classe (para spawn), restringida a T e filhas.
- TSharedPtr / TSharedRef / TUniquePtr / TWeakPtr: ponteiros inteligentes para tipos não-UObject (structs F, Slate). Nunca use com UObjects.

## Coleta de lixo (GC)
UObjects são liberados pelo coletor quando nada os referencia. Uma referência só conta se estiver numa UPROPERTY (ou num TArray UPROPERTY, ou registrada via AddReferencedObjects/FGCObject). Um ponteiro cru membro sem UPROPERTY para um UObject pode virar ponteiro pendente (dangling) depois de uma coleta, causando crash aleatório. Atores destruídos (Destroy) ficam pendentes de limpeza: use IsValid(Ator), que também detecta objetos marcados para destruição. Para manter um objeto vivo sem dono, use AddToRoot (e RemoveFromRoot depois) com moderação, ou um subsystem dono.

## Criação de objetos
- Componentes no construtor: CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Mesh")).
- Atores: GetWorld()->SpawnActor<AMyActor>(Classe, Transform, Params) ou SpawnActorDeferred + FinishSpawning para configurar antes do BeginPlay.
- UObjects comuns: NewObject<UMyObject>(Outer). O Outer define o dono; para objetos temporários use GetTransientPackage().
- Componentes em tempo de execução: NewObject<UMyComponent>(this) seguido de RegisterComponent() (e AddInstanceComponent para aparecer no editor).
Nunca use new/delete com UObjects.

## Construtor x BeginPlay
O construtor roda também para criar o Class Default Object (CDO) e no editor; nele, só crie componentes e defina valores padrão. Não acesse o mundo, outros atores, GetWorld(), nem carregue assets dinamicamente no construtor (exceto ConstructorHelpers::FObjectFinder, que só funciona no construtor e cria dependência hard). Lógica de jogo vai no BeginPlay, PostInitializeComponents ou OnConstruction (que roda no editor ao mexer no ator, como o Construction Script).

## Logs e mensagens na tela
```cpp
DECLARE_LOG_CATEGORY_EXTERN(LogMyGame, Log, All);   // no .h
DEFINE_LOG_CATEGORY(LogMyGame);                      // num .cpp
UE_LOG(LogMyGame, Warning, TEXT("Vida: %f, Nome: %s"), Health, *GetName());
if (GEngine) GEngine->AddOnScreenDebugMessage(-1, 5.f, FColor::Green, TEXT("Olá"));
```
Verbosidades: Fatal, Error, Warning, Display, Log, Verbose, VeryVerbose. FString precisa do * para virar TCHAR* no formato. A UE 5.2+ também tem UE_LOGFMT com sintaxe de formatação por nome.

## Asserções
check(Expr) para invariantes (crash em builds de desenvolvimento), checkf com mensagem, verify (avalia a expressão também em Shipping), ensure(Expr) e ensureMsgf (registram um erro e uma pilha uma vez, sem crash, e retornam o valor booleano: útil em if (!ensure(Ptr)) return;). Em Shipping, check é removido.

## Delegates (resumo)
DECLARE_DELEGATE (um ouvinte, C++), DECLARE_MULTICAST_DELEGATE (vários ouvintes, C++), DECLARE_DYNAMIC_DELEGATE e DECLARE_DYNAMIC_MULTICAST_DELEGATE (refletidos, serializáveis, usáveis em Blueprint como Event Dispatchers; funções ligadas precisam ser UFUNCTION). Variações com _OneParam, _TwoParams etc. Detalhes no arquivo 04.

## Strings de caminho de assets
Caminho de objeto: /Game/MeuJogo/Armas/BP_Espada.BP_Espada_C (o _C indica a classe gerada de um Blueprint). /Game corresponde à pasta Content do projeto; /NomeDoPlugin à pasta Content de um plugin; /Engine ao conteúdo da engine. Use FSoftObjectPath ou TSoftObjectPtr em vez de strings soltas.
