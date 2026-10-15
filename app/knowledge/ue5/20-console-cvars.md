# 20 Comandos de console e CVars (UE5)

## Console: como usar
Abra com a tecla crase (`) no editor e no jogo (Development). Tab autocompleta. Comandos podem ir na linha de comando com -ExecCmds="stat fps, r.ScreenPercentage 75", em Blueprints com Execute Console Command, em C++ com GEngine->Exec(World, TEXT("...")) ou IConsoleManager, e permanentemente no DefaultEngine.ini na seção [SystemSettings] (CVars) ou em Device Profiles por plataforma. Em Shipping o console fica desativado por padrão.

## Console: estatísticas
stat fps (quadros por segundo), stat unit (Frame, Game, Draw, GPU), stat unitgraph (gráfico), stat gpu, stat scenerendering, stat game, stat memory, stat streaming, stat anim, stat physics, stat net, stat Niagara, stat ai, stat hitches, stat none (desliga todos). stat startfile / stat stopfile gravam um arquivo de estatísticas (prefira Unreal Insights).

## Console: visualização e mostrar/esconder
show collision, show bounds, show navigation, show particles, show postprocessing, show fog, show staticmeshes, show skeletalmeshes; viewmode lit, unlit, wireframe, lightingonly, shadercomplexity; r.VisualizeOccludedPrimitives 1; freezerendering (congela o culling para inspecionar o que está sendo desenhado). ToggleDebugCamera: câmera livre durante o jogo.

## Console: jogo e trapaças de teste
slomo 0.5 (câmera lenta), pause, god, fly, ghost (atravessa paredes), walk (volta ao normal), teleport (vai até onde aponta), summon NomeDaClasse, open NomeDoMapa, open 127.0.0.1 (conectar a servidor), disconnect, reconnect, exit, killall NomeDaClasse, DisplayAll NomeDaClasse NomeDaPropriedade, HighResShot 2 (captura em alta resolução em Saved/Screenshots). Alguns exigem o Cheat Manager ativo (PIE ou builds não-Shipping).

## CVars: renderização e resolução
r.ScreenPercentage 75 (resolução interna), r.AntiAliasingMethod (0 nenhum, 1 FXAA, 2 TAA, 3 MSAA, 4 TSR), t.MaxFPS 60 (limite de FPS), r.VSync 0/1, r.SetRes 1920x1080f (f tela cheia, w janela), sg.ResolutionQuality, r.DynamicGlobalIlluminationMethod (0 nenhum, 1 Lumen), r.ReflectionMethod (0 nenhum, 1 Lumen, 2 SSR), r.Shadow.Virtual.Enable 0/1, r.Nanite 0/1 (desligar para comparar), r.Tonemapper.Sharpen.

## CVars: grupos de escalabilidade
sg.ViewDistanceQuality, sg.AntiAliasingQuality, sg.ShadowQuality, sg.GlobalIlluminationQuality, sg.ReflectionQuality, sg.PostProcessQuality, sg.TextureQuality, sg.EffectsQuality, sg.FoliageQuality, sg.ShadingQuality (0 Low a 4 Cinematic). scalability 0-4 define todos de uma vez. Valores de cada nível ficam no DefaultScalability.ini.

## CVars: Lumen
r.Lumen.DiffuseIndirect.Allow, r.Lumen.Reflections.Allow, r.Lumen.HardwareRayTracing 0/1, r.Lumen.TraceMeshSDFs, r.Lumen.ScreenProbeGather.DownsampleFactor (qualidade x desempenho), r.Lumen.Reflections.MaxRoughnessToTrace. Os nomes e efeitos exatos podem variar entre versões 5.x; liste com o autocomplete digitando r.Lumen.

## CVars: streaming e memória
r.Streaming.PoolSize (MB para streaming de texturas), r.Streaming.FullyLoadUsedTextures, r.Streaming.Boost, memreport -full (relatório de memória em Saved/Profiling), obj list class=Classe, obj gc (força coleta de lixo), gc.TimeBetweenPurgingPendingKillObjects, rhi.DumpMemory.

## CVars: rede
net.PktLag=150 (latência simulada em ms), net.PktLagVariance, net.PktLoss=5 (perda em %), net.PktDup, net.PktOrder, NetEmulation.PktLag (variação em algumas versões), stat net, net.ListActorChannels, p.NetShowCorrections 1 (mostra correções de movimento do CMC), log LogNet Verbose, net.MaxRepArraySize.

## CVars: física, animação e IA
p.Chaos.DebugDraw.Enabled, p.Chaos.Solver.IterationCount, p.EnableAsyncScene; a.URO.Enable (Update Rate Optimization), a.VisualizeLODs, a.Budget.Enabled; ai.DebugDrawEnabled, ShowFlag.Navigation, gdt.Toggle (Gameplay Debugger), AbilitySystem.Debug.NextCategory.

## Profiling por comando
trace.start default / trace.stop (Unreal Insights), trace.bookmark Nome, ProfileGPU (captura de um frame da GPU), stat startfile, csvprofile start/stop (CSVs para análise automatizada), DumpTicks (lista tudo que faz tick), r.ShaderPipelineCache.Open/Save (PSO cache), r.PSOPrecaching 1.

## Criar sua própria CVar em C++
```cpp
static TAutoConsoleVariable<float> CVarEnemySpeedScale(
    TEXT("mygame.EnemySpeedScale"), 1.0f,
    TEXT("Multiplica a velocidade dos inimigos."), ECVF_Cheat);

float Scale = CVarEnemySpeedScale.GetValueOnGameThread();
```
Para comandos: FAutoConsoleCommand com um delegate, ou funções UFUNCTION(Exec) no PlayerController/CheatManager. Use o prefixo do projeto nas CVars e ECVF_Cheat para as que não devem existir em Shipping.
