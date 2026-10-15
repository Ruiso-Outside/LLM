# 17 Desempenho e profiling (UE5)

## Desempenho: descobrir o gargalo
Comandos: stat fps, stat unit (tempos de Frame, Game = CPU da lógica, Draw = CPU da renderização, GPU, RHIT; o maior é o gargalo), stat unitgraph, stat gpu (custo por etapa de GPU), stat scenerendering (draw calls, primitivas), stat game (Tick, física, IA), stat memory. Regra: Game alto → lógica, Tick, IA, física, Blueprints; Draw alto → muitos objetos/draw calls; GPU alto → resolução, iluminação, sombras, pós-processamento, partículas, overdraw.

## Unreal Insights
Ferramenta principal de profiling (Tools > Unreal Insights, ou UnrealInsights.exe em Engine/Binaries). Rode o jogo com -trace=default (ou cpu,gpu,frame,bookmark,loadtime,memory,net) ou use o comando trace.start / trace.stop. Mostra a linha do tempo de cada thread por frame, com eventos nomeados. Adicione escopos próprios em C++: TRACE_CPUPROFILER_EVENT_SCOPE(MyFunction) ou SCOPED_NAMED_EVENT. Também: Memory Insights, Networking Insights, Asset Loading Insights. Faça profiling em builds Development ou Test empacotadas, não no editor (o editor distorce os números).

## GPU: diagnóstico
ProfileGPU (Ctrl+Shift+,) captura um frame com o custo de cada passo. Viewmodes de otimização: Shader Complexity, Quad Overdraw, Light Complexity, Lightmap Density, Nanite e Lumen visualizations. Ferramentas externas: RenderDoc (plugin), NVIDIA Nsight, PIX. Reduza Screen Percentage com TSR/DLSS/FSR, qualidade de Lumen e sombras, número de luzes com sombra, translucidez e partículas grandes, e materiais caros.

## CPU: lógica de jogo
Desligue Tick desnecessário (bCanEverTick false; TickInterval; ligar só quando preciso), troque polling por eventos e timers, evite GetAllActorsOfClass e buscas frequentes (guarde referências, use subsistemas que registram atores), mova laços pesados de Blueprint para C++, use Significance Manager para atualizar menos o que está longe, reduza traces e queries por frame (ou use assíncronos), e cuidado com animação (URO, Visibility Based Anim Tick) e com o Character Movement de muitos NPCs (use NavWalking e movimento simplificado longe da câmera).

## Draw calls e instancing
Cada malha com material diferente custa draw calls. Use Instanced Static Mesh (ISM) e Hierarchical ISM (HISM) para objetos repetidos (folhagem, pedras, cercas); Packed Level Actors convertem conjuntos em instâncias; Nanite reduz drasticamente o custo de geometria e de draw calls de malhas compatíveis; Merge Actors combina malhas estáticas; menos materiais únicos e mais Material Instances do mesmo mestre.

## LOD e culling
LODs automáticos para malhas não-Nanite (Static Mesh Editor > LOD Settings, Auto Compute LOD Distances), Max Draw Distance por componente, Cull Distance Volume (por tamanho do objeto), Precomputed Visibility (mapas pequenos e fechados), occlusion culling automático por hardware, HLOD para grupos distantes. Skeletal Meshes: LODs com menos ossos e redução de qualidade de animação com a distância.

## Memória
Comandos: stat memory, memreport -full, obj list, rhi.DumpMemory. Texturas costumam dominar: limite tamanhos (LOD Groups, Maximum Texture Size, Never Stream só quando necessário), use streaming (r.Streaming.PoolSize), Virtual Textures. Áudio: compressão e streaming de sons longos. Referências hard em cadeia carregam conteúdo desnecessário: Size Map e soft references. Vazamentos: objetos presos por referências esquecidas (delegates, arrays UPROPERTY que crescem, timers).

## Carregamento e hitches
Hitches (travadas de alguns frames) vêm de carregamento síncrono (LoadSynchronous, ConstructorHelpers em runtime), compilação de shaders (PSO), spawn de muitos atores no mesmo frame, garbage collection pesada, e streaming de níveis. Soluções: carregamento assíncrono, PSO precaching, espalhar spawns entre frames, pools de atores, ajustar o GC (gc.TimeBetweenPurgingPendingKillObjects, incremental GC em versões recentes), telas de loading durante transições, World Partition com Loading Range adequado. stat hitches e Insights mostram os picos.

## Garbage collection
Muitos UObjects criados e destruídos aumentam o custo do GC. Reaproveite objetos (pools), use structs (USTRUCT) em vez de UObjects para dados simples, evite criar UObjects temporários por frame. Cluster de GC para assets carregados juntos reduz o custo de marcação. O GC roda em intervalos (gc.TimeBetweenPurgingPendingKillObjects, padrão 61 s) e na troca de mapa.

## Rede: desempenho do servidor
Reduza NetUpdateFrequency de atores que mudam pouco, use dormência (NetDormancy) e relevância (NetCullDistanceSquared), condições de replicação (COND_OwnerOnly), quantização (FVector_NetQuantize), Fast Array Serializer para listas, e evite RPCs Reliable frequentes. Para muitos jogadores: Replication Graph ou Iris. Meça com stat net e Networking Insights.

## Plataformas e alvos de desempenho
Defina orçamentos por frame (16,6 ms para 60 FPS, 33,3 ms para 30 FPS) divididos entre game thread, render thread e GPU. Teste no hardware mínimo. Use os níveis de Scalability e Device Profiles (DefaultDeviceProfiles.ini) para ajustar CVars por plataforma ou por classe de hardware. Desative recursos caros (Lumen, Nanite, VSM) em perfis de baixo desempenho e ofereça alternativas (iluminação mais simples, sombras tradicionais).

## Medir sempre em build empacotada
O editor tem custo extra (ferramentas, objetos de editor, sem otimizações de cook). Meça em builds Development ou Test empacotadas (Test tem otimizações de Shipping mantendo algumas ferramentas de profiling). Use -csvprofile (stat csvprofile start/stop) para gerar CSVs de desempenho e comparar versões automaticamente em CI.
