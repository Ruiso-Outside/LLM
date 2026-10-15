# 01 Editor e projeto (UE5)

## Editor: janelas principais
Viewport (vista 3D do nível), Outliner (lista de atores do nível em hierarquia), Details (propriedades do selecionado), Content Browser e Content Drawer (assets do projeto; o Drawer abre com Ctrl+Espaço), barra de ferramentas (salvar, modos, adicionar atores, Play, plataformas), World Settings (GameMode do nível, World Partition, gravidade). Janelas fechadas voltam pelo menu Window; o layout padrão volta em Window > Load Layout > Default Editor Layout.

## Editor: navegação na viewport
Botão direito segurado + WASD anda (Q/E descem e sobem); a roda do mouse com o botão direito muda a velocidade. Botão do meio desloca. Alt + botão esquerdo orbita em volta do foco; Alt + botão direito dá zoom. F foca no ator selecionado. G alterna o modo jogo (esconde ícones). H esconde o selecionado e Ctrl+H mostra tudo.

## Editor: atalhos essenciais
W/E/R mover, girar e escalar; Espaço alterna; End encosta no chão; Alt + arrastar duplica; Ctrl+D duplica no lugar; segurar V encaixa em vértices. Alt+P joga no editor (PIE), Alt+S simula, F8 solta a câmera durante o jogo, Shift+F1 libera o mouse, Esc para. Ctrl+S salva o nível, Ctrl+Shift+S salva tudo. A tecla crase (`) abre o console. Ctrl+L + mover o mouse gira o sol (Directional Light) na viewport.

## Projeto: estrutura de pastas
- Config: arquivos DefaultEngine.ini, DefaultGame.ini, DefaultInput.ini, DefaultEditor.ini (configurações do projeto, versionadas).
- Content: assets (.uasset, .umap). Nunca mova ou renomeie pelo Explorer do Windows; use o Content Browser para atualizar referências e depois Fix Up Redirectors na pasta.
- Source: código C++ (um módulo por pasta, com .Build.cs) e os arquivos .Target.cs.
- Plugins: plugins do projeto.
- Binaries, Intermediate, DerivedDataCache, Saved: gerados; podem ser apagados (com o editor fechado) e não vão para o controle de versão. Saved guarda logs, autosaves (Saved/Autosaves), crashes e SaveGames do editor.
- Arquivo .uproject: JSON com a versão da engine (EngineAssociation), módulos e plugins habilitados.

## Projeto: convenção de nomes de assets
Prefixos comuns: BP_ (Blueprint), WBP_ (Widget Blueprint), ABP_ (Animation Blueprint), M_ (Material), MI_ (Material Instance), MF_ (Material Function), T_ (Texture), SM_ (Static Mesh), SK_ (Skeletal Mesh), SKEL_ (Skeleton), PHYS_ (Physics Asset), A_ ou AS_ (Animation Sequence), AM_ (Anim Montage), BS_ (Blend Space), NS_ (Niagara System), MS_ (MetaSound), DT_ (DataTable), DA_ (Data Asset), E_ (Enum), S_ ou F_ (Struct), IA_ (Input Action), IMC_ (Input Mapping Context), GA_ (Gameplay Ability), GE_ (Gameplay Effect), BT_ (Behavior Tree), BB_ (Blackboard). Organize o conteúdo do jogo em Content/NomeDoJogo, separado de pacotes externos.

## Projeto: Project Settings x Editor Preferences
Project Settings (Edit > Project Settings) são do projeto e salvos em Config/Default*.ini: mapas e modos (mapa inicial, GameMode padrão, GameInstance), renderização, colisão, input, física, empacotamento, plataformas. Editor Preferences (Edit > Editor Preferences) são pessoais: idioma, atalhos, autosave, desempenho do editor, onde o Play abre.

## Projeto: mapas iniciais e GameMode padrão
Project Settings > Maps & Modes: Editor Startup Map (abre no editor), Game Default Map (abre no jogo), Default GameMode, Game Instance Class. Um mapa pode sobrescrever o GameMode em World Settings > GameMode Override. Mapas são abertos no jogo com UGameplayStatics::OpenLevel ou o comando de console open NomeDoMapa.

## Projeto: controle de versão
Perforce (Helix Core) é o padrão em estúdios: lida com binários grandes e permite travar arquivos (exclusive checkout) para que dois artistas não editem o mesmo .uasset. Git funciona para equipes pequenas com Git LFS para .uasset, .umap, texturas e áudio, e com o .gitignore ignorando Binaries, DerivedDataCache, Intermediate, Saved, .vs e os arquivos de solução gerados. Ative One File Per Actor (padrão com World Partition) para que cada ator de um nível seja um arquivo próprio e haja menos conflitos. O editor integra com o provedor em Revision Control (canto inferior direito).

## Projeto: gerar arquivos do Visual Studio
Clique com o botão direito no .uproject > Generate Visual Studio project files (ou, no editor, Tools > Refresh Visual Studio Project). Necessário depois de adicionar ou remover arquivos C++ fora do editor. O Visual Studio precisa da carga de trabalho "Desenvolvimento para jogos com C++" com os componentes da Unreal; o Rider também é muito usado e lê o .uproject diretamente.

## Projeto: adicionar C++ a um projeto Blueprint
Tools > New C++ Class cria a primeira classe, a pasta Source, o módulo principal e os arquivos Target. A partir daí o projeto precisa ser compilado no Visual Studio/Rider ou pelo editor (Live Coding). Projetos com C++ abrem o editor a partir do IDE (configuração Development Editor) ou pelo .uproject depois de compilados.

## Projeto: atualizar a versão da engine
Faça backup ou commit. No Epic Games Launcher, clique com o botão direito no projeto > Clone para a nova versão, ou abra com a versão nova e escolha abrir uma cópia. Projetos C++ precisam recompilar e corrigir APIs alteradas ou obsoletas (deprecated). Confira os plugins de terceiros (precisam suportar a versão), as notas de versão e os avisos do Output Log. Opcional: Resave All na pasta Content para salvar os assets no formato novo.

## Editor: Output Log e Message Log
Output Log (Window > Output Log) mostra todas as mensagens, com filtros por categoria e verbosidade. Message Log (Window > Message Log) organiza erros de compilação de Blueprints, Map Check, PIE e ferramentas, com links para os nós. Logs ficam em Saved/Logs/NomeDoProjeto.log; crashes em Saved/Crashes.

## Editor: Play In Editor (PIE) para multiplayer
No menu ao lado do Play: Number of Players e Net Mode (Play Standalone, Play As Listen Server, Play As Client). Em Advanced Settings: Network Emulation para simular latência e perda de pacotes, e Run Under One Process (desligue para testar processos separados). Teste sempre com pelo menos dois jogadores como Listen Server e como Client.

## Editor: ferramentas úteis do Content Browser
Reference Viewer (quem usa e o que é usado por um asset), Size Map (memória total puxada por um asset e suas dependências hard), Audit Assets, Fix Up Redirectors, Resave, filtros e coleções. Size Map é a primeira ferramenta para descobrir por que um Blueprint carrega metade do jogo na memória.
