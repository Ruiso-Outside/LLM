# 12 Renderização: Lumen, Nanite, sombras, materiais (UE5)

## Lumen: iluminação global dinâmica
Lumen calcula iluminação global (luz rebatida) e reflexões em tempo real, sem lightmaps. Ativação: Project Settings > Rendering > Dynamic Global Illumination Method = Lumen e Reflection Method = Lumen. Software Ray Tracing (usa Mesh Distance Fields, funciona em mais placas) ou Hardware Ray Tracing (Use Hardware Ray Tracing when available; mais preciso, exige GPU com RT). Qualidade no Post Process Volume: Lumen Scene Lighting Quality, Final Gather Quality, Lumen Scene Detail, Max Trace Distance. Visualização: Lit > Lumen > Lumen Scene. Paredes finas (< ~10 cm) vazam luz; malhas muito complexas ou pequenas demais podem não aparecer na cena do Lumen.

## Lumen: luzes e emissivos
Com Lumen, use luzes Movable; Static/Stationary não fazem sentido (sem lightmaps). Materiais emissivos contribuem com luz indireta (limitado; não substituem luzes de verdade para fontes pequenas). Sky Light com Real Time Capture para atualizar com o céu. Interiores precisam de aberturas ou luzes de preenchimento; Lumen não "inventa" luz em salas fechadas.

## Nanite: geometria virtualizada
Nanite permite malhas com milhões de triângulos sem LODs manuais, desenhando só o detalhe visível em pixels. Ative na importação (Build Nanite) ou na Static Mesh (Enable Nanite Support) ou em lote (botão direito > Nanite > Enable). Visualize em Lit > Nanite Visualization (Mask, Triangles, Clusters, Overdraw). Suportado: malhas estáticas opacas e Masked; folhagem e malhas esqueléticas ganharam suporte em versões recentes. Não usa: materiais translúcidos. Objetos simples com poucos triângulos não se beneficiam. Nanite Fallback Mesh é usada em colisão complexa e em plataformas sem suporte.

## Virtual Shadow Maps
Método de sombras padrão da UE5 (Project Settings > Shadows > Shadow Map Method), com resolução virtual alta e cache. Custos: número de luzes com sombra e invalidação do cache por objetos que se movem ou por World Position Offset (folhas ao vento). Ajuste World Position Offset Disable Distance nas malhas e desligue Cast Shadow em luzes pequenas. Visualização: Lit > Virtual Shadow Map. Para hardware fraco/mobile: Shadow Maps tradicionais.

## Luzes: tipos e mobilidade
Directional Light (sol), Point Light, Spot Light, Rect Light, Sky Light. Mobility: Static (assada em lightmaps com Build Lighting; sem custo no jogo, mas não muda), Stationary (posição fixa, cor/intensidade variáveis), Movable (totalmente dinâmica). Com Lumen, use Movable; para mobile ou PCs fracos, lightmaps com Lightmass (GPU Lightmass é mais rápido). Ambiente exterior básico: Directional Light + Sky Atmosphere + Sky Light + Exponential Height Fog + Volumetric Cloud (Window > Env. Light Mixer cria tudo).

## Materiais: entradas principais
Base Color, Metallic (0 ou 1, raramente intermediário), Specular (normalmente 0,5), Roughness (0 espelho, 1 fosco), Emissive Color, Normal, Opacity (Translucent), Opacity Mask (Masked), Ambient Occlusion, World Position Offset (deforma vértices; ex.: vento), Pixel Depth Offset. Shading Models: Default Lit, Unlit, Subsurface, Clear Coat, Two Sided Foliage, Hair, Eye, Cloth, Thin Translucent, Substrate (novo sistema de materiais em camadas das versões recentes).

## Materiais: Material Instance e parâmetros
Transforme valores em parâmetros (Scalar, Vector, Texture Parameter) no material mestre e crie Material Instances (Constant, editadas no editor sem recompilar). Em tempo de execução: UMaterialInstanceDynamic* MID = Mesh->CreateDynamicMaterialInstance(0); MID->SetScalarParameterValue(TEXT("Brilho"), 2.f); SetVectorParameterValue; SetTextureParameterValue. Material Parameter Collection guarda parâmetros globais lidos por todos os materiais (umidade, hora do dia): UKismetMaterialLibrary::SetScalarParameterValue(this, Collection, Nome, Valor). Custom Primitive Data permite variar valores por objeto sem criar instâncias dinâmicas (bom para instancing).

## Materiais: Blend Modes
Opaque (padrão, mais barato), Masked (recorte duro com Opacity Mask: folhas, grades; funciona com Nanite e sombras), Translucent (vidro, água, fumaça; caro, sem escrita de profundidade, problemas de ordenação), Additive, Modulate. Para vidro: Translucent com Lighting Mode Surface TranslucencyVolume ou Surface Forward Shading e Refraction. Evite grandes áreas translúcidas sobrepostas (overdraw).

## Materiais: desempenho
Use Shader Complexity (Optimization Viewmodes) para ver o custo por pixel. Reduza instruções e amostras de textura, use Material Functions para reaproveitar, Static Switch Parameters para criar permutações (cuidado: muitas permutações aumentam o tempo de compilação de shaders), Texture Packing (Roughness, Metallic e AO nos canais R, G, B de uma textura só), e Quality Switch/Feature Level Switch para plataformas. Muitos materiais diferentes na cena aumentam draw calls e trocas de estado.

## Texturas
Compressão por tipo: Default (DXT/BC1/BC3 para cor), Normalmap (BC5), Masks (sem sRGB, para canais de dados), HDR, UserInterface2D (UI sem mipmaps). Desligue sRGB em texturas de dados (Roughness, Metallic, máscaras). Tamanhos em potências de 2 para mipmaps e streaming. Texture Streaming carrega mips sob demanda; problemas de textura borrada podem ser pool de streaming pequeno (r.Streaming.PoolSize). Virtual Textures (SVT) para texturas enormes e Runtime Virtual Textures para mesclar terreno e objetos.

## Pós-processamento
Post Process Volume (Infinite Extent para valer no mapa todo; Priority e Blend Radius para vários volumes): Exposure (trave Min e Max EV100 iguais para exposição fixa, ou use Exposure Compensation), Bloom, Color Grading (saturação, contraste, temperatura, LUT), Vignette, Depth of Field, Motion Blur, Lens Flares, Film Grain, Chromatic Aberration, configurações de Lumen e reflexos, e Post Process Materials (contornos, visão térmica, efeitos de tela; Blendable Location define a etapa).

## Anti-aliasing e upscaling
Temporal Super Resolution (TSR) é o padrão da UE5: renderiza abaixo da resolução e reconstrói com dados temporais. Screen Percentage controla a resolução interna (r.ScreenPercentage). Alternativas por plugin: NVIDIA DLSS, AMD FSR, Intel XeSS. TAA, FXAA e MSAA (este só no Forward Shading, comum em VR). Artefatos de ghosting/borrão em objetos que se movem: verifique velocidades (Output Velocity) e materiais com WPO.

## Escalabilidade (Scalability)
Grupos de qualidade (0 Low a 4 Cinematic): View Distance, Anti-Aliasing, Post Processing, Shadows, Global Illumination, Reflections, Textures, Effects, Foliage, Shading. Configuração em Config/DefaultScalability.ini (CVars por nível). No jogo: UGameUserSettings::GetGameUserSettings() → SetOverallScalabilityLevel, SetShadowQuality, SetScreenResolution, SetFullscreenMode, SetFrameRateLimit, SetVSyncEnabled → ApplySettings(false) e SaveSettings(). RunHardwareBenchmark + ApplyHardwareBenchmarkResults escolhe automaticamente.

## Forward x Deferred shading
Deferred (padrão): muitas luzes dinâmicas e recursos completos (Lumen exige deferred). Forward Shading (Project Settings > Rendering > Forward Shading): mais leve, permite MSAA, comum em VR e mobile; menos recursos de pós-processamento e iluminação. Mobile usa um renderizador próprio (Mobile Forward ou Mobile Deferred).

## Ray tracing e Path Tracer
Hardware Ray Tracing pode alimentar Lumen (melhor qualidade de reflexos e GI) e efeitos específicos. O Path Tracer (Lit > Path Tracing) gera imagens de referência fisicamente corretas e renders finais via Movie Render Queue, mas não é para tempo real em jogos.

## Shaders: compilação e travamentos (stutter)
A compilação de shaders na primeira vez que um material aparece causa travadas (PSO stutter) em DirectX 12/Vulkan. Mitigação: PSO Precaching (ativado por padrão nas versões recentes) e PSO cache coletado jogando o jogo (r.ShaderPipelineCache), compilação antecipada nas telas de carregamento, menos permutações de materiais. O DDC (Derived Data Cache) compartilhado em rede ou na nuvem acelera a compilação para a equipe.
