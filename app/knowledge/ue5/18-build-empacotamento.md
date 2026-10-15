# 18 Build, módulos, plugins e empacotamento (UE5)

## Unreal Build Tool (UBT) e Automation Tool (UAT)
UBT compila o código C++ a partir dos arquivos .Build.cs (módulos) e .Target.cs (alvos). UAT (RunUAT.bat) automatiza cook, empacotamento e implantação (BuildCookRun). O Unreal Header Tool (UHT) gera o código de reflexão antes da compilação. Configurações de build: Debug, DebugGame (jogo sem otimizações, engine otimizada), Development (padrão, com ferramentas), Test (quase Shipping, com profiling), Shipping (final). Alvos: Game, Client, Server, Editor, Program.

## Módulos: Build.cs
```csharp
using UnrealBuildTool;

public class MyGame : ModuleRules
{
    public MyGame(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new string[] {
            "Core", "CoreUObject", "Engine", "InputCore", "EnhancedInput" });
        PrivateDependencyModuleNames.AddRange(new string[] {
            "UMG", "Slate", "SlateCore", "GameplayAbilities", "GameplayTags", "GameplayTasks",
            "AIModule", "NavigationSystem", "Niagara", "NetCore" });
    }
}
```
Public: módulos cujos headers aparecem nos seus headers públicos (quem depende de você também precisa). Private: usados só nos .cpp. Erros de link "unresolved external symbol" muitas vezes significam um módulo faltando aqui. Depois de mudar o Build.cs, regenere os arquivos do projeto.

## Módulos: estrutura e organização
Um módulo tem pasta própria em Source com NomeDoModulo.Build.cs, e normalmente as pastas Public (headers expostos) e Private (cpp e headers internos), mais um arquivo de módulo (IMPLEMENT_PRIMARY_GAME_MODULE para o principal; IMPLEMENT_MODULE para os outros). Liste módulos no .uproject (ou .uplugin) com Type (Runtime, Editor, UncookedOnly, Developer) e LoadingPhase (Default, PreDefault, PostConfigInit, PostEngineInit). Separe código de editor (ferramentas, detalhes customizados) num módulo Editor para não entrar no jogo. Divida o jogo em módulos para compilar mais rápido e forçar dependências limpas.

## Target.cs
```csharp
public class MyGameTarget : TargetRules
{
    public MyGameTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Game;
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        ExtraModuleNames.Add("MyGame");
    }
}
```
Existem MyGame.Target.cs (jogo), MyGameEditor.Target.cs (Type = Editor) e, para servidor dedicado, MyGameServer.Target.cs (Type = Server; exige a engine compilada do código-fonte). Para cliente sem servidor: Type = Client.

## Plugins
Pasta Plugins/NomeDoPlugin com NomeDoPlugin.uplugin (descrição, módulos, dependências de outros plugins, CanContainContent), Source e Content opcionais. Crie em Edit > Plugins > Add (modelos: Blank, Content Only, Blueprint Library, Editor Mode, Editor Standalone Window, Third Party Library). Habilite/desabilite no .uproject. Plugins de terceiros precisam ser compatíveis com a versão exata da engine (ou recompilados a partir do código). Para bibliotecas externas (.lib/.dll), crie um módulo External com PublicAdditionalLibraries, PublicIncludePaths e RuntimeDependencies para copiar DLLs no pacote.

## Live Coding e Hot Reload
Live Coding (Ctrl+Alt+F11 no editor; ativado por padrão) recompila e aplica mudanças em .cpp com o editor aberto. Limitações: mudanças em headers que alteram layout de classes (adicionar UPROPERTY, mudar herança, adicionar UFUNCTION, mudar construtores) podem não ser aplicadas corretamente ou corromper Blueprints abertos; nesses casos, feche o editor e compile pelo IDE. Hot Reload antigo foi substituído pelo Live Coding e não é recomendado.

## Cook e empacotamento
Cook converte os assets para o formato da plataforma (texturas comprimidas, shaders compilados) e remove dados de editor. Empacotamento junta binários e conteúdo cozido em arquivos .pak/.utoc/.ucas (IoStore). No editor: Platforms > Windows > Package Project (configuração Development ou Shipping em Platforms > Binary Configuration). Project Settings > Packaging: Build Configuration, Full Rebuild, For Distribution (Shipping final), Use Pak File, Use Io Store, List of maps to include, Additional Asset Directories to Cook, Directories to never cook, Create compressed cooked packages.

## Empacotar por linha de comando
```bat
"C:\Program Files\Epic Games\UE_5.x\Engine\Build\BatchFiles\RunUAT.bat" BuildCookRun ^
  -project="D:\Projetos\MyGame\MyGame.uproject" -noP4 -platform=Win64 ^
  -clientconfig=Shipping -build -cook -stage -pak -iostore -archive ^
  -archivedirectory="D:\Builds\MyGame"
```
Para servidor dedicado: -server -serverconfig=Development -noclient (com a engine compilada do código-fonte). O Project Launcher (Tools > Project Launcher) cria perfis visuais de build. Automatize em CI (Jenkins, GitHub Actions self-hosted, TeamCity, Horde) com essa linha.

## Assets faltando no jogo empacotado
O cook só inclui o que os mapas incluídos referenciam (diretamente ou em cadeia) e o Asset Manager descobre. Assets carregados por caminho em string ficam de fora: use soft references, adicione o diretório em Additional Asset Directories to Cook, ou registre-os como Primary Assets. Confira também a lista de mapas, os plugins habilitados (Content de plugin precisa de CanContainContent) e funções Editor Only. Teste antes com Standalone Game e leia os logs do jogo empacotado em Saved/Logs dentro da pasta do pacote (build Development).

## Chunks, patches e DLC
O Asset Manager atribui assets a chunks (Primary Asset Labels com Chunk ID), gerando .pak separados para download sob demanda (ChunkDownloader) ou DLC. Patches: empacote com "Create a patch release" a partir de uma versão base (Release Version) para gerar paks só com as diferenças. Plataformas de distribuição (Steam, Epic) também fazem diferenças binárias; manter a ordem do pak estável reduz o tamanho das atualizações.

## Assinatura, criptografia e proteção
Project Settings > Crypto: chave para criptografar os .pak e assinar (Pak Signing) para dificultar extração e modificação. Não impede engenharia reversa determinada, mas protege contra ferramentas comuns. Nunca coloque segredos (chaves de API privadas) no cliente: coloque no servidor.

## Plataformas: Windows, Linux, consoles, mobile
Windows: SDK do Windows e Visual Studio. Linux: toolchain cross-compile da Epic para compilar do Windows (bom para servidores dedicados). Android: Android Studio, SDK/NDK/JDK nas versões indicadas para a versão da engine, Project Settings > Platforms > Android (package name, SDK license, arquiteturas arm64), APK ou AAB. iOS: exige Mac para compilação/assinatura (ou build remota). Consoles: SDKs e documentação sob NDA, obtidos com o fabricante e a Epic.

## Engine a partir do código-fonte
Necessária para servidores dedicados, modificações na engine e alguns consoles. Acesso: vincular a conta Epic ao GitHub e entrar na organização EpicGames; clonar o repositório UnrealEngine (branch release ou a tag da versão), rodar Setup.bat, GenerateProjectFiles.bat e compilar UnrealEditor (Development Editor, Win64). Associe o projeto à engine compilada (botão direito no .uproject > Switch Unreal Engine version). Use um DDC compartilhado e, para equipes, distribua binários da engine (Installed Build com BuildGraph) em vez de cada um compilar.
