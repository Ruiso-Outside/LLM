# 13 Mundo: World Partition, streaming, terreno e PCG (UE5)

## World Partition: conceito
Divide o mapa numa grade de células carregadas e descarregadas automaticamente pela distância das fontes de streaming (o jogador). Substitui World Composition e subníveis manuais em mundos grandes. Cada ator é salvo em arquivo próprio (One File Per Actor, OFPA). O template Open World já vem com World Partition. Para converter um mapa antigo: Tools > Convert Level (faça backup).

## World Partition: editor e configurações
Window > World Partition > World Partition Editor mostra o mapa de cima; selecione áreas e Load Region From Selection para editar só aquela parte. World Settings > World Partition Setup: Runtime Grids (Cell Size, Loading Range, prioridade); atores podem ir para grades diferentes (ex.: uma grade de longo alcance para marcos visuais). Atores com Is Spatially Loaded desligado ficam sempre carregados (gerenciadores, lógica global). Fontes de streaming adicionais: UWorldPartitionStreamingSourceComponent (útil para câmeras de cutscene ou teleportes que precisam pré-carregar uma área).

## World Partition: Data Layers
Camadas de conteúdo ligáveis no editor e em tempo de execução (dia/noite, antes/depois de um evento, missões). Crie Data Layer Assets, adicione-os ao mapa (Data Layers Outliner) e atribua atores. Em execução: UDataLayerManager / nó Set Data Layer Runtime State com estados Unloaded, Loaded e Activated (só no servidor em multiplayer; replica para os clientes).

## Level Instances e Packed Level Actors
Level Instance: um nível pequeno reutilizado como objeto (uma casa montada com várias peças); editar o original atualiza todas as cópias. Packed Level Actor: versão otimizada que converte as malhas repetidas em instâncias (ISM/HISM), reduzindo draw calls, sem lógica. Criação: selecione atores > botão direito > Level > Create Level Instance / Create Packed Level Actor.

## HLOD com World Partition
HLOD substitui grupos de objetos distantes por malhas combinadas e simplificadas, usadas quando as células estão descarregadas. HLOD Layers (Instancing, Merged Mesh, Simplified Mesh, Approximated Mesh) atribuídas por padrão em World Settings ou por ator. Gere em Build > Build HLODs (ou commandlet WorldPartitionBuilderCommandlet com o builder de HLOD). Regere após mudanças grandes de cenário.

## Level Streaming tradicional
Para mapas sem World Partition: subníveis em Window > Levels, carregados com Level Streaming Volumes ou por código (UGameplayStatics::LoadStreamLevel / UnloadStreamLevel, ou ULevelStreamingDynamic::LoadLevelInstance para instanciar um nível em tempo de execução, útil em masmorras procedurais).

## Coordenadas grandes (Large World Coordinates)
A UE5 usa double em posições (FVector com double), permitindo mundos enormes sem tremedeira de precisão perto da origem distante. Ainda assim, cuidado com materiais e shaders que usam posições absolutas (use os nós LWC adequados) e com física muito longe da origem. World Origin Rebasing não é mais necessário na maioria dos casos.

## Landscape: criar e esculpir
Modo Landscape (Shift+2): Manage > New, Create New ou Import from File (heightmap PNG/RAW de 16 bits), com Section Size, Sections Per Component e Number of Components (use os tamanhos sugeridos). Sculpt: Sculpt (Shift inverte), Smooth, Flatten, Ramp, Erosion, Hydro Erosion, Noise, Retopologize. Edit Layers permitem esculpir em camadas não destrutivas e são necessárias para splines e água escavarem o terreno. Escala: 1 unidade = 1 cm; a escala Z do landscape define a altura máxima.

## Landscape: material e pintura de camadas
Material com Landscape Layer Blend (camadas Weight Blend: Grama, Terra, Pedra), uma cópia do blend para cada canal (cor, normal, rugosidade). No modo Paint, crie Layer Info para cada camada e pinte. Landscape Grass Type gera grama automaticamente onde a camada é pintada (com cull distance). Limite camadas por componente (3 a 4) para desempenho. Runtime Virtual Texture ajuda a mesclar objetos com o terreno e a reduzir o custo do material.

## Foliage
Modo Foliage (Shift+3): arraste malhas para criar Foliage Types com Density, Scale, Align to Normal, Random Yaw, Ground Slope Angle, Cull Distance e colisão. Usa HISM (instâncias), então milhares de cópias são baratas. Para áreas enormes, Procedural Foliage Spawner ou PCG. Folhagem com Nanite está disponível em versões recentes (Nanite Foliage), reduzindo a necessidade de LODs.

## PCG (Procedural Content Generation)
Plugin Procedural Content Generation Framework: grafos de nós que geram conteúdo por regras. Fluxo típico: Get Landscape Data → Surface Sampler (pontos) → filtros (Density Filter, por inclinação, altura, distância de splines) → Transform Points (variação) → Static Mesh Spawner. Coloque um PCG Volume com o grafo, ou um PCG Component num Blueprint, e clique Generate. Diferença de dados (Difference) exclui áreas (estradas, construções). Suporta geração em tempo de execução (Runtime Generation, com grade hierárquica), partição por World Partition, atributos por ponto e subgrafos reutilizáveis. Bom para florestas, pedras, cercas ao longo de splines e vilas.

## Água
Plugin Water: Water Body Ocean, Lake, River (por spline, com largura, profundidade e velocidade por ponto), Water Body Custom, Water Zone (malha de renderização). Com Edit Layers, escava o landscape automaticamente. Flutuação de objetos: UBuoyancyComponent com pontões. Personagem nadando: o CMC entra em Swimming dentro de volumes de água (Physics Volume com Water Volume, ou a integração do plugin).

## Ciclo de dia e noite
Directional Light com Atmosphere Sun Light ligado + Sky Atmosphere + Sky Light com Real Time Capture. Gire a Directional Light no eixo Pitch ao longo do tempo (Tick, Timeline ou um subsistema de tempo) e ajuste a intensidade e a cor por curvas. Lua: segunda Directional Light com Atmosphere Sun Light Index = 1. Estrelas num material de céu que aparece à noite. Com Lumen, a iluminação indireta acompanha automaticamente.

## Neblina e nuvens
Exponential Height Fog (densidade, falloff pela altura, Start Distance, Volumetric Fog para luz volumétrica com Volumetric Scattering Intensity nas luzes) e Volumetric Cloud (camada de nuvens com material próprio, afetada pelo sol). Volumetric Fog e nuvens custam GPU: ajuste View Distance e qualidade por escalabilidade.

## Ferramentas de modelagem e blockout
Modo Modeling (plugin Modeling Tools Editor Mode, Shift+5): criação de formas, PolyEdit, Boolean, Remesh, Simplify, UV, Pivot, Bake Transform, Cube Grid para blockout rápido de níveis. Geometry Script permite modelagem procedural em Blueprint/C++ (UDynamicMesh). Resultado vira Static Mesh. Para arte final, programas externos (Blender, Maya) continuam o padrão.
