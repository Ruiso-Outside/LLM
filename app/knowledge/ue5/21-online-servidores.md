# 21 Online: sessões, EOS e servidores dedicados (UE5)

## Online Subsystem: o que é
Camada que abstrai serviços online por plataforma: sessões (criar, procurar, entrar), amigos, identidade/login, conquistas, placares, armazenamento na nuvem e voz. Implementações: OnlineSubsystemNull (LAN e testes locais), OnlineSubsystemSteam, OnlineSubsystemEOS (Epic Online Services, multiplataforma), e as de consoles. Configure no DefaultEngine.ini em [OnlineSubsystem] DefaultPlatformService=EOS (ou Steam/Null). Módulos: OnlineSubsystem, OnlineSubsystemUtils. A UE5 também tem a Online Services (OSSv2), interface nova que convive com a antiga.

## Sessões: fluxo básico
Hospedar: IOnlineSessionPtr Sessions = Online::GetSessionInterface(GetWorld()); configure FOnlineSessionSettings (NumPublicConnections, bShouldAdvertise, bUsesPresence, bUseLobbiesIfAvailable, bAllowJoinInProgress, chaves de busca com Set(FName, Valor, EOnlineDataAdvertisementType::ViaOnlineService)) e chame CreateSession; no callback, ServerTravel para o mapa com ?listen. Procurar: FindSessions com FOnlineSessionSearch (filtros e MaxSearchResults). Entrar: JoinSession com o resultado escolhido; no callback, GetResolvedConnectString e ClientTravel. Encerrar: DestroySession. Use delegates (AddOnCreateSessionCompleteDelegate_Handle etc.) e guarde os handles para remover depois.

## Sessões: Blueprints e plugins prontos
Nós nativos: Create Session, Find Sessions, Join Session, Destroy Session (limitados). O plugin Advanced Sessions (comunidade) expõe muito mais (configurações extras, Steam, amigos). O CommonUser plugin (do Lyra) encapsula login e sessões de forma moderna com suporte a EOS e outras plataformas.

## Epic Online Services (EOS)
Serviços gratuitos e multiplataforma da Epic: contas (Epic Account e Connect com outras identidades: Steam, consoles, device ID), lobbies e sessões, matchmaking básico, P2P com NAT traversal e relay, voz, estatísticas, conquistas, placares, armazenamento de jogador e título, anti-cheat (Easy Anti-Cheat) e reporte de jogadores. Configure um produto no Developer Portal da Epic (Product ID, Sandbox ID, Deployment ID, Client ID/Secret) e preencha em Project Settings (plugin EOS / OnlineSubsystemEOS e EOS Shared). Use Device ID ou Developer Authentication Tool para testes locais sem conta.

## Steam
OnlineSubsystemSteam com o App ID (480, Spacewar, para testes) em DefaultEngine.ini: [OnlineSubsystemSteam] bEnabled=true, SteamDevAppId=480, e a NetDriver Steam (SteamNetDriver/SteamSockets) para conexões P2P via Steam. Exige o cliente Steam aberto e o jogo iniciado fora do PIE para testar (Standalone ou empacotado). Para lançar, use seu próprio App ID e o Steamworks SDK da versão suportada.

## Servidor dedicado: criar e rodar
Compile a engine do código-fonte, crie o Target Server (MyGameServer.Target.cs), compile Development Server e empacote o servidor (Project Launcher ou RunUAT com -server -noclient). Rode: MyGameServer.exe /Game/Mapas/Arena -log -port=7777. Linux é o comum em produção (compilação cruzada pelo Windows com o toolchain da Epic). O mapa padrão do servidor fica em Project Settings > Maps & Modes > Server Default Map. Abra a porta UDP (padrão 7777) no firewall.

## Servidor dedicado: código específico
Use IsRunningDedicatedServer() ou GetNetMode() == NM_DedicatedServer para pular UI, áudio, efeitos e câmeras. Use UE_SERVER (macro de compilação) para código que só deve existir no binário do servidor e WITH_SERVER_CODE para remover lógica de servidor do cliente. Servidores não carregam assets puramente visuais quando configurados para isso (texturas e partículas podem ser removidas no cook de servidor).

## Hospedagem e orquestração
Opções: máquinas próprias/VPS para poucos servidores; serviços de hospedagem de servidores de jogos e orquestração (Amazon GameLift, Hathora, Edgegap, Agones no Kubernetes, entre outros) para criar e destruir instâncias sob demanda por região, com matchmaking. Padrão: um backend (API própria com PostgreSQL + Redis) cuida de contas, inventário, matchmaking e alocação; o servidor dedicado roda a partida e reporta resultados ao backend por HTTP com autenticação de servidor.

## Backend próprio e HTTP
Módulo HTTP: FHttpModule::Get().CreateRequest(), SetURL, SetVerb("POST"), SetHeader("Content-Type", "application/json"), SetContentAsString(Json), OnProcessRequestComplete().BindUObject(...), ProcessRequest(). JSON: FJsonObject, FJsonSerializer, ou FJsonObjectConverter::UStructToJsonObjectString / JsonObjectStringToUStruct para converter USTRUCTs. WebSockets: módulo WebSockets (FWebSocketsModule::Get().CreateWebSocket(Url)). Nunca guarde segredos no cliente; o cliente usa tokens de sessão do jogador e o servidor dedicado usa credenciais próprias.

## Segurança e anti-cheat em multiplayer
O servidor é a autoridade: valide todas as ações vindas de RPCs (alcance, recarga, munição, posição plausível, taxa de ações). Nunca deixe o cliente decidir dano, compras ou recompensas. Ofusque o mínimo necessário e use soluções de anti-cheat (Easy Anti-Cheat via EOS, ou outras) para detecção no cliente. Proteja o backend com autenticação, rate limiting e idempotência nas operações econômicas.

## Voz e chat
EOS Voice (lobbies e salas de voz) ou Vivox; o Online Subsystem expõe a interface de voz. Chat de texto pode ir por RPCs no próprio jogo (moderação e filtros no servidor) ou por serviços externos. Respeite regras das plataformas sobre moderação e denúncias.

## Testar online localmente
OnlineSubsystemNull para LAN no PIE; múltiplas instâncias Standalone (-game) com contas de teste; EOS Dev Auth Tool para logar várias contas no mesmo PC; Network Emulation para latência; servidores dedicados locais com -log e clientes conectando com open 127.0.0.1:7777.
