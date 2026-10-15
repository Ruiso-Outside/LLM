# 16 Assets, dados, carregamento e SaveGame (UE5)

## Referências hard x soft
Referência hard (UPROPERTY TObjectPtr<UStaticMesh>, TSubclassOf, ou um Cast/variável de tipo Blueprint): o asset referenciado é carregado junto com quem referencia. Muitas referências hard em cadeia fazem um Blueprint simples carregar metade do jogo (veja com Size Map). Referência soft (TSoftObjectPtr, TSoftClassPtr, FSoftObjectPath): guarda só o caminho; o asset é carregado quando você pedir. Use soft para conteúdo opcional ou grande (armas não equipadas, skins, níveis, sons raros).

## Carregamento assíncrono em C++
```cpp
#include "Engine/AssetManager.h"
#include "Engine/StreamableManager.h"

UPROPERTY(EditAnywhere) TSoftObjectPtr<UStaticMesh> WeaponMesh;

void AMyActor::LoadWeapon()
{
    if (WeaponMesh.IsValid()) { Apply(WeaponMesh.Get()); return; }   // já carregado
    FStreamableManager& SM = UAssetManager::GetStreamableManager();
    Handle = SM.RequestAsyncLoad(WeaponMesh.ToSoftObjectPath(),
        FStreamableDelegate::CreateUObject(this, &AMyActor::OnWeaponLoaded));
}
void AMyActor::OnWeaponLoaded() { Apply(WeaponMesh.Get()); }
```
Guarde o TSharedPtr<FStreamableHandle> enquanto quiser manter o asset carregado. LoadSynchronous() existe, mas trava o jogo: use só em ferramentas ou carregamentos pequenos em telas de loading. Em Blueprint: Async Load Asset / Async Load Class Asset.

## Asset Manager e Primary Assets
O Asset Manager gerencia Primary Assets (identificados por FPrimaryAssetId: Tipo:Nome), descoberta por pastas e carregamento por "bundles". Configure em Project Settings > Asset Manager (Primary Asset Types to Scan: tipo, classe base, diretórios). Classes derivadas de UPrimaryDataAsset são descobertas automaticamente. Funções: GetPrimaryAssetIdList, LoadPrimaryAsset(s) com bundles (ex.: carregar só os dados de UI de um item, sem a malha), UnloadPrimaryAsset. Também controla o chunking (divisão do conteúdo em pacotes para DLC e download sob demanda).

## Data Assets
```cpp
UCLASS(BlueprintType)
class MYGAME_API UWeaponData : public UPrimaryDataAsset
{
    GENERATED_BODY()
public:
    UPROPERTY(EditDefaultsOnly, Category = "Weapon") FText DisplayName;
    UPROPERTY(EditDefaultsOnly, Category = "Weapon") float Damage = 10.f;
    UPROPERTY(EditDefaultsOnly, Category = "Weapon", meta = (AssetBundles = "Game")) TSoftObjectPtr<USkeletalMesh> Mesh;
    UPROPERTY(EditDefaultsOnly, Category = "Weapon", meta = (AssetBundles = "UI")) TSoftObjectPtr<UTexture2D> Icon;
    virtual FPrimaryAssetId GetPrimaryAssetId() const override { return FPrimaryAssetId(TEXT("Weapon"), GetFName()); }
};
```
Crie instâncias no Content Browser (Miscellaneous > Data Asset). Bons para itens, armas, personagens, habilidades: cada um vira um asset próprio com referências a outros assets, editável por designers.

## DataTables
Tabela de linhas baseadas numa struct derivada de FTableRowBase, editável como planilha e importável/exportável em CSV ou JSON (ótimo para balanceamento). Leitura: FMyRow* Row = Table->FindRow<FMyRow>(RowName, TEXT("Contexto")); GetAllRows. Composite DataTable combina várias tabelas (base + DLC). Curve Tables guardam curvas por nível (XP, dano escalonado), usadas também pelo GAS. DataTable x Data Asset: tabela para muitos registros homogêneos e numéricos; Data Asset para registros com muitas referências a assets e estrutura rica.

## SaveGame
```cpp
UCLASS()
class MYGAME_API UMySave : public USaveGame
{
    GENERATED_BODY()
public:
    UPROPERTY() int32 Level = 1;
    UPROPERTY() int32 Gold = 0;
    UPROPERTY() FVector PlayerLocation;
    UPROPERTY() TArray<FName> UnlockedItems;
};

// salvar
UMySave* Save = Cast<UMySave>(UGameplayStatics::CreateSaveGameObject(UMySave::StaticClass()));
Save->Gold = 500;
UGameplayStatics::AsyncSaveGameToSlot(Save, TEXT("Slot1"), 0);
// carregar
if (UGameplayStatics::DoesSaveGameExist(TEXT("Slot1"), 0))
{
    UMySave* Loaded = Cast<UMySave>(UGameplayStatics::LoadGameFromSlot(TEXT("Slot1"), 0));
}
```
Arquivos em Saved/SaveGames (editor) ou na pasta do usuário (jogo empacotado). Use as versões Async para não travar. Guarde ids (FName, FPrimaryAssetId, soft paths), nunca ponteiros. Inclua um número de versão no save para migrar formatos. Centralize em um UGameInstanceSubsystem. Para salvar atores do mundo, marque propriedades com SaveGame e serialize com FMemoryWriter + FObjectAndNameAsStringProxyArchive (ArIsSaveGame = true).

## Configurações em arquivos .ini
UCLASS(Config=Game) com UPROPERTY(Config) lê valores de DefaultGame.ini na seção [/Script/MeuModulo.MinhaClasse]. Para configurações editáveis em Project Settings, derive de UDeveloperSettings (UCLASS(Config=Game, DefaultConfig, meta=(DisplayName="Minhas Configurações"))) e acesse com GetDefault<UMySettings>(). Configurações do jogador (gráficos, controles) ficam em UGameUserSettings (GameUserSettings.ini por usuário).

## Importação e reimportação
Formatos: FBX, glTF/GLB, USD, OBJ (malhas); PNG, TGA, EXR, PSD (texturas); WAV (áudio). A UE5 usa o Interchange Framework para importação extensível. Reimportar mantém referências (botão direito > Reimport; ou Auto Reimport ao detectar mudança no arquivo de origem em Editor Preferences). Escala: 1 unidade = 1 cm; Z para cima. Datasmith importa cenas completas de programas CAD/arquitetura.

## Redirectors e Core Redirects
Mover/renomear assets no Content Browser deixa Object Redirectors no lugar antigo; limpe com Fix Up Redirectors. Para renomear classes, propriedades ou structs C++ sem quebrar assets salvos, use Core Redirects no DefaultEngine.ini: [CoreRedirects] +ClassRedirects=(OldName="/Script/MeuJogo.OldClass", NewName="/Script/MeuJogo.NewClass") e +PropertyRedirects=(OldName="MyClass.OldProp", NewName="MyClass.NewProp").

## Gerenciamento de memória de assets
Ferramentas: Size Map, Reference Viewer, memreport -full (relatório de memória por tipo de asset), obj list class=Texture2D, Memory Insights (Unreal Insights com -trace=memory), Audit Assets. Táticas: soft references, Asset Manager com bundles, limites de tamanho de textura por grupo (Texture LOD Groups, Maximum Texture Size), descarregar níveis e conteúdo não usado, evitar Casts para classes Blueprint pesadas (use interfaces ou classes base C++ leves).

## Game Features e Modular Gameplay
Plugins Game Features permitem empacotar funcionalidades como módulos ativáveis (modos de jogo, eventos sazonais, DLC): o plugin contém conteúdo e código, e Game Feature Actions adicionam componentes a atores existentes (Add Components), habilidades, input e dados quando ativado. O Modular Gameplay (UGameFrameworkComponentManager) permite que atores recebam componentes de fora. O Lyra é a referência dessa arquitetura.
