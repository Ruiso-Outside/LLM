# 14 Física e colisão (UE5, Chaos)

## Colisão: configuração de um componente
Cada UPrimitiveComponent tem: Collision Enabled (NoCollision, QueryOnly para traces e overlaps, PhysicsOnly, QueryAndPhysics), Object Type (WorldStatic, WorldDynamic, Pawn, PhysicsBody, Vehicle, Destructible ou canais próprios) e uma resposta (Ignore, Overlap, Block) para cada canal. Collision Presets (BlockAll, OverlapAllDynamic, Pawn, NoCollision, CharacterMesh, Ragdoll...) agrupam configurações. Crie canais e presets em Project Settings > Engine > Collision.

## Colisão: regras de resposta
Dois objetos se bloqueiam só se ambos derem Block um para o outro. Overlap ocorre se ao menos um der Overlap e nenhum der Ignore, com Generate Overlap Events ligado nos dois. Hit (OnComponentHit) exige Block; para corpos com física, ligue Simulation Generates Hit Events. Visualize com Show > Collision no editor ou o comando show collision.

## Colisão: em C++
```cpp
Mesh->SetCollisionProfileName(TEXT("BlockAllDynamic"));
Mesh->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
Mesh->SetCollisionObjectType(ECC_WorldDynamic);
Mesh->SetCollisionResponseToAllChannels(ECR_Ignore);
Mesh->SetCollisionResponseToChannel(ECC_Pawn, ECR_Block);
Mesh->SetGenerateOverlapEvents(true);
Mesh->SetNotifyRigidBodyCollision(true);  // "Simulation Generates Hit Events"
```
Canais personalizados viram ECC_GameTraceChannelN; defina constantes com nomes claros num header (#define ECC_Interact ECC_GameTraceChannel1).

## Colisão de malhas estáticas
No editor da Static Mesh: Show > Simple Collision. Crie formas simples (Collision > Add Box/Sphere/Capsule Simplified Collision, Auto Convex Collision) ou importe com prefixos UCX_/UBX_/USP_/UCP_ do programa 3D. Collision Complexity: Project Simple as Complex (padrão), Use Complex Collision As Simple (usa os triângulos; preciso para escadas e terreno detalhado, mas caro e não serve para simulação física). Objetos que simulam física precisam de colisão simples.

## Personagem atravessando ou travando em objetos
Causas: a malha não tem colisão simples; preset com NoCollision ou Ignore/Overlap para Pawn; degrau acima de MaxStepHeight (45) ou rampa acima de WalkableFloorAngle (~44,76°); escala negativa ou muito grande; objetos finos atravessados em alta velocidade (ative CCD: bUseCCD no corpo físico para objetos rápidos). Para projéteis rápidos, use UProjectileMovementComponent (faz sweep) ou traces em vez de física pura.

## Física: simular corpos
Simulate Physics no componente (Mobility Movable e colisão simples). Propriedades: Mass (kg, ou calculada pelo volume), Linear/Angular Damping, Enable Gravity, Physical Material (atrito, restituição, densidade, tipo de superfície para sons e efeitos). Em C++: AddImpulse(Vetor, NAME_None, bVelChange), AddForce (contínua, no Tick), AddRadialImpulse (explosão), SetPhysicsLinearVelocity. Corpos dormem (sleep) quando param; WakeRigidBody acorda.

## Physical Materials e superfícies
Crie Physical Material assets com Friction, Restitution e Surface Type (configurados em Project Settings > Physics > Physical Surface: Concreto, Metal, Madeira, Terra). O FHitResult traz PhysMaterial; use UGameplayStatics::GetSurfaceType(Hit) para escolher sons de passos e efeitos de impacto por superfície. Aplique no material (Phys Material) ou sobrescreva no componente.

## Constraints
UPhysicsConstraintComponent liga dois corpos: dobradiças (portas físicas), cordas, molas, correntes. Configure limites lineares (Free, Limited, Locked) e angulares (Swing1, Swing2, Twist), motores (Linear/Angular Drive) para mover com força e Break Threshold para quebrar sob carga. Physics Handle (UPhysicsHandleComponent) segura e arrasta objetos com o mouse/arma de gravidade.

## Chaos Destruction
Modo Fracture: selecione a malha > Generate > Geometry Collection; frature (Uniform, Clustered, Radial, Planar, Slice, Brick, Mesh), com níveis hierárquicos. Damage Threshold por nível define quanta força quebra. Quebrar: impactos físicos, Field System (campos de força: FS_MasterField, Radial Falloff, External Strain) ou dano aplicado. Otimize com limites de partículas simuladas, Remove On Sleep/Max Sleep Time e cache de simulação (Chaos Cache Manager) para destruição cinemática pré-gravada.

## Veículos (Chaos Vehicles)
Plugin Chaos Vehicles: classe AWheeledVehiclePawn com UChaosWheeledVehicleMovementComponent; configure rodas (UChaosVehicleWheel: raio, suspensão, atrito, se tem tração/freio/direção), motor (curva de torque, RPM), transmissão (marchas, automática) e direção. A malha precisa de Physics Asset com corpos e os ossos das rodas. Entradas: SetThrottleInput, SetSteeringInput, SetBrakeInput, SetHandbrakeInput. O template Vehicle traz exemplos.

## Física em rede
Física não é determinística entre máquinas: em multiplayer, simule no servidor e replique posição/velocidade (Replicate Movement com Physics), com suavização no cliente. A UE5 tem Network Physics/Physics Prediction (resimulação) em evolução nas versões 5.x para objetos físicos previstos. Para gameplay competitivo, prefira movimento cinemático controlado a física livre em objetos críticos.

## Substepping e estabilidade
Project Settings > Physics: Substepping divide o passo da física em passos menores para estabilidade com FPS baixo (cordas, veículos, ragdolls). Async Physics roda a física numa thread própria em passo fixo. Objetos muito leves ligados a muito pesados ficam instáveis; mantenha razões de massa moderadas (até ~10:1) em constraints.

## Queries de física em lote
Para muitos traces por frame (IA, projéteis), use AsyncLineTraceByChannel (resultado no próximo frame via delegate) para não travar a game thread, e limite a quantidade. Overlaps com formas simples (esfera, caixa) são mais baratos que muitos traces.
