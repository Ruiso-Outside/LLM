# 07 Rede e replicação (UE5)

## Rede: modelo cliente-servidor
A Unreal usa servidor autoritativo: o servidor decide o estado verdadeiro e replica para os clientes. Modos de rede (ENetMode): NM_Standalone (sem rede), NM_DedicatedServer (servidor sem jogador local), NM_ListenServer (servidor que também é jogador), NM_Client. Consulte com GetNetMode(). Clientes enviam pedidos (RPCs Server) e o servidor valida e aplica. Nunca confie em valores vindos do cliente (dano, posição, compras) sem validação.

## Rede: autoridade e papéis (roles)
HasAuthority() é verdadeiro no servidor para atores criados por ele. GetLocalRole() / GetRemoteRole(): ROLE_Authority (servidor), ROLE_AutonomousProxy (o Pawn controlado por este cliente), ROLE_SimulatedProxy (atores de outros jogadores e objetos no cliente). IsLocallyControlled() (Pawn) indica que o input é local. Padrão: if (HasAuthority()) { lógica do servidor } else { pedir ao servidor via RPC }.

## Rede: replicar um ator
No construtor: bReplicates = true; SetReplicateMovement(true) para replicar posição/rotação. Só atores criados no servidor com bReplicates aparecem nos clientes. Componentes: SetIsReplicated(true) (ou SetIsReplicatedByDefault no construtor do componente). Atores colocados no nível já existem nos dois lados e são associados por nome (bNetLoadOnClient).

## Rede: propriedades replicadas e RepNotify
```cpp
// .h
UPROPERTY(ReplicatedUsing = OnRep_Health) float Health = 100.f;
UPROPERTY(Replicated) int32 Ammo = 30;
UFUNCTION() void OnRep_Health(float OldHealth);
virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

// .cpp
#include "Net/UnrealNetwork.h"
void AMyCharacter::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);
    DOREPLIFETIME(AMyCharacter, Health);
    DOREPLIFETIME_CONDITION(AMyCharacter, Ammo, COND_OwnerOnly);
}
```
Só o servidor deve alterar propriedades replicadas. OnRep roda nos clientes quando o valor chega (não roda no servidor em C++: chame manualmente se o servidor também precisar do efeito visual). Condições úteis: COND_OwnerOnly, COND_SkipOwner, COND_InitialOnly, COND_SimulatedOnly, COND_AutonomousOnly. A replicação envia o estado mais recente, não cada mudança intermediária.

## Rede: RPCs
```cpp
UFUNCTION(Server, Reliable, WithValidation) void ServerFire(FVector_NetQuantize Aim);
UFUNCTION(NetMulticast, Unreliable)          void MulticastPlayFireFX();
UFUNCTION(Client, Reliable)                  void ClientShowMessage(const FText& Msg);

void AMyCharacter::ServerFire_Implementation(FVector_NetQuantize Aim) { /* valida e aplica */ MulticastPlayFireFX(); }
bool AMyCharacter::ServerFire_Validate(FVector_NetQuantize Aim) { return true; }  // false desconecta o cliente
void AMyCharacter::MulticastPlayFireFX_Implementation() { /* efeitos */ }
```
Server: cliente pede ao servidor; só funciona em atores que o cliente possui (seu Pawn, PlayerController, PlayerState ou atores com Owner apontando para a sua conexão). Client: servidor chama no cliente dono. NetMulticast: servidor chama em todos (inclusive nele). Reliable garante entrega e ordem (use para ações importantes e pouco frequentes); Unreliable pode se perder (efeitos, dados frequentes). Excesso de RPCs Reliable satura o buffer e desconecta.

## Rede: dono (Owner) e por que o RPC Server não chega
Um RPC Server chamado num ator sem dono (ex.: uma porta do nível) é descartado silenciosamente. Solução: rotear pelo PlayerController ou pelo Pawn do jogador (o personagem chama ServerInteract(Porta) e o servidor executa na porta), ou definir o Owner do ator para o PlayerController (SetOwner no servidor). Erro comum relacionado: "No owning connection for actor".

## Rede: relevância, prioridade e frequência
NetCullDistanceSquared define a distância de relevância; bAlwaysRelevant ignora a distância; bOnlyRelevantToOwner. NetUpdateFrequency (atualizações por segundo, ex.: 100 para o jogador, 2 a 10 para objetos lentos) e MinNetUpdateFrequency. NetPriority dá preferência quando a banda é limitada. ForceNetUpdate() envia já. Dormência (NetDormancy: DORM_Initial, DORM_DormantAll) para atores que raramente mudam: acorde com FlushNetDormancy antes de alterar. Reduzir frequência e usar dormência é a principal otimização de rede no servidor.

## Rede: Replication Graph e Iris
Para jogos com muitos jogadores e atores (dezenas de jogadores, milhares de atores), o Replication Graph organiza atores em nós espaciais e por regras para reduzir o custo de decidir o que replicar. A UE5 trouxe o Iris, novo sistema de replicação (opt-in, habilitado por plugin e configuração nas versões 5.x), mais eficiente em CPU e com filtragem e priorização próprias. Para projetos pequenos e médios, o sistema padrão com ajustes de frequência e dormência basta.

## Rede: previsão no cliente
O Character Movement Component já faz previsão: o cliente move imediatamente, envia os movimentos ao servidor, e o servidor corrige se discordar (correção com suavização). Para outras ações (atirar, habilidades), o padrão é executar localmente o efeito visual na hora (previsão cosmética) e pedir ao servidor, que confirma e replica o resultado. O GAS tem previsão embutida (Prediction Keys) para habilidades e efeitos. Movimentos customizados (dash, wallrun, sprint) que funcionam bem com lag devem ser implementados dentro do CMC (FSavedMove com flags comprimidas e GetCompressedFlags/UpdateFromCompressedFlags, ou a extensão de movimento da versão).

## Rede: compensação de lag em tiros
Hitscan com lag: o cliente atira no que vê, mas o servidor está "no futuro". Abordagens: confiar parcialmente no cliente (o cliente informa o alvo e o servidor valida distância, linha de visão e tempo), ou rebobinar no servidor (server-side rewind: guardar o histórico de posições das hitboxes dos últimos ~200 ms e testar o tiro na posição do instante em que o cliente atirou). Projéteis lentos podem ser criados no servidor com um projétil cosmético previsto no cliente.

## Rede: tipos quantizados e banda
FVector_NetQuantize (arredonda para inteiros), FVector_NetQuantize10 / 100 (1 ou 2 casas decimais), FVector_NetQuantizeNormal (vetores unitários). Para rotações, FRotator::CompressAxisToByte/Short. Estruturas customizadas podem implementar NetSerialize (com TStructOpsTypeTraits WithNetSerializer) para compactar bits. Fast Array Serializer (FFastArraySerializer) replica arrays grandes enviando só itens alterados, com callbacks por item (inventários).

## Rede: servidor dedicado
Precisa da engine compilada a partir do código-fonte (GitHub da Epic) para gerar o target Server: crie MeuJogoServer.Target.cs com Type = TargetType.Server, compile Development Server e empacote pelo Project Launcher ou com RunUAT BuildCookRun -server -noclient. Rode com MeuJogoServer.exe /Game/Mapas/Mapa -log -port=7777. Clientes conectam com o comando open IP:7777. No código, proteja o que só faz sentido com tela (UI, áudio, efeitos) com IsNetMode(NM_DedicatedServer) ou GetNetMode() != NM_DedicatedServer.

## Rede: testes e depuração
PIE com 2+ jogadores (Listen Server e Client), Network Emulation (latência 100-200 ms, perda 1-5%), comandos net.PktLag=150 e net.PktLoss=5, stat net, a ferramenta Network Profiler/Networking Insights (Unreal Insights com -trace=net) para ver banda por ator e propriedade, e logs com a categoria LogNet. Sempre teste como cliente: muitos bugs não aparecem no servidor.

## Rede: erros comuns
Alterar propriedade replicada no cliente (é sobrescrita pelo servidor); esperar OnRep no servidor; RPC Server em ator sem dono; spawnar ator replicado no cliente (só existe localmente); lógica de BeginPlay que assume que o PlayerState ou o Controller já existem no cliente (use OnRep_PlayerState, OnRep_Controller ou PossessedBy); usar GetPlayerController(0) no servidor; TMap replicado (não suportado: use TArray de structs); RPCs Reliable no Tick.
