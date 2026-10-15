# 04 Atores, componentes, eventos e subsistemas (UE5)

## Ciclo de vida de um ator
Ao ser colocado ou criado: construtor (cria componentes) → PostActorCreated / PostLoad → OnConstruction (também no editor) → PreInitializeComponents → InitializeComponent dos componentes → PostInitializeComponents → BeginPlay (dos componentes e do ator) → Tick a cada frame. Ao sair: EndPlay(EEndPlayReason) quando é destruído, o nível descarrega ou o jogo para → Destroyed → coleta de lixo. Libere timers, delegates e recursos em EndPlay, não no destrutor.

## Componentes: tipos
- UActorComponent: comportamento sem posição (vida, inventário, lógica). Não tem transform.
- USceneComponent: tem transform e pode ter filhos (pontos de referência, pivôs).
- UPrimitiveComponent (deriva de Scene): tem geometria, renderização e/ou colisão: UStaticMeshComponent, USkeletalMeshComponent, UBoxComponent, USphereComponent, UCapsuleComponent.
- Outros comuns: UCameraComponent, USpringArmComponent, UAudioComponent, UNiagaraComponent, UWidgetComponent, UArrowComponent, UProjectileMovementComponent, URotatingMovementComponent, UInstancedStaticMeshComponent, USplineComponent.

## Componentes: criar no construtor e anexar
```cpp
AMyDoor::AMyDoor()
{
    PrimaryActorTick.bCanEverTick = false;
    Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
    SetRootComponent(Root);
    Frame = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Frame"));
    Frame->SetupAttachment(Root);
    Trigger = CreateDefaultSubobject<UBoxComponent>(TEXT("Trigger"));
    Trigger->SetupAttachment(Root);
    Trigger->SetBoxExtent(FVector(100.f, 100.f, 100.f));
}
```
No construtor use SetupAttachment; em tempo de execução, AttachToComponent(Pai, FAttachmentTransformRules::SnapToTargetNotIncludingScale, SocketName). Para criar componentes de ator só depois de spawnado, use NewObject + RegisterComponent.

## Tick: configurar e evitar excesso
PrimaryActorTick.bCanEverTick = true habilita; bStartWithTickEnabled controla se começa ligado; SetActorTickEnabled(true/false) liga e desliga; PrimaryActorTick.TickInterval = 0.2f roda 5 vezes por segundo; TickGroup (TG_PrePhysics, TG_DuringPhysics, TG_PostPhysics, TG_PostUpdateWork) define a ordem relativa à física; AddTickPrerequisiteActor garante ordem entre atores. Componentes têm PrimaryComponentTick. Sempre multiplique movimento por DeltaTime. Prefira timers e eventos para lógica que não precisa de todo frame.

## Timers
```cpp
FTimerHandle RegenHandle;
GetWorldTimerManager().SetTimer(RegenHandle, this, &AMyCharacter::Regen, 1.0f, true, 2.0f); // a cada 1 s, começando em 2 s
GetWorldTimerManager().ClearTimer(RegenHandle);
GetWorldTimerManager().SetTimerForNextTick(this, &AMyCharacter::LateInit);
// com lambda
GetWorldTimerManager().SetTimer(RegenHandle, FTimerDelegate::CreateWeakLambda(this, [this]() { Regen(); }), 1.0f, false);
```
Timers respeitam a pausa e a dilatação de tempo do mundo. Limpe-os em EndPlay (ou use ClearAllTimersForObject(this)). Use CreateWeakLambda/CreateUObject para que o timer não chame um objeto destruído.

## Spawn e destruição de atores
```cpp
FActorSpawnParameters Params;
Params.Owner = this;
Params.Instigator = GetInstigator();
Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;
AProjectile* P = GetWorld()->SpawnActor<AProjectile>(ProjectileClass, Muzzle->GetComponentTransform(), Params);
```
Para configurar antes do BeginPlay: SpawnActorDeferred<T>(Classe, Transform, Owner, Instigator), defina propriedades e chame UGameplayStatics::FinishSpawningActor(Ator, Transform). Destruir: Destroy() ou SetLifeSpan(Segundos). Em multiplayer, spawne atores replicados apenas no servidor. Para muitos objetos de vida curta (tiros, efeitos), use um pool em vez de spawn/destroy constante.

## Eventos de colisão: overlap e hit
```cpp
// no BeginPlay (não no construtor, para não ser sobrescrito pela serialização do Blueprint)
Trigger->OnComponentBeginOverlap.AddDynamic(this, &AMyDoor::OnOverlapBegin);
Mesh->OnComponentHit.AddDynamic(this, &AMyDoor::OnHit);

UFUNCTION()
void OnOverlapBegin(UPrimitiveComponent* OverlappedComp, AActor* OtherActor, UPrimitiveComponent* OtherComp,
                    int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult);
UFUNCTION()
void OnHit(UPrimitiveComponent* HitComp, AActor* OtherActor, UPrimitiveComponent* OtherComp,
           FVector NormalImpulse, const FHitResult& Hit);
```
As funções ligadas com AddDynamic precisam ser UFUNCTION e ter a assinatura exata. Overlap exige Generate Overlap Events ligado nos dois componentes e resposta Overlap no canal. Hit exige Block, e para objetos com física, Simulation Generates Hit Events. Ator inteiro: OnActorBeginOverlap e NotifyActorBeginOverlap (sobrescrevível).

## Delegates: declarar, ligar e disparar
```cpp
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnHealthChanged, float, NewHealth, float, Delta);

UPROPERTY(BlueprintAssignable, Category = "Health")
FOnHealthChanged OnHealthChanged;

OnHealthChanged.Broadcast(Health, -Damage);              // dispara
OnHealthChanged.AddDynamic(this, &UMyHud::HandleHealth); // liga (função UFUNCTION)
OnHealthChanged.RemoveDynamic(this, &UMyHud::HandleHealth);
```
Delegates não dinâmicos (DECLARE_MULTICAST_DELEGATE) são mais rápidos e aceitam lambdas: Handle = Delegate.AddUObject(this, &X::F) ou AddLambda; remova com Remove(Handle). Use dinâmicos quando precisar de Blueprint (BlueprintAssignable) ou serialização. Sempre desligue em EndPlay quando o ouvinte vive menos que o emissor.

## Interfaces em C++
```cpp
UINTERFACE(MinimalAPI, Blueprintable)
class UInteractable : public UInterface { GENERATED_BODY() };

class MYGAME_API IInteractable
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintNativeEvent, BlueprintCallable, Category = "Interaction")
    void Interact(AActor* Instigator);
};

// implementar: class AChest : public AActor, public IInteractable
// virtual void Interact_Implementation(AActor* Instigator) override;

// chamar (funciona para implementações em C++ e em Blueprint):
if (Target && Target->Implements<UInteractable>())
{
    IInteractable::Execute_Interact(Target, this);
}
```
Com funções BlueprintNativeEvent/ImplementableEvent, sempre chame via Execute_NomeDaFuncao: um Cast<IInteractable> falha quando a interface foi adicionada só no Blueprint.

## Subsistemas
```cpp
UCLASS()
class MYGAME_API UInventorySubsystem : public UGameInstanceSubsystem
{
    GENERATED_BODY()
public:
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;
};
// uso
UInventorySubsystem* Inv = GetGameInstance()->GetSubsystem<UInventorySubsystem>();
```
Tipos e vida: UEngineSubsystem (engine inteira), UEditorSubsystem (editor), UGameInstanceSubsystem (sessão de jogo), UWorldSubsystem e UTickableWorldSubsystem (cada mundo/mapa, incluindo PIE), ULocalPlayerSubsystem (cada jogador local; o Enhanced Input usa). Sobrescreva ShouldCreateSubsystem para criar só em certas condições (ex.: só no servidor). Em Blueprint aparecem como nós de acesso automáticos. Substituem singletons e "managers" colocados no nível.

## Componentes reutilizáveis: exemplo de vida
Um UHealthComponent (UActorComponent) com MaxHealth, Health, ApplyDamage e delegates OnHealthChanged/OnDeath pode ser adicionado a qualquer ator (jogador, inimigo, barril). Para integrar com o sistema de dano da engine, no BeginPlay do componente ligue GetOwner()->OnTakeAnyDamage.AddDynamic(this, &UHealthComponent::HandleDamage) e aplique dano com UGameplayStatics::ApplyDamage / ApplyPointDamage / ApplyRadialDamage. Em multiplayer, altere Health só no servidor e replique com RepNotify.

## Line trace e sweep
```cpp
FHitResult Hit;
FVector Start = Camera->GetComponentLocation();
FVector End = Start + Camera->GetForwardVector() * 1000.f;
FCollisionQueryParams Params(SCENE_QUERY_STAT(Interact), false, this); // ignora o próprio ator
if (GetWorld()->LineTraceSingleByChannel(Hit, Start, End, ECC_Visibility, Params))
{
    AActor* HitActor = Hit.GetActor();
}
DrawDebugLine(GetWorld(), Start, End, FColor::Red, false, 2.f);
```
Variações: LineTraceMultiByChannel, SweepSingleByChannel com FCollisionShape::MakeSphere(Raio), OverlapMultiByObjectType, traces por ObjectType ou por Profile. Crie canais próprios em Project Settings > Collision (aparecem como ECC_GameTraceChannel1...).

## Tags de ator e de componente
Actor->Tags (TArray<FName>) e ActorHasTag(FName("Inimigo")) são simples para marcações rápidas. Para sistemas maiores, prefira Gameplay Tags (FGameplayTag, FGameplayTagContainer, hierárquicas como Status.Debuff.Stun), definidas em Project Settings > GameplayTags ou em arquivos .ini, com consultas HasTag e HasAny/HasAll. Interfaces IGameplayTagAssetInterface permitem consultar tags de qualquer ator.
