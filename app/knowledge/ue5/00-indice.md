# Base de conhecimento Unreal Engine 5 — índice

Referência em português para desenvolvimento de jogos na Unreal Engine 5 (UE5), com foco em C++, editor, multiplayer e produção. Cada seção é curta e autocontida para a busca encontrar o trecho certo. Os nomes de classes, menus e opções ficam em inglês, como aparecem na engine.

## Arquivos desta base
- 01 Editor e projeto: interface, atalhos, estrutura de pastas, configurações, controle de versão.
- 02 C++ e reflexão: UCLASS, UPROPERTY, UFUNCTION, USTRUCT, UENUM, especificadores, tipos, coleta de lixo, ponteiros.
- 03 Gameplay Framework: GameMode, GameState, PlayerController, PlayerState, Pawn, Character, HUD, GameInstance.
- 04 Atores e componentes: ciclo de vida, spawn, timers, tick, delegates, interfaces, subsystems.
- 05 Enhanced Input: Input Actions, Mapping Contexts, modificadores, gatilhos, remapeamento.
- 06 Blueprints e C++: expor código, BlueprintNativeEvent, comunicação, boas práticas.
- 07 Rede e replicação: autoridade, RPCs, propriedades replicadas, relevância, previsão, servidores dedicados.
- 08 Gameplay Ability System (GAS): ASC, atributos, habilidades, efeitos, tags, cues.
- 09 Animação: Animation Blueprint, montages, notifies, IK, Control Rig, retargeting, Motion Matching.
- 10 Inteligência artificial: AIController, Behavior Tree, Blackboard, Perception, EQS, navegação, State Tree.
- 11 Interface: UMG, CommonUI, Slate, MVVM.
- 12 Renderização: Lumen, Nanite, sombras, materiais, pós-processamento, escalabilidade.
- 13 Mundo: World Partition, Data Layers, Level Instances, HLOD, PCG, terreno, água.
- 14 Física e colisão: canais, traces, Chaos, constraints, destruição, veículos.
- 15 Áudio e efeitos: MetaSounds, atenuação, Niagara.
- 16 Assets e dados: referências soft/hard, Asset Manager, Data Assets, DataTables, SaveGame, carregamento assíncrono.
- 17 Desempenho: stat, Unreal Insights, otimização de CPU, GPU e memória.
- 18 Build e empacotamento: UBT, módulos, Build.cs, plugins, cook, pak, plataformas.
- 19 Depuração e erros comuns: erros de compilação e link, crashes, logs, Live Coding.
- 20 Console e CVars: comandos e variáveis de console mais usados.
- 21 Online: Online Subsystem, EOS, sessões, servidores dedicados.
- 22 Arquitetura e boas práticas: padrão de código da Epic, organização, módulos, testes.

## Sobre versões
O conteúdo vale para a UE5 em geral (5.0 em diante). Alguns recursos mudaram entre versões: Motion Matching e o retargeting automático ficaram completos a partir da 5.4; State Tree e Mass amadureceram ao longo da série 5.x; Nanite para malhas esqueléticas e folhagem chegou em versões recentes. Quando uma resposta depender da versão, confira a versão do projeto (arquivo .uproject, campo EngineAssociation).
