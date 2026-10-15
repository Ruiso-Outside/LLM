# 09 Animação (UE5)

## Animação: assets
Skeleton (hierarquia de ossos, compartilhável entre malhas), Skeletal Mesh, Physics Asset (corpos de colisão por osso, ragdoll), Animation Sequence (animação), Blend Space (mistura por 1 ou 2 parâmetros), Aim Offset (blend space aditivo para mirar), Anim Montage (animação tocada sob comando, com seções e slots), Pose Asset, Animation Blueprint, IK Rig, IK Retargeter, Control Rig, Pose Search Database (Motion Matching).

## Animation Blueprint: estrutura
Event Graph: lê dados do personagem (Event Blueprint Update Animation; Try Get Pawn Owner, velocidade, se está caindo, direção). Anim Graph: monta a pose com State Machines, Blend Spaces, Layered Blend per Bone, Slots e Output Pose. Em C++, crie uma classe derivada de UAnimInstance e sobrescreva NativeInitializeAnimation e NativeUpdateAnimation (ou NativeThreadSafeUpdateAnimation para rodar fora da thread principal) para calcular as variáveis; o Animation Blueprint herda dela. Use Property Access e funções Thread Safe para desempenho.

## Animation Blueprint: C++ base
```cpp
UCLASS()
class MYGAME_API UMyAnimInstance : public UAnimInstance
{
    GENERATED_BODY()
protected:
    virtual void NativeInitializeAnimation() override;
    virtual void NativeUpdateAnimation(float DeltaSeconds) override;
    UPROPERTY(BlueprintReadOnly, Category = "Locomotion") float GroundSpeed = 0.f;
    UPROPERTY(BlueprintReadOnly, Category = "Locomotion") bool bIsFalling = false;
    UPROPERTY() TObjectPtr<ACharacter> Character;
};

void UMyAnimInstance::NativeInitializeAnimation()
{
    Super::NativeInitializeAnimation();
    Character = Cast<ACharacter>(TryGetPawnOwner());
}
void UMyAnimInstance::NativeUpdateAnimation(float DeltaSeconds)
{
    Super::NativeUpdateAnimation(DeltaSeconds);
    if (!Character) return;
    GroundSpeed = Character->GetVelocity().Size2D();
    bIsFalling = Character->GetCharacterMovement()->IsFalling();
}
```

## State Machine de locomoção
Estados típicos: Idle/Walk/Run (um Blend Space por velocidade), JumpStart, FallLoop, Land. Transições com regras (bIsFalling verdadeiro; Time Remaining Ratio < 0,1; Automatic Rule Based on Sequence Player). Duração da transição suaviza a troca. Conduits agrupam regras; State Aliases evitam dezenas de setas. Para jogos grandes, use Linked Anim Layers (camadas de animação trocáveis por arma ou estado) como no Lyra.

## Blend Spaces e Aim Offset
Blend Space 2D: eixo horizontal Direção (-180 a 180) e vertical Velocidade (0 a 600), com animações de andar e correr em cada direção. Blend Space 1D: só velocidade. Aim Offset: poses aditivas de mirar (cima, baixo, esquerda, direita) misturadas por Pitch e Yaw da mira; as animações precisam ser aditivas (Additive Anim Type = Mesh Space, com pose base). Ajuste Smoothing Time para suavizar mudanças de parâmetro.

## Anim Montages
Usadas para ataques, recarregar, interações e emotes. Seções (Sections) permitem combos e loops (Montage_JumpToSection, Montage_SetNextSection). Slots definem onde tocam (DefaultSlot no corpo inteiro; UpperBody com Layered Blend per Bone a partir de spine_01 para tocar só no tronco enquanto as pernas andam). Em C++: AnimInstance->Montage_Play(Montage, Rate), Montage_Stop, Montage_IsPlaying, delegates OnMontageEnded e OnMontageBlendingOut; no Character, PlayAnimMontage. Em multiplayer, toque montages com um Multicast ou por replicação de estado (o GAS tem PlayMontageAndWait com replicação embutida).

## Anim Notifies e Notify States
Notifies disparam eventos num quadro exato: Play Sound, Play Niagara Effect, ou eventos personalizados (AnimNotify_Nome no Anim Blueprint). Notify States têm início e fim: janelas de dano de espada, invencibilidade, rastro de arma. Em C++, derive de UAnimNotify (Notify) ou UAnimNotifyState (NotifyBegin, NotifyTick, NotifyEnd). Notifies em montages tocadas no servidor dedicado podem não disparar se a malha não estiver atualizando: configure VisibilityBasedAnimTickOption como AlwaysTickPoseAndRefreshBones no servidor quando a lógica depender de notifies.

## IK e ajuste de pés
Two Bone IK, FABRIK, CCDIK e Look At no Anim Graph. Para pés se adaptando ao terreno, use Control Rig com traces (o Control Rig de exemplo dos personagens Manny/Quinn) ou o nó Leg IK com traces calculados no Event Graph. O plugin Full Body IK resolve cadeias completas. Para segurar armas com as duas mãos, IK da mão de apoio até um socket na arma.

## Control Rig
Sistema de rig dentro da Unreal: animar no Sequencer com controles (Bake to Animation Sequence para salvar) e ajustes procedurais em tempo de jogo pelo nó Control Rig no Anim Graph (foot IK, olhar para alvo, recuo procedural). Modular Control Rig (versões recentes) monta rigs a partir de módulos prontos.

## Retargeting (IK Rig e IK Retargeter)
1) Crie um IK Rig para cada esqueleto, definindo o Retarget Root (pélvis) e as Retarget Chains (coluna, cabeça, braços, pernas; existe criação automática para esqueletos conhecidos). 2) Crie um IK Retargeter ligando origem e destino, ajuste a pose de retarget (ex.: A-pose para T-pose) e confira o mapeamento das cadeias. 3) Exporte as animações (Export Selected Animations). Versões recentes oferecem retargeting automático rápido para esqueletos parecidos com o do Manny/Quinn (botão direito na animação > Retarget Animations).

## Motion Matching
Em vez de uma State Machine com dezenas de transições, o Motion Matching escolhe a cada momento o trecho de animação de uma base (Pose Search Database) que melhor combina com a pose atual e a trajetória desejada. Peças: plugin Pose Search, Pose Search Schema (o que comparar: ossos, trajetória), Pose Search Database (as animações), nó Motion Matching no Anim Graph e o componente de trajetória (Character Trajectory). Ficou completo para produção a partir da UE 5.4; o Game Animation Sample da Epic traz uma configuração pronta com centenas de animações.

## Ragdoll e física de personagem
Ragdoll: GetMesh()->SetSimulatePhysics(true) com o perfil de colisão Ragdoll e Physics Asset configurado; desligue a cápsula. Physical Animation Component mistura física com animação (personagem reagindo a impactos). Em multiplayer, ragdoll normalmente é só cosmético e local.

## Otimização de animação
Update Rate Optimizations (URO) reduzem a frequência de atualização de malhas distantes; Visibility Based Anim Tick Option (não atualizar quando não renderizado); LODs da malha com menos ossos; Anim Budget Allocator (plugin) para limitar o custo total; Animation Sharing para multidões; desabilitar bEnableUpdateRateOptimizations só quando necessário. Leader Pose Component (antigo Master Pose) para malhas modulares (roupas, cabelo) que seguem a malha principal sem custo de animação próprio.
