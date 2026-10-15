# 15 Áudio e efeitos visuais (UE5)

## Áudio: assets
Sound Wave (arquivo importado; WAV é o padrão de importação, compressão configurável por plataforma), Sound Cue (grafo antigo de combinação), MetaSound Source (áudio procedural moderno), Sound Attenuation (queda de volume com a distância e espacialização), Sound Class e Sound Class Mix (grupos e volumes: Música, Efeitos, Voz), Sound Submix (mixagem e efeitos de saída), Sound Concurrency (limite de instâncias simultâneas), Reverb Effect e Audio Volume (reverberação por área).

## Áudio: tocar sons em C++
```cpp
UGameplayStatics::PlaySound2D(this, ClickSound);                                // sem posição (UI, música)
UGameplayStatics::PlaySoundAtLocation(this, ExplosionSound, GetActorLocation()); // no mundo, fire-and-forget
UAudioComponent* Engine = UGameplayStatics::SpawnSoundAttached(EngineSound, GetRootComponent());
Engine->SetFloatParameter(TEXT("RPM"), Rpm);   // parâmetro de MetaSound
Engine->FadeOut(1.f, 0.f);
```
Um UAudioComponent no ator dá controle (Play, Stop, volume, pitch, parâmetros). Em servidores dedicados não há áudio: proteja chamadas desnecessárias. Em multiplayer, sons de eventos replicados normalmente tocam via Multicast ou OnRep.

## MetaSounds
Grafo de áudio procedural com execução em tempo real: geradores (osciladores, Wave Player), mixers, filtros, envelopes, matemática e lógica, triggers e entradas (Inputs) expostas ao jogo. Exemplos: tiros com variação aleatória de amostra e pitch (Random Get + Wave Player com Pitch Shift), motor com RPM, passos por superfície. Saída Out Mono/Stereo e On Finished ligado para o som terminar. Parâmetros mudados com SetFloatParameter/SetTriggerParameter. MetaSound Patches são subgrafos reutilizáveis. Preferível aos Sound Cues em projetos novos.

## Áudio: atenuação e espacialização
Sound Attenuation: Attenuation Shape (esfera, cápsula, caixa, cone), Inner Radius e Falloff Distance, curva de queda, Spatialization (panning ou HRTF/binaural para fones), oclusão (traces que abafam sons atrás de paredes), Attenuation Focus, Reverb Send por distância, filtro de ar (passa-baixa com a distância). Configure por tipo de som e reaproveite assets de atenuação.

## Áudio: mixagem e opções de volume
Organize sons em Sound Classes (Master > Musica, Efeitos, Voz, UI). Volume nas opções: Sound Class Mix com ajuste por classe (UGameplayStatics::SetSoundMixClassOverride + PushSoundMixModifier) ou Audio Modulation (plugin, Control Buses com Control Bus Mix: abordagem moderna). Submixes aplicam efeitos (reverb, compressão) e medem níveis (envelope following para visualizadores).

## Áudio: música e transições
Dois Audio Components para crossfade (FadeIn/FadeOut) ou um MetaSound com estados. Para música adaptativa (camadas por intensidade de combate), controle parâmetros do MetaSound pelo jogo. Quartz (subsistema de relógio musical) agenda eventos sincronizados com o compasso. Middleware externo (Wwise, FMOD) é comum em produções grandes e tem plugins oficiais.

## Niagara: estrutura
Niagara System contém Emitters. Cada emitter tem grupos de módulos: Emitter Spawn/Update (estado do emitter), Particle Spawn (inicialização: posição, velocidade, cor, tamanho, tempo de vida), Particle Update (cada frame: gravidade, arrasto, curvas ao longo da vida, colisão), Event Handlers, e Renderers (Sprite, Mesh, Ribbon, Light, Component). Spawn Rate (contínuo) ou Spawn Burst Instantaneous (explosão). Sim Target CPU ou GPUCompute Sim (milhares de partículas, sem eventos de CPU).

## Niagara: tocar efeitos em C++
```cpp
#include "NiagaraFunctionLibrary.h"
#include "NiagaraComponent.h"

UNiagaraFunctionLibrary::SpawnSystemAtLocation(this, ImpactFX, Hit.ImpactPoint, Hit.ImpactNormal.Rotation());
UNiagaraComponent* Trail = UNiagaraFunctionLibrary::SpawnSystemAttached(TrailFX, Mesh, TEXT("Muzzle"),
    FVector::ZeroVector, FRotator::ZeroRotator, EAttachLocation::SnapToTarget, true);
Trail->SetVariableLinearColor(TEXT("User.Color"), FLinearColor::Red);
Trail->SetVariableFloat(TEXT("User.Intensity"), 2.f);
```
Módulos Niagara e NiagaraCore no Build.cs (Niagara basta na maioria dos casos). Parâmetros de usuário se chamam User.Nome. Sistemas com bAutoDestroy se destroem sozinhos ao terminar.

## Niagara: colisão e dados do mundo
Módulo Collision em Particle Update: CPU Scene Trace (preciso, caro), GPU Depth Buffer (barato, só o que está na tela) ou GPU Distance Fields (exige Mesh Distance Fields). Data Interfaces leem dados do jogo: Skeletal Mesh (partículas na superfície do personagem), Static Mesh, Curl Noise, Spline, Audio Spectrum, Collision Query, arrays definidos pelo jogo. Simulation Stages permitem simulações em grade (fluidos 2D/3D com Niagara Fluids).

## Niagara: desempenho
Use Scalability no sistema (Effect Type com orçamento, culling por distância e por visibilidade, contagem máxima por qualidade), Fixed Bounds para evitar cálculos de limites, prefira GPU para muitas partículas, limite overdraw de sprites translúcidos grandes, use LODs de emitter e pooling (Pooling Method ao spawnar). Ferramentas: Niagara Debugger (Window > Niagara Debugger) e stat Niagara.

## Decals
UDecalComponent / ADecalActor projeta um material (Material Domain = Deferred Decal) em superfícies: marcas de tiro, sangue, sujeira. UGameplayStatics::SpawnDecalAtLocation(this, Mat, Size, Local, Rotacao, LifeSpan). Decals têm custo de pixel: limite quantidade e use Fade Screen Size e LifeSpan.

## Sequencer e cinemáticas
Level Sequence: trilhas de atores (Transform, Animation, propriedades), Cine Camera Actor com Camera Cuts, eventos (Event Track chamando Blueprint), áudio, fades. Toque com ULevelSequencePlayer::CreateLevelSequencePlayer(World, Sequence, Settings, OutActor) e Play(), ou Level Sequence Actor com Auto Play. Template de cutscene com o personagem do jogador: Possessable binding ou Binding Override. Render offline: Movie Render Queue (anti-aliasing por amostras temporais e espaciais, EXR/PNG/ProRes, warm-up frames) ou Movie Render Graph em versões recentes.
