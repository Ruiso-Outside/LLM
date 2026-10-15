# 22 Arquitetura e boas práticas (UE5)

## Padrão de código da Epic (coding standard)
Classes e structs com prefixos (A, U, F, E, I, T, S); PascalCase para tipos, funções e variáveis; booleanos com prefixo b (bIsDead); parâmetros de saída com Out (OutHits); enums com enum class e uint8 quando expostos; use os tipos da engine (int32, FString, TArray) em vez dos da biblioteca padrão; const correto; nullptr; auto só quando o tipo é óbvio; chaves em linha própria; TEXT() em literais; comentários de API com Doxygen (/** */). Ordem no header: public antes de protected e private. Headers mínimos: forward declarations e includes nos .cpp.

## Organização: C++ base + Blueprint de conteúdo
Defina comportamento e dados em C++ (classes base abstratas ou configuráveis) e crie filhos Blueprint que só configuram assets e efeitos. Exemplo: AWeaponBase (C++) com disparo, munição e replicação; BP_Rifle e BP_Shotgun configuram malha, sons, taxa e dano (ou leem de Data Assets). Evite Blueprints com lógica pesada chamando C++ e C++ dependendo de classes Blueprint (dependência invertida e frágil): C++ nunca deve conhecer tipos Blueprint; use classes base, interfaces e TSubclassOf configurados no editor.

## Organização: componentes em vez de herança profunda
Prefira composição: UHealthComponent, UInventoryComponent, UInteractionComponent reutilizáveis em vários atores, em vez de hierarquias profundas (APersonagem > AInimigo > AInimigoVoador > ...). Comunicação entre componentes por delegates e interfaces. Para funcionalidades adicionadas dinamicamente, Game Features e o Modular Gameplay (componentes adicionados por plugins).

## Organização: dados separados da lógica
Valores de balanceamento em Data Assets, DataTables e Curve Tables, não espalhados em Blueprints. Identifique itens por FPrimaryAssetId ou FGameplayTag, não por strings. Configurações globais em UDeveloperSettings. Isso permite designers ajustarem sem programadores e facilita salvar, carregar e replicar ids em vez de objetos.

## Organização: subsistemas em vez de singletons
Gerenciadores globais (inventário do jogador, missões, áudio, save, conquistas) como UGameInstanceSubsystem ou UWorldSubsystem, com vida controlada pela engine e acesso tipado. Evite atores "Manager" colocados manualmente em cada mapa e variáveis estáticas globais (quebram no PIE com vários mundos e em testes).

## Organização: Gameplay Tags
Use Gameplay Tags para estados, categorias e mensagens (State.Dead, Item.Weapon.Rifle, Event.Interact). São hierárquicas, rápidas, editáveis e evitam dezenas de booleanos e enums que crescem. O Gameplay Message Subsystem (do Lyra) permite mensagens desacopladas por tag (um sistema publica, outros escutam) sem referências diretas.

## Projeto de referência: Lyra
O Lyra Starter Game (gratuito, da Epic) demonstra a arquitetura moderna: Game Features para modos de jogo, GAS para habilidades, Enhanced Input com Input Tags, CommonUI, Modular Gameplay com componentes, Experience Definitions (Data Assets que descrevem um modo de jogo), Gameplay Message Subsystem, CommonUser para login/sessões, e organização por plugins. É complexo para iniciantes, mas ótimo para estudar padrões e copiar sistemas.

## Multiplayer desde o início
Se o jogo terá multiplayer, projete-o desde o começo: autoridade do servidor, dados no lugar certo (GameState, PlayerState), RPCs mínimos e validados, replicação por estado (RepNotify) em vez de eventos, e teste com PIE como cliente desde as primeiras semanas. Converter um jogo single-player para multiplayer depois costuma exigir reescrever grande parte do gameplay.

## Testes automatizados
Automation Test Framework: testes C++ com IMPLEMENT_SIMPLE_AUTOMATION_TEST (unidade), testes latentes, Functional Tests (atores AFunctionalTest colocados em mapas de teste) e o framework Automation Spec (BDD: Describe/It). Rode pelo Session Frontend (Tools > Session Frontend > Automation) ou por linha de comando (-ExecCmds="Automation RunTests MyGame" -unattended -nullrhi). Gauntlet automatiza sessões completas (cliente e servidor) em CI. Teste sistemas puros (cálculo de dano, inventário) com testes unitários e fluxos com testes funcionais.

## Controle de versão e fluxo de equipe
Perforce para equipes com muitos artistas (travas de arquivos binários) ou Git com LFS e locks (git lfs lock) em equipes pequenas. Commits pequenos e frequentes; nunca versione Binaries, Intermediate, Saved, DerivedDataCache. One File Per Actor e Level Instances reduzem conflitos em mapas. Combine quem edita Blueprints e mapas compartilhados. Um servidor de build (CI) que compila, cozinha e roda testes a cada mudança evita surpresas no fim do projeto.

## Desempenho desde o início
Defina orçamentos (FPS alvo, memória, tamanho do pacote) no começo e meça com frequência em builds empacotadas no hardware mínimo. Evite Tick por padrão, use soft references para conteúdo grande, prefira eventos a polling, e use Insights antes de otimizar (meça, não adivinhe).

## Segurança e confiabilidade
Nunca confie no cliente (valide RPCs no servidor); não coloque segredos no cliente; criptografe e assine os paks; trate falhas de rede e de backend (timeouts, retries, mensagens ao jogador); salve com versões e de forma assíncrona; tenha backups e controle de versão; registre logs úteis com categorias próprias e níveis adequados.

## Checklist de um sistema novo
1) Onde ficam os dados (componente, PlayerState, subsistema, Data Asset)? 2) Quem tem autoridade e o que replica? 3) Como Blueprint e designers configuram? 4) Como é salvo e carregado? 5) Como a UI é notificada (delegates, MVVM)? 6) Custo por frame e memória (Tick, referências hard)? 7) Como testar (teste automatizado, PIE como cliente)? 8) Como depurar (logs, Gameplay Debugger, comandos de console)?
