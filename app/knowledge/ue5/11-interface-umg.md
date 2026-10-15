# 11 Interface: UMG, CommonUI, Slate e MVVM (UE5)

## UMG: conceitos
UMG (Unreal Motion Graphics) é o editor visual de interfaces baseado em Slate. Um Widget Blueprint (UUserWidget) tem a aba Designer (layout) e Graph (lógica). Painéis: Canvas Panel (posição livre com âncoras), Overlay (empilha), Horizontal/Vertical Box, Grid Panel, Uniform Grid Panel, Wrap Box, Scroll Box, Size Box, Scale Box, Border, Spacer, Widget Switcher (troca páginas). Controles: Text, Rich Text Block, Image, Button, Progress Bar, Slider, Check Box, Editable Text, Combo Box, List View/Tile View (listas virtualizadas).

## UMG: âncoras e resolução
Âncoras definem o ponto de referência do widget no Canvas: canto superior esquerdo para a barra de vida, centro (com Alignment 0,5/0,5) para a mira, esticada para barras de largura total. DPI Scaling em Project Settings > User Interface ajusta a escala pela resolução (curva por menor lado da tela). Teste no Designer trocando a resolução de pré-visualização. Prefira Overlay e Boxes a Canvas Panel aninhados: Canvas é mais caro e difícil de adaptar.

## UMG: criar e mostrar widgets em C++
```cpp
// .h
UPROPERTY(EditDefaultsOnly, Category = "UI") TSubclassOf<UUserWidget> HudClass;
UPROPERTY() TObjectPtr<UUserWidget> Hud;

// .cpp (no PlayerController local)
void AMyPlayerController::BeginPlay()
{
    Super::BeginPlay();
    if (IsLocalController() && HudClass)
    {
        Hud = CreateWidget<UUserWidget>(this, HudClass);
        Hud->AddToViewport();
    }
}
```
Crie a interface no PlayerController local (ou no HUD), nunca no servidor dedicado. Remova com RemoveFromParent. Módulos no Build.cs: UMG, Slate, SlateCore.

## UMG: ligar widgets do Designer a variáveis C++
```cpp
UCLASS()
class MYGAME_API UHealthBar : public UUserWidget
{
    GENERATED_BODY()
protected:
    UPROPERTY(meta = (BindWidget)) TObjectPtr<UProgressBar> HealthBar;          // obrigatório no Designer
    UPROPERTY(meta = (BindWidgetOptional)) TObjectPtr<UTextBlock> HealthText;   // opcional
    UPROPERTY(Transient, meta = (BindWidgetAnim)) TObjectPtr<UWidgetAnimation> DamageFlash;
    virtual void NativeConstruct() override;
public:
    void SetHealth(float Current, float Max);
};
```
O Widget Blueprint (filho dessa classe) precisa ter um widget com exatamente o mesmo nome e tipo, senão não compila. NativeConstruct substitui o Event Construct; NativeTick existe, mas evite. Botões: Button->OnClicked.AddDynamic(this, &UMyMenu::HandleClick) no NativeConstruct.

## UMG: atualizar a interface de forma eficiente
Evite Bindings de propriedade (a função roda todo frame). Atualize por eventos: o componente de vida dispara um delegate, o widget escuta e atualiza. Use Invalidation Box ou Retainer Box para áreas estáticas, e marque widgets que não mudam como Volatile = false. List View/Tile View reutilizam entradas (virtualização) para listas grandes; os dados vêm de UObjects (UListView::SetListItems) e a entrada implementa IUserObjectListEntry.

## UMG: input do mouse e do teclado na UI
PlayerController: SetInputMode(FInputModeUIOnly) ou FInputModeGameAndUI, SetShowMouseCursor(true); ao fechar, FInputModeGameOnly e esconder o cursor. Foco: SetUserFocus/SetKeyboardFocus no widget. Navegação por gamepad: configure Navigation nos widgets e use o CommonUI para um tratamento completo de foco e de input por plataforma.

## UMG: menu de pausa
Ao pausar: UGameplayStatics::SetGamePaused(this, true), criar/mostrar o widget, modo de input UI e cursor visível. Com o jogo pausado, ações do Enhanced Input só disparam se o Input Action tiver Trigger when Paused; o widget pode tratar a tecla de voltar em NativeOnKeyDown. Em multiplayer, pausar o jogo inteiro normalmente não faz sentido: abra só o menu local.

## UMG: widgets no mundo
UWidgetComponent mostra um widget no espaço 3D (Space = World) ou sempre virado para a tela (Screen): barras de vida sobre inimigos, painéis interativos. Em Screen Space o custo é menor. Para interação com widgets 3D, use UWidgetInteractionComponent (VR ou mira). Muitos widgets 3D pesam: oculte por distância.

## CommonUI
Plugin da Epic para interfaces de jogos completos (usado no Lyra e no Fortnite): pilhas de telas ativáveis (UCommonActivatableWidget e UCommonActivatableWidgetStack/Queue), roteamento de input por camadas (só a tela do topo recebe input), suporte nativo a gamepad e teclado com troca automática de ícones (Controller Data por plataforma), botões com estilos (UCommonButtonBase), texto estilizado e ações de input (Back, Confirm) declaradas por tela. Exige configurar o Game Viewport Client como CommonGameViewportClient em Project Settings. Recomendado para jogos que sairão em console ou terão suporte a controle.

## MVVM (Model-View-ViewModel)
Plugin UMG Viewmodel: a lógica de UI fica em ViewModels (UMVVMViewModelBase) com propriedades FieldNotify; os widgets ligam suas propriedades às do ViewModel no editor (View Bindings), atualizando só quando o valor muda (sem Tick nem Binding por frame). Separa dados e apresentação e facilita testes e reaproveitamento. Em C++, use UE_MVVM_SET_PROPERTY_VALUE para notificar mudanças.

## Slate
Framework de UI em C++ puro sobre o qual o UMG é construído; usado no editor e em ferramentas. Sintaxe declarativa com SNew(SVerticalBox) + SVerticalBox::Slot()[ SNew(STextBlock).Text(...) ]. No jogo, escreva Slate para widgets muito customizados ou de alto desempenho e exponha ao UMG com uma UWidget que embrulha o SWidget. Para ferramentas de editor, Slate (ou Editor Utility Widgets) é o caminho.

## Localização de textos
Use FText para tudo que o jogador lê (LOCTEXT("Chave", "Texto") com #define LOCTEXT_NAMESPACE, ou NSLOCTEXT). O Localization Dashboard (Tools) coleta os textos, gera arquivos .po para tradução e compila. Troca de idioma em tempo de execução: FInternationalization::Get().SetCurrentCulture(TEXT("pt-BR")) ou o nó Set Current Culture. Strings FString e FName não são localizadas.

## Fontes e estilos
Importe fontes TTF/OTF como Font Face e agrupe numa Font (Composite Font) com fallbacks para outros alfabetos. Para escalar bem, use Font Size com DPI Scaling e evite tamanhos fixos enormes. Estilos reutilizáveis: Slate Widget Style assets ou, no CommonUI, Text Styles e Button Styles.
