# 08 Gameplay Ability System — GAS (UE5)

## GAS: o que é e quando usar
O Gameplay Ability System é um framework para habilidades, atributos (vida, mana, stamina), efeitos (dano, buffs, debuffs, custos, recargas) e tags, com replicação e previsão no cliente embutidas. Ideal para RPGs, MOBAs, shooters com habilidades e qualquer jogo com muitos modificadores. Tem curva de aprendizado alta; para jogos simples, componentes próprios podem bastar. Habilite o plugin Gameplay Abilities e adicione os módulos GameplayAbilities, GameplayTags e GameplayTasks ao Build.cs. O projeto de exemplo Lyra usa GAS extensivamente.

## GAS: peças principais
- UAbilitySystemComponent (ASC): o componente central que guarda atributos, habilidades concedidas, efeitos ativos e tags.
- UAttributeSet: define os atributos (FGameplayAttributeData) e reage a mudanças.
- UGameplayAbility (GA): uma habilidade (atirar, pular, curar) com ativação, custo, recarga e fim.
- UGameplayEffect (GE): altera atributos e tags (instantâneo, com duração ou infinito; pode ser periódico).
- Gameplay Tags: estados e categorias (State.Stunned, Ability.Fire, Cooldown.Dash).
- Gameplay Cues: efeitos cosméticos (som, partículas) disparados por tags GameplayCue.*, replicados de forma barata.
- Ability Tasks: ações assíncronas dentro de habilidades (PlayMontageAndWait, WaitTargetData, WaitGameplayEvent, WaitDelay).

## GAS: onde colocar o ASC
No Pawn: simples, mas atributos e efeitos se perdem quando o Pawn morre e é recriado (bom para inimigos e IA). No PlayerState: persiste entre respawns (padrão para jogadores em multiplayer); o Pawn implementa IAbilitySystemInterface retornando o ASC do PlayerState. Inicialize com ASC->InitAbilityActorInfo(Owner, Avatar): OwnerActor é quem possui (PlayerState), AvatarActor é o corpo (Pawn). Chame no servidor em PossessedBy e no cliente em OnRep_PlayerState.

## GAS: modo de replicação do ASC
SetReplicationMode: Full (tudo replicado para todos; single-player ou poucos atores), Mixed (efeitos completos só para o dono, tags e cues para todos; recomendado para jogadores em multiplayer), Minimal (só tags e cues; recomendado para IA). Com ASC no PlayerState, aumente o NetUpdateFrequency do PlayerState (ex.: 100), pois o padrão é baixo e atrasa as atualizações.

## GAS: AttributeSet
```cpp
#include "AttributeSet.h"
#include "AbilitySystemComponent.h"

#define ATTRIBUTE_ACCESSORS(ClassName, PropertyName) \
    GAMEPLAYATTRIBUTE_PROPERTY_GETTER(ClassName, PropertyName) \
    GAMEPLAYATTRIBUTE_VALUE_GETTER(PropertyName) \
    GAMEPLAYATTRIBUTE_VALUE_SETTER(PropertyName) \
    GAMEPLAYATTRIBUTE_VALUE_INITTER(PropertyName)

UCLASS()
class MYGAME_API UMyAttributeSet : public UAttributeSet
{
    GENERATED_BODY()
public:
    UPROPERTY(BlueprintReadOnly, ReplicatedUsing = OnRep_Health) FGameplayAttributeData Health;
    ATTRIBUTE_ACCESSORS(UMyAttributeSet, Health)
    UPROPERTY(BlueprintReadOnly, ReplicatedUsing = OnRep_MaxHealth) FGameplayAttributeData MaxHealth;
    ATTRIBUTE_ACCESSORS(UMyAttributeSet, MaxHealth)
    UPROPERTY(BlueprintReadOnly) FGameplayAttributeData IncomingDamage;   // meta-atributo, não replicado
    ATTRIBUTE_ACCESSORS(UMyAttributeSet, IncomingDamage)

    virtual void PreAttributeChange(const FGameplayAttribute& Attribute, float& NewValue) override;
    virtual void PostGameplayEffectExecute(const FGameplayEffectModCallbackData& Data) override;
    virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
    UFUNCTION() void OnRep_Health(const FGameplayAttributeData& Old) { GAMEPLAYATTRIBUTE_REPNOTIFY(UMyAttributeSet, Health, Old); }
    UFUNCTION() void OnRep_MaxHealth(const FGameplayAttributeData& Old) { GAMEPLAYATTRIBUTE_REPNOTIFY(UMyAttributeSet, MaxHealth, Old); }
};
```
Replique com DOREPLIFETIME_CONDITION_NOTIFY(UMyAttributeSet, Health, COND_None, REPNOTIFY_Always). Use PreAttributeChange para limitar o valor atual (clamp) e PostGameplayEffectExecute para lógica após efeitos (converter IncomingDamage em perda de Health, detectar morte). Crie o AttributeSet como subobjeto do dono do ASC (CreateDefaultSubobject no PlayerState ou Pawn).

## GAS: Gameplay Effects
Duration Policy: Instant (altera o valor base permanentemente, como dano), Has Duration (temporário, como buff de 10 s), Infinite (até ser removido, como uma aura). Modifiers: Add, Multiply, Divide, Override, com magnitude Scalable Float (com Curve Table por nível), Attribute Based, Set By Caller (valor passado em tempo de execução por uma tag, ex.: Data.Damage) ou Custom Calculation Class. Execution Calculations (UGameplayEffectExecutionCalculation) fazem cálculos complexos de dano com atributos do atacante e do alvo. Period: efeito periódico (veneno a cada 1 s). Stacking: como acumula. Tags concedidas (Granted Tags), requisitos (Application/Ongoing Tag Requirements) e imunidades.

## GAS: aplicar um efeito em C++
```cpp
FGameplayEffectContextHandle Ctx = SourceASC->MakeEffectContext();
Ctx.AddSourceObject(this);
FGameplayEffectSpecHandle Spec = SourceASC->MakeOutgoingSpec(DamageEffectClass, AbilityLevel, Ctx);
if (Spec.IsValid())
{
    Spec.Data->SetSetByCallerMagnitude(FGameplayTag::RequestGameplayTag(TEXT("Data.Damage")), 25.f);
    SourceASC->ApplyGameplayEffectSpecToTarget(*Spec.Data.Get(), TargetASC);
}
```
Aplique efeitos no servidor (ou em habilidades com previsão). Para obter o ASC de qualquer ator: UAbilitySystemBlueprintLibrary::GetAbilitySystemComponent(Actor).

## GAS: Gameplay Abilities
Ciclo: CanActivateAbility (checa custo, recarga e tags) → ActivateAbility → CommitAbility (aplica custo e recarga) → lógica (Ability Tasks) → EndAbility. Políticas: Instancing Policy (InstancedPerActor recomendado; NonInstanced para habilidades simples sem estado), Net Execution Policy (LocalPredicted: roda no cliente na hora e no servidor, padrão para habilidades do jogador; ServerOnly; LocalOnly; ServerInitiated). Tags: Ability Tags, Cancel Abilities With Tag, Block Abilities With Tag, Activation Owned Tags (tags enquanto ativa, ex.: State.Attacking), Activation Required/Blocked Tags. Custo (Cost Gameplay Effect) e recarga (Cooldown Gameplay Effect com uma tag Cooldown.*).

## GAS: conceder e ativar habilidades
Conceda no servidor: ASC->GiveAbility(FGameplayAbilitySpec(AbilityClass, Level, InputID, SourceObject)). Ative por classe (TryActivateAbilityByClass), por tags (TryActivateAbilitiesByTag) ou por evento (SendGameplayEventToActor com uma tag de evento e a habilidade configurada com Ability Triggers). Para ligar ao Enhanced Input, um padrão comum (usado no Lyra) é associar Input Actions a Input Tags num Data Asset e, ao pressionar, procurar specs com a tag e chamar AbilitySpecInputPressed/TryActivateAbility.

## GAS: Gameplay Cues
Tags GameplayCue.* (ex.: GameplayCue.Hit.Fire). Dois tipos: GameplayCueNotify_Static (efeitos instantâneos, sem instância: som de impacto) e GameplayCueNotify_Actor (efeitos persistentes que começam e terminam: aura). São disparados por Gameplay Effects (Gameplay Cues no GE) ou manualmente (ExecuteGameplayCue, AddGameplayCue). São cosméticos: nunca coloque lógica de jogo neles. Em servidores dedicados não precisam rodar.

## GAS: escutar mudanças de atributos (UI)
ASC->GetGameplayAttributeValueChangeDelegate(UMyAttributeSet::GetHealthAttribute()).AddUObject(this, &UMyWidgetController::OnHealthChanged) recebe FOnAttributeChangeData (OldValue, NewValue). Para tags: RegisterGameplayTagEvent(Tag, EGameplayTagEventType::NewOrRemoved). Em Blueprint, as Ability Async tasks (Wait For Attribute Changed, Wait Gameplay Tag Added) fazem o mesmo.

## GAS: erros comuns
Esquecer InitAbilityActorInfo no cliente (habilidades não ativam e a UI não atualiza); ASC no PlayerState com NetUpdateFrequency baixo (atrasos); aplicar efeitos no cliente sem previsão; esquecer de chamar UAbilitySystemGlobals::Get().InitGlobalData() em versões antigas (nas recentes é automático); habilidades que nunca chamam EndAbility (ficam ativas e bloqueiam outras); modificar atributos diretamente (SetHealth) em vez de por Gameplay Effects, perdendo previsão e replicação; tags digitadas erradas (prefira declarar tags nativas em C++ com UE_DEFINE_GAMEPLAY_TAG).

## GAS: tags nativas em C++
```cpp
// MyTags.h
#include "NativeGameplayTags.h"
UE_DECLARE_GAMEPLAY_TAG_EXTERN(TAG_State_Stunned);
// MyTags.cpp
UE_DEFINE_GAMEPLAY_TAG_COMMENT(TAG_State_Stunned, "State.Stunned", "Personagem atordoado");
```
Assim as tags existem sem digitar strings e erros aparecem na compilação.
