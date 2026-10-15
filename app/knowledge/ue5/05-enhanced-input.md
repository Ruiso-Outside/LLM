# 05 Enhanced Input (UE5)

## Enhanced Input: conceitos
O Enhanced Input é o sistema de controles padrão da UE5. Assets: Input Action (IA_*, a ação com Value Type: Digital bool, Axis1D float, Axis2D Vector2D, Axis3D Vector) e Input Mapping Context (IMC_*, liga teclas e botões às ações, com modificadores e gatilhos). Os contextos são adicionados ao UEnhancedInputLocalPlayerSubsystem do jogador local com prioridade; vários contextos podem estar ativos ao mesmo tempo. O módulo EnhancedInput precisa estar no Build.cs para C++.

## Enhanced Input: modificadores (Modifiers)
Negate (inverte, para S e A no movimento), Swizzle Input Axis Values (troca X e Y, para W e S mapearem no eixo Y), Dead Zone (zona morta do analógico), Scalar (multiplica), Response Curve, Smooth, FOV Scaling. Exemplo de IA_Move (Axis2D): W com Swizzle; S com Swizzle + Negate; D sem modificador; A com Negate; analógico esquerdo com Dead Zone.

## Enhanced Input: gatilhos (Triggers)
Down (padrão, enquanto pressionado), Pressed (uma vez ao apertar), Released (ao soltar), Hold (após segurar X segundos), Hold And Release, Tap (apertar e soltar rápido), Pulse (repete em intervalos), Chorded Action (só vale com outra ação ativa, ex.: Shift + tecla), Combo. Eventos disparados: Started, Ongoing, Triggered, Completed, Canceled. Para pular, use Started (ou Triggered com gatilho Pressed); para ações contínuas como mover, Triggered.

## Enhanced Input: configuração em C++ no Character
```cpp
// .h
UPROPERTY(EditDefaultsOnly, Category = "Input") TObjectPtr<UInputMappingContext> DefaultContext;
UPROPERTY(EditDefaultsOnly, Category = "Input") TObjectPtr<UInputAction> MoveAction;
UPROPERTY(EditDefaultsOnly, Category = "Input") TObjectPtr<UInputAction> JumpAction;

// .cpp
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"

void AMyCharacter::NotifyControllerChanged()
{
    Super::NotifyControllerChanged();
    if (APlayerController* PC = Cast<APlayerController>(Controller))
    {
        if (auto* Sub = ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(PC->GetLocalPlayer()))
        {
            Sub->AddMappingContext(DefaultContext, 0);
        }
    }
}

void AMyCharacter::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
    Super::SetupPlayerInputComponent(PlayerInputComponent);
    if (auto* EIC = Cast<UEnhancedInputComponent>(PlayerInputComponent))
    {
        EIC->BindAction(MoveAction, ETriggerEvent::Triggered, this, &AMyCharacter::Move);
        EIC->BindAction(JumpAction, ETriggerEvent::Started, this, &ACharacter::Jump);
        EIC->BindAction(JumpAction, ETriggerEvent::Completed, this, &ACharacter::StopJumping);
    }
}

void AMyCharacter::Move(const FInputActionValue& Value)
{
    const FVector2D Axis = Value.Get<FVector2D>();
    const FRotator Yaw(0.f, Controller->GetControlRotation().Yaw, 0.f);
    AddMovementInput(FRotationMatrix(Yaw).GetUnitAxis(EAxis::X), Axis.Y);
    AddMovementInput(FRotationMatrix(Yaw).GetUnitAxis(EAxis::Y), Axis.X);
}
```
Os templates de terceira e primeira pessoa trazem esse código pronto.

## Enhanced Input: trocar contextos (a pé, veículo, menu)
Crie IMC_Pe, IMC_Veiculo e IMC_Menu. Ao entrar no veículo, RemoveMappingContext(IMC_Pe) e AddMappingContext(IMC_Veiculo, 0), ou mantenha ambos com prioridades diferentes (o de maior prioridade vence quando a mesma tecla aparece nos dois). Um IMC_Global com pausa pode ficar sempre ativo. ClearAllMappings remove tudo.

## Enhanced Input: remapeamento pelo jogador
Marque as ações/teclas como mapeáveis (Player Mappable Key Settings, com um nome único) e use as Enhanced Input User Settings (habilitadas em Project Settings > Enhanced Input > User Settings). Em tempo de execução, a UEnhancedInputUserSettings do subsistema permite MapPlayerKey/UnMapPlayerKey, salvar (SaveSettings) e consultar as teclas atuais para exibir na interface. O CommonUI integra os ícones de teclas por plataforma.

## Enhanced Input: input com o jogo pausado e na UI
Ações precisam de bTriggerWhenPaused (Trigger when Paused no Input Action) para funcionar com o jogo pausado. Ao abrir menus: SetInputMode(FInputModeUIOnly ou FInputModeGameAndUI) e bShowMouseCursor = true no PlayerController; ao voltar, FInputModeGameOnly. No CommonUI, o modo de input é controlado pelas ativações das telas (GetDesiredInputConfig).

## Enhanced Input: injetar input e depurar
O comando de console showdebug enhancedinput mostra contextos e ações ativas. Para testes automatizados ou IA, o subsistema tem InjectInputForAction. Input Debug Key e o Input Action Value aparecem também no Blueprint Debugger.

## Enhanced Input: Blueprints
No Blueprint do personagem ou do controller: no BeginPlay, Get Player Controller > Get Enhanced Input Local Player Subsystem > Add Mapping Context. Clique com o botão direito no grafo e digite o nome da ação (EnhancedInputAction IA_Jump) para criar o evento com os pinos Triggered, Started, Ongoing, Canceled e Completed, e o valor da ação.
