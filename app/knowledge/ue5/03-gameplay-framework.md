# 03 Gameplay Framework (UE5)

## Gameplay Framework: visão geral das classes
- UGameInstance: um por execução do jogo; sobrevive à troca de mapas. Dados globais, sessões online, subsistemas de jogo.
- AGameModeBase / AGameMode: regras da partida. Existe SÓ no servidor. Define as classes padrão (Pawn, PlayerController, PlayerState, GameState, HUD) e faz login e spawn dos jogadores.
- AGameStateBase / AGameState: estado da partida replicado para todos (placar, tempo, fase). Tem a lista PlayerArray com os PlayerStates.
- APlayerController: a "vontade" do jogador. Existe no servidor e no cliente dono. Input, câmera, HUD, RPCs do jogador.
- APlayerState: dados públicos de um jogador, replicados para todos (nome, pontuação, time); sobrevive à morte do Pawn e pode sobreviver a reconexões.
- APawn: um ator que pode ser possuído (possessed) por um Controller.
- ACharacter: Pawn com UCapsuleComponent, USkeletalMeshComponent e UCharacterMovementComponent (andar, pular, nadar, voar, com previsão de rede).
- AHUD: desenho de HUD antigo e dono de widgets; hoje a UI fica em UMG.
- AAIController: controlador de IA.

## GameMode x GameModeBase
AGameModeBase é a base simples. AGameMode adiciona o fluxo de partida (MatchState: EnteringMap, WaitingToStart, InProgress, WaitingPostMatch, LeavingMap), com funções como StartMatch, EndMatch e ReadyToStartMatch. Use AGameMode com AGameState (não misture GameMode com GameStateBase, nem GameModeBase com GameState: dá erro de compatibilidade no log).

## Fluxo de entrada de um jogador
No servidor: PreLogin (pode recusar), Login (cria o PlayerController), PostLogin (jogador conectado; bom ponto para inicializar dados), HandleStartingNewPlayer, RestartPlayer (escolhe o PlayerStart com ChoosePlayerStart e cria o Pawn com SpawnDefaultPawnFor), Possess. Na saída: Logout. Sobrescreva no seu GameMode para regras próprias (times, pontos de spawn).

## Onde guardar cada dado (multiplayer)
Regras e decisões: GameMode (servidor). Estado da partida visível a todos: GameState. Dados públicos do jogador: PlayerState. Input, UI e dados privados do jogador: PlayerController. Corpo e estado físico no mundo: Pawn/Character. Dados entre mapas e da sessão local: GameInstance. Erros comuns: ler o GameMode num cliente (retorna nulo), guardar a pontuação no Character (perde ao morrer) ou guardar dados de partida na GameInstance esperando que replique (ela não replica).

## Acessar as classes do framework em C++
```cpp
UWorld* World = GetWorld();
AGameModeBase* GM = World->GetAuthGameMode();              // nulo em clientes
AGameStateBase* GS = World->GetGameState();
APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0); // jogador local 0
APawn* Pawn = PC ? PC->GetPawn() : nullptr;
UGameInstance* GI = GetGameInstance();
APlayerState* PS = Pawn ? Pawn->GetPlayerState() : nullptr;
```
Faça Cast<AMyGameMode>(GM) para o tipo concreto. Em código de jogo multiplayer, evite GetPlayerController(this, 0) no servidor: ele pega o primeiro jogador, não o "dono" do contexto; prefira Pawn->GetController() ou o Owner.

## Possessão e controle
Controller->Possess(Pawn) e UnPossess(). O Pawn recebe PossessedBy (servidor) e o cliente recebe OnRep_Controller/notificações de controle; para lógica que depende de o controlador estar pronto tanto no servidor quanto no cliente, APawn::NotifyControllerChanged e o evento Receive Controller Changed (Blueprint) ajudam. Para input local, configure o Enhanced Input em SetupPlayerInputComponent (Pawn) ou em PawnClientRestart / OnPossess (controller).

## Character Movement Component
Configurações principais: MaxWalkSpeed, MaxAcceleration, BrakingDecelerationWalking, GroundFriction, JumpZVelocity, AirControl, GravityScale, MaxStepHeight (degrau, padrão 45), WalkableFloorAngle (rampa máxima, ~44,76°), bOrientRotationToMovement (vira o personagem na direção do movimento), RotationRate, bUseControllerDesiredRotation, NavAgentProps (para IA). Modos de movimento: Walking, NavWalking, Falling, Swimming, Flying, Custom. O CMC tem previsão no cliente e correção do servidor embutidas; movimentos customizados que precisam funcionar em rede devem ser implementados dentro do CMC (flags salvas no FSavedMove) e não só alterando a velocidade num RPC.

## Câmeras: terceira pessoa, primeira pessoa e top-down
Terceira pessoa: USpringArmComponent (TargetArmLength, bUsePawnControlRotation=true, bDoCollisionTest) com UCameraComponent filha; no Character, bUseControllerRotationYaw=false e bOrientRotationToMovement=true. Primeira pessoa: câmera presa à cabeça (socket) ou à cápsula com bUsePawnControlRotation=true e bUseControllerRotationYaw=true; malha de braços com OnlyOwnerSee e corpo com OwnerNoSee. Top-down: Spring Arm com rotação fixa (pitch -60), sem herdar rotação do controle. APlayerCameraManager controla a câmera final (shakes, limites de pitch, fades) e pode ser customizado.

## GameInstance e subsistemas
UGameInstance::Init roda uma vez no início; Shutdown no fim. Melhor que encher a GameInstance de código é usar UGameInstanceSubsystem: classes que a engine cria automaticamente com a mesma vida da GameInstance, acessadas com GetGameInstance()->GetSubsystem<UMySubsystem>(). Outros tipos: UWorldSubsystem (por mundo/mapa), ULocalPlayerSubsystem (por jogador local), UEngineSubsystem, UEditorSubsystem. Ver o arquivo 04.

## Troca de mapa
Single-player: UGameplayStatics::OpenLevel(this, FName("Mapa")) (destrói o mundo atual; só a GameInstance sobrevive). Multiplayer: no servidor, GetWorld()->ServerTravel("/Game/Mapas/Mapa?listen") leva os clientes junto; com bUseSeamlessTravel=true no GameMode, a viagem passa por um mapa de transição e preserva PlayerControllers e PlayerStates (com CopyProperties do PlayerState para levar dados). Para carregar partes do mundo sem trocar o mapa, use Level Streaming ou World Partition.

## PlayerStart e respawn
Coloque atores APlayerStart no nível (pode usar a tag PlayerStartTag para escolher por time). Para respawn: no servidor, destrua ou desposse o Pawn morto e chame GameMode->RestartPlayer(Controller), possivelmente com um timer. Sobrescreva ChoosePlayerStart_Implementation para escolher o ponto (mais longe dos inimigos, por time).

## Cheat Manager e comandos Exec
UCheatManager (configurado no PlayerController em CheatClass) concentra comandos de trapaça para teste: funções UFUNCTION(Exec) chamadas pelo console (god, fly, ghost, slomo, teleport já existem). Em multiplayer, comandos que mudam o estado precisam de um RPC Server. Desativados em Shipping por padrão.
