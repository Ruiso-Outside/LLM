# Arasaka Mikoshi

> Antes chamado **Piphin LLM**. Os arquivos, pastas e dados continuam com o nome antigo.

App da **Piphin Studio** para rodar modelos de IA no seu PC. Sem conta, sem plano pago, sem telemetria e sem nada sendo enviado para a internet. (Os arquivos e a pasta do programa ainda se chamam `LLM Local`, para as instalações existentes continuarem se atualizando.)

## Instalação

1. Baixe **`LLM-Local-X.Y.Z-win-x64.zip`** na página de [Releases](https://github.com/Ruiso-Outside/ArasakaMikoshi/releases/latest).
2. Extraia numa pasta fixa (ex.: `C:\Programas\LLM Local` ou `G:\LLM\LLM Local`).
3. Abra o **`LLM Local.exe`**. Na primeira vez, o app oferece criar os atalhos no Menu Iniciar e na Área de Trabalho (dá para recriar depois pelo menu do ícone perto do relógio).

**Por que um .zip e não um instalador?** O **Controle Inteligente de Aplicativos** do Windows bloqueia programas sem assinatura digital, inclusive instaladores. O `LLM Local.exe` é o executável do Electron oficial, sem modificações, que o Windows já reconhece, por isso ele abre normalmente (o arquivo `.exe` mostra o ícone do Electron; os atalhos e a janela usam o do Arasaka Mikoshi). As atualizações também não executam instalador nenhum. Para desinstalar, apague a pasta do app (seus modelos e conversas ficam na pasta de dados escolhida na primeira execução).

### Segundo plano e pergunta rápida
- Fechar a janela **não encerra** o app: ele continua no ícone perto do relógio. Para sair de verdade, clique com o botão direito no ícone e escolha **Sair**.
- **`Ctrl+Shift+Espaço`**, de qualquer lugar do Windows, abre a **pergunta rápida**: uma janelinha flutuante para perguntar e receber a resposta na hora.
  - `Enter` envia · `Esc` para a resposta ou esconde a janela · `Ctrl+N` começa uma nova conversa · `Ctrl+Shift+C` copia a resposta · `Ctrl+O` continua a conversa no app completo
  - 📌 fixa a janela, para ela não sumir ao clicar fora
  - **Tela e área de transferência:** 📋 anexa o que você copiou (texto ou imagem) e 🖥 anexa um print do monitor. O atalho global **`Ctrl+Alt+S`** tira o print e já abre a janela com ele; é só perguntar (ou apertar Enter para "o que é isto?"). Colar uma imagem com `Ctrl+V` também anexa. Para imagens, use um modelo com visão 👁
  - **Voz:** 🎤 (ou `Ctrl+M`) grava sua pergunta, o Whisper transcreve e envia. O atalho global **`Ctrl+Alt+Espaço`** abre a janela já gravando; aperte de novo para enviar. 🔊 lê as respostas em voz alta com as vozes do Windows (escolha a voz em Configurações → App desktop)
  - Dá para escolher um **modelo próprio** para ela (Configurações → App desktop → Modelo da pergunta rápida), por exemplo um modelo pequeno e rápido, e onde ele roda (GPU ou CPU). Ele é carregado junto com o principal, sem trocar o modelo do app
  - Sem modelo próprio, ela usa o principal (e carrega o último usado se estiver descarregado)
- Em **Configurações → App desktop** você troca o atalho, liga ou desliga "Iniciar com o Windows" e muda a pasta de dados.
- Pelo menu do ícone perto do relógio dá para **descarregar o modelo** e liberar a GPU (para jogar, por exemplo) sem fechar o app.

### Atualizações automáticas
Ao abrir (e a cada 6 horas), o app consulta os [Releases do GitHub](https://github.com/Ruiso-Outside/ArasakaMikoshi/releases). Se houver versão nova, ele baixa só os arquivos do app (`app-patch-X.zip`, menos de 1 MB), confere o SHA-512 e pergunta se pode reiniciar. Se você escolher "Depois", a atualização é aplicada quando o app for fechado. Dá para verificar na hora em **Configurações → App desktop** ou no menu do ícone perto do relógio.

A atualização **não executa nenhum instalador**: ela troca só as pastas `resources\app` e `resources\server`. O `.exe` continua sendo o do Electron oficial, por isso o **Controle Inteligente de Aplicativos** do Windows não bloqueia. Se algo falhar, o app volta à versão anterior. Só quando a versão do Electron mudar (raro) o app pede para baixar o instalador completo.

> **Assinatura digital:** para o Windows mostrar "Editor: Piphin Studio" e aceitar também o instalador, é preciso um certificado de assinatura de código (OV, a partir de ~US$ 216/ano; em nome da empresa exige CNPJ). O Azure Artifact Signing não está disponível para o Brasil.

### Publicar uma versão nova (para todos os PCs atualizarem)
1. Aumente `"version"` em `desktop/package.json` (ex.: `1.2.0` → `1.3.0`).
2. Faça commit e push, e crie a tag da versão: `git tag v1.3.0` e `git push origin v1.3.0`.
3. Publique o Release (precisa de um token do GitHub com permissão de escrita no repositório, na variável `GH_TOKEN`):
```
cd desktop
set GH_TOKEN=seu_token
npm run release
```
O comando confere a tag, cria **um único** Release, gera o `.zip` portátil e o pacote de atualização (`app-patch-X.zip` + `patch.json`), e espera o **GitHub Actions** (workflow *Instalador Windows*, disparado pela tag) anexar o instalador `LLM-Local-Setup-X.exe` + `latest.yml`, que as versões antigas (até a 1.3.0) usam para se atualizar. O instalador é gerado na nuvem porque o Controle Inteligente de Aplicativos bloqueia o build dele no PC. Ele gera o pacote (`app-patch-X.zip` + `patch.json`), envia tudo e no fim verifica se tudo baixa. Ele cria o Release `v1.3.0` com os arquivos que o app usa para se atualizar (`latest.yml`, instalador e `.blockmap`).

### Gerar a versão portátil de novo, sem publicar
```
cd desktop
npm install
node node_modules\electron\install.js
npm run dist
```

### Módulo da Arasaka Central
O Arasaka Mikoshi também roda **dentro do [Arasaka Central](https://github.com/Ruiso-Outside/ArasakaCentral)** (1.2.0 ou mais novo), como módulo de cerca de 1 MB: usa o Electron do Hub em vez de trazer o próprio.
- `desktop/module/backend.js` faz o papel do `desktop/main.js`: inicia o mesmo servidor Python, cuida da pergunta rápida (janela extra do Hub), dos atalhos globais, do print da tela e da área de transferência.
- `app/web/piphin-bridge.js` monta a mesma ponte `window.llmDesktop` falando com o Hub; no app separado e no navegador ele não faz nada.
- A configuração e a pasta de dados são as mesmas do app separado (`%APPDATA%\LLM Local\config.json`). Evite abrir os dois ao mesmo tempo: os atalhos ficam com quem abriu primeiro.
- No Hub, "Iniciar com o Windows" é do Hub (o módulo só liga e desliga a opção dele) e as atualizações do módulo são feitas pelo Hub.

`npm run module` gera `desktop\dist\piphin-module-llm-X.Y.Z.zip`; o `npm run dist` e o `npm run release` já o geram, e o `release` o envia ao Release junto com o pacote de atualização.

## Como usar

1. Abra o **Arasaka Mikoshi**.
2. **Modelos → Runtime**: clique em *Instalar* no **CUDA** (para placa NVIDIA). Isso baixa o `llama.cpp` direto do GitHub oficial.
3. **Modelos → Baixar modelos**: busque um modelo (ex.: `Qwen`, `gemma`). Cada resultado mostra o que o modelo sabe fazer e se cabe na sua placa. Ao abrir um, o arquivo marcado com ⭐ é o de melhor qualidade que cabe na sua GPU.

   | Ícone | Significado |
   |---|---|
   | 👁 Visão / 🎬 Vídeo | Enxerga imagens (e vídeos, pelos quadros). Baixe com "Incluir visão" |
   | 🎧 Áudio | Entende áudio direto (sem isso, o app usa o Whisper) |
   | 🛠️ Ferramentas | Funciona no modo Codex |
   | 🧠 Raciocínio | Pensa antes de responder |
   | 💻 Programação | Especializado em código |
   | 🔓 Sem censura | Ajustado para recusar menos |
   | ⚡ MoE rápido | Usa só parte dos parâmetros por vez: roda mais rápido do que o tamanho sugere |
   | ✨ Otimizado | Quantização com imatrix/dinâmica: mais qualidade no mesmo tamanho |
   | 🎨 Gera imagens / 🔎 Embedding | Não são modelos de conversa |
   | 🧩 / 📏 / ★ | Parâmetros, contexto máximo e qualidade do arquivo (quantização) |

   Use os filtros (👁 Visão, 🛠️ Codex, 🖥️ Cabe na minha GPU...) para achar mais rápido.
4. Escolha o modelo no topo, clique em **Carregar** e converse.

Para encerrar de vez, clique com o botão direito no ícone perto do relógio e escolha **Sair**. O modelo é descarregado junto.

## Pastas

Ficam dentro da pasta de dados escolhida na primeira execução (dá para mudar em Configurações → App desktop).

| Pasta | Conteúdo |
|---|---|
| `models/` | Seus arquivos `.gguf`. Pode copiar modelos para cá manualmente. |
| `engine/` | O motor llama.cpp (CUDA / Vulkan / CPU) |
| `data/chats/` | Suas conversas, em JSON |
| `data/uploads/` | Arquivos anexados e imagens geradas (apagados junto com a conversa) |
| `models/mmproj/`, `models/whisper/`, `models/image/` | Arquivos de visão, modelos do Whisper e de imagem |
| `data/settings.json` | Suas configurações |

## Modos: Chat, Codex e Imagem

Acima da caixa de mensagem há quatro modos:

### 💬 Chat com anexos 📎
Clique no 📎, arraste arquivos para a janela ou cole (Ctrl+V). O app prepara cada tipo:

| Tipo | O que acontece |
|---|---|
| Texto e código (`.txt`, `.py`, `.js`, `.json`, `.csv`...) | O conteúdo vai junto com a mensagem |
| PDF | O texto é extraído. PDFs escaneados viram imagens das primeiras páginas |
| Word, Excel, PowerPoint (`.docx`, `.xlsx`, `.pptx`, `.odt`) | O texto é extraído |
| Imagens | O modelo **vê** a imagem, se tiver visão (veja abaixo) |
| Áudio | É transcrito pelo Whisper. Modelos que entendem áudio recebem o som direto |
| Vídeo | O app extrai alguns quadros (para modelos com visão) e transcreve o áudio |

**Visão:** para o modelo enxergar imagens, ele precisa de um projetor de visão (*mmproj*). Ao baixar um modelo com visão (Gemma 3, Qwen2.5-VL, Qwen3-VL...), deixe marcado **"Incluir visão"**. Para modelos já baixados, escolha o arquivo em **Modelos → Meus modelos**. O topo mostra `👁 visão` quando o modelo carregado enxerga.

### 🛠️ Codex (agente de programação)
O modelo cria e edita projetos de software sozinho, **somente** dentro das pastas que você liberar (escolha no seletor ao lado dos modos, ou em Configurações → Codex).
- Ele lista, lê, cria, edita, busca e apaga arquivos, roda comandos no PowerShell (instalar dependências, compilar, testar) e pode gerar imagens para o projeto.
- **Comandos e exclusões pedem sua confirmação** (Permitir / Sempre nesta conversa / Negar). Em Configurações dá para também pedir confirmação antes de alterar arquivos.
- Caminhos fora da pasta liberada são bloqueados.
- Funciona melhor com modelos bons em programação e em "tool calling", como Qwen3, Qwen3-Coder ou Devstral, e com contexto de 32k ou mais.

**RAG no Codex:** escolha a base no 📚 da barra do Codex. O Codex ganha a ferramenta *search_knowledge* e consulta seus documentos (specs, documentação, código de referência) quantas vezes precisar enquanto trabalha, citando os trechos como [D1], [D2].

**Desfazer o que o Codex fez:** antes de alterar um arquivo, o Codex guarda a versão original. Na resposta aparecem **🔍 Ver alterações** (as diferenças, linha por linha) e **↩ Desfazer alterações** (tudo volta a ficar como antes do pedido; arquivos criados são removidos). Comandos executados não são desfeitos. Os pontos de restauração ficam 30 dias.

### 🔌 Ferramentas MCP (Roblox Studio e outros programas)
O Codex e os agentes podem controlar outros programas que falam **MCP** (Model Context Protocol). Configure em **Configurações → Ferramentas MCP**.
- **Roblox Studio:** clique em **+ Roblox Studio** (aparece se o Studio estiver instalado). Com o Studio aberto num jogo, a IA consegue consultar e alterar o jogo com código Luau, criar e editar scripts, entrar e sair do modo Play, rodar testes e ler o console para corrigir erros.
- **Outros servidores:** **+ Outro servidor** aceita um programa local (comando, ex.: `npx -y @modelcontextprotocol/server-filesystem "C:\Projetos"`) ou um servidor remoto (URL).
- **No Codex:** os servidores com *Usar no Codex* ficam disponíveis junto com a pasta. No seletor de pasta, **🔌 Sem pasta: só ferramentas MCP** usa apenas os programas (bom para trabalhar só no Roblox Studio).
- **Nos agentes:** marque os servidores no editor de cada agente (campo *Ferramentas MCP*). Um agente sozinho com ferramentas, ou dentro de um grupo, chama as ferramentas e mostra cada passo.
- **Confirmação:** ações que alteram algo pedem **Permitir / Sempre nesta conversa / Negar**. Ferramentas só de leitura não pedem. Marque *Não pedir confirmação* se confiar no servidor.

### 🕹️ Arasaka Construct (MCP, sem configurar nada)
A Mikoshi conversa com o **[Arasaka Construct](https://github.com/Ruiso-Outside/ArasakaConstruct)** (a engine de jogos do estúdio, só por convite) pelo MCP, sozinha:
- **Descoberta:** ao abrir, ela procura o editor instalado (o que a Arasaka Central instalou, `~/.local/bin/demonic-editor` no Linux, a pasta do app no Windows ou o `PATH`) e abre `demonic-editor <projeto> --mcp` em segundo plano. O projeto é o aberto por último no editor (a mesma lista da tela inicial dele); dá para escolher outro no setor **Sprites**.
- **Estado na tela:** o indicador **Construct** na barra de cima fica verde com o número de ferramentas (37 na 0.25.0), mostra o erro em vermelho ou "Construct ausente". Clique nele para ver os detalhes, reconectar e trocar de projeto.
- **No Codex:** as ferramentas do Construct (criar projeto e cenas, escrever scripts, rodar o jogo, tirar print, mexer no banco...) ficam ligadas como as dos outros servidores MCP, com as mesmas confirmações. Em Configurações → Ferramentas MCP ele aparece como servidor embutido: dá para desligar, não pedir confirmação ou escolher as ferramentas (ocupam ~4,6 mil tokens).
- Precisa do Construct **0.25.0** ou mais novo para receber imagens (`write_image` e `create_sprite`); as versões antigas conectam, mas não recebem sprites.

### 👾 Sprites (pixel art com IA local)
Setor próprio (botão **👾 Sprites** na barra da esquerda) para criar personagens, itens e folhas de sprites:
1. **Preparar (uma vez):** *Instalar motor* baixa o stable-diffusion.cpp (Vulkan, ~40 MB; no Linux a Mikoshi escolhe o pacote que roda com a glibc do sistema). Depois escolha o **Modelo** e clique em *Baixar modelo* (a Mikoshi mostra o tamanho e pergunta antes; vai para `models/image/<modelo>`):

   | Modelo | O que baixa | Total | Para quem |
   |---|---|---|---|
   | **Qwen-Image 2512 (20B, máximo)** — padrão | Qwen-Image 2512 GGUF Q4_K_M (13,3 GB) + Qwen2.5-VL 7B Q4_K_M como codificador de texto (4,7 GB) + VAE (254 MB) + LoRA [Pixel Art](https://huggingface.co/prithivMLmods/Qwen-Image-2512-Pixel-Art-LoRA) (1,2 GB) + LoRA [Lightning 8 passos](https://huggingface.co/lightx2v/Qwen-Image-2512-Lightning) (850 MB) | **~20,3 GB** | placas de 16 GB: o melhor resultado, mais lento |
   | **Z-Image Turbo (6B, rápido)** | Z-Image Turbo bf16 sem quantizar (12,3 GB) + Qwen3 4B Q8 (4,3 GB) + VAE (335 MB) + LoRA [Pixel Art Style](https://huggingface.co/tarn59/pixel_art_style_lora_z_image_turbo) (170 MB) | **~17,1 GB** | ótima qualidade, várias vezes mais rápido |
   | **Pixel Art XL (SDXL, leve)** | SDXL 1.0 (6,9 GB) + VAE fp16 (335 MB) + LoRA [Pixel Art XL](https://huggingface.co/nerijs/pixel-art-xl) (171 MB) + LCM LoRA (394 MB) | **~7,8 GB** | placas de 8 GB |

   Sem escolha, o setor usa o mais forte já baixado. Todos têm licença aberta (Apache 2.0, MIT ou OpenRAIL) e não pedem conta no Hugging Face.
2. **Gerar:** descreva o sprite (inglês dá resultados melhores), escolha o tamanho (**16, 24, 32, 48, 64, 96 ou 128 px**), o número de cores, as **direções** (frente, esquerda, direita, costas: uma linha da folha cada) e as **variações** por direção (colunas). *Rápido* usa 8 passos (Lightning, Turbo ou LCM); *Qualidade* usa mais passos (40 no Qwen-Image, bem mais lento). A mesma semente em todas as direções mantém o mesmo personagem.
3. **Pixel art de verdade:** a imagem do modelo passa por um pós-processamento próprio (sem bibliotecas extras): tira o fundo (a cor da borda, com limpeza da franja), recorta o desenho, reduz escolhendo a **cor dominante de cada bloco** (vizinho mais próximo, sem borrar), encosta os pés na base do quadro, **reduz a paleta** (corte mediano, a mesma paleta em todos os quadros da folha) e põe contorno de 1 px se você quiser. Alfa só 0 ou 255.
4. **Usar:** *Baixar PNG* (folha ou cada quadro), *Reprocessar* (muda tamanho, cores e contorno sem gerar de novo), *Pixelar uma imagem…* (transforma uma imagem sua, sem IA) e **Enviar ao Arasaka Construct**: grava `assets/mikoshi/<nome>.png` e cria `sprites/<nome>.sprite.luau` com as animações `parado` e `andando` no projeto escolhido.

**Por que esses modelos:** numa placa de 16 GB (o PC de referência tem RTX 5070 Ti e 60 GB de RAM), o maior modelo aberto de imagem que cabe é o **Qwen-Image 2512** (20 bilhões de parâmetros, contra 2,6 do SDXL) em Q4_K_M: 13,3 GB na GPU, com o codificador de texto passando pela RAM (`--offload-to-cpu`) e o VAE em blocos. Ele segue descrições longas e desenha formas bem melhor, e a LoRA Lightning corta de 40 para 8 passos. O Z-Image Turbo (6B, inteiro em bf16) é a opção rápida, com a LoRA de pixel art mais baixada do Hugging Face. Tudo roda no stable-diffusion.cpp, que já era o motor de imagem da Mikoshi: um executável de ~40 MB pelo Vulkan, sem PyTorch (~5 GB; as placas RTX 50 pedem builds CUDA 12.8) nem um ComfyUI à parte. Com o modelo de texto carregado ao mesmo tempo, ative "Descarregar o modelo de texto enquanto gera imagens" se faltar memória de vídeo.

**Servidor MCP da Mikoshi:** a Mikoshi também é um servidor MCP em `http://127.0.0.1:8765/mcp` (só no PC), com `generate_sprite` (com `model` para escolher o modelo e `construct_name` para gravar direto no projeto do Construct), `pixelate_image` e `sprite_status`. Assim o Claude Code, o Cursor ou outro assistente que mexe no Construct gera os sprites aqui:
```
claude mcp add --transport http mikoshi http://127.0.0.1:8765/mcp
```

### 🔬 REA (engenharia reversa)
O [REA](https://github.com/morluto/rea) faz parte do motor: o Codex passa a entender programas sem o código-fonte (apps Electron/JavaScript, `.exe`/`.dll`, .NET, Go, Rust, pacotes, SQLite).
- **Instalar:** Configurações → **Codex** → **Instalar REA** (ou o indicador 🔬 na barra do modo Codex, ou Modelos → Runtime). Baixa uma vez (~290 MB: um Node.js portátil oficial, conferido por SHA-256, e o `rea-agents` numa versão fixa) para `engine/rea`. Depois **funciona sem internet** e sem nada instalado no Windows.
- **No Codex:** com uma pasta de projeto, o Codex usa o REA pelo terminal com a saída limitada (`--token-limit`), sem gastar contexto com as 207 ferramentas dele. Dá para desligar em Configurações → Codex.
- **Como ferramentas MCP (opcional):** Configurações → Ferramentas MCP → **+ REA (MCP)** usa a mesma cópia local. O perfil **Essenciais** liga 8 ferramentas (~4,4 mil tokens) e **Windows completo**, 18. Em cada servidor MCP dá para ligar e desligar ferramentas uma a uma.

### 🎨 Imagem
Descreva a imagem (em português mesmo). O modelo de texto carregado melhora a descrição antes de gerar.
- Instale em **Modelos → Mídia**: o motor (*stable-diffusion.cpp*; Vulkan é o recomendado) e um modelo: **Z-Image Turbo** (melhor qualidade, ~6 GB) ou **SDXL Turbo** (mais rápido). Para pixel art, use o setor **👾 Sprites**.
- **Linux:** até a 1.28.3, o instalador do motor baixava o pacote do Ubuntu 26.04, que não abre no Zorin OS 18 / Ubuntu 24.04 (falta `GLIBC_2.43`). Agora ele escolhe a versão mais nova que roda com a glibc do sistema e avisa quando o motor instalado não abre: clique em instalar de novo.
- Escolha o tamanho no seletor ao lado dos modos. Clique na imagem para ampliar; dá para salvar, gerar outra ou abrir a pasta.
- Se faltar memória de vídeo, ative "Descarregar o modelo de texto enquanto gera imagens" nas Configurações.

### 👥 Agentes e grupos
Crie agentes com uma **função** própria e junte vários num **grupo** que trabalha em sequência. Abra **Agentes** na barra lateral (ou o ⚙️ ao lado do modo 👥 Agentes).

- **Agente:** nome, ícone, cor, **modelo** e a função (as instruções dele). Opcionalmente, temperatura própria (baixa para calcular e validar, alta para criar) e permissão para pesquisar na web.
- **Grupo:** uma lista de etapas. Cada agente recebe o seu pedido **e o trabalho dos agentes anteriores**.
- **✅ Validador:** marque uma etapa como validador. Ele termina com *VEREDITO: APROVADO* ou *REPROVADO*. Se reprovar, o agente anterior refaz com o feedback e o validador confere de novo (até o número de tentativas extras do grupo).
- **Modelos prontos:** 🧮 Matemática (cria o cálculo → resolve → valida), 📝 Redação (pesquisa na web → escreve → revisa) e 💻 Programação (planeja → programa → revisa).
- **Um modelo por agente:** cada agente pode usar um modelo diferente (ex.: um leve e rápido para criar, um mais forte para validar). Os modelos diferentes do principal são carregados **ao mesmo tempo**, cada um no seu motor. Em **Onde rodar** você escolhe **GPU** (mais rápido), **CPU** (usa a RAM e não disputa a GPU, ótimo para modelos leves) ou **Automático** (GPU se couber, senão CPU). Se faltar memória, os extras usados há mais tempo são descarregados. Em Modelos → Meus modelos aparece quanto de VRAM e de RAM os modelos estão usando. Extras parados também são descarregados depois de alguns minutos (Configurações → Carregamento do modelo).
- Para usar, escolha o modo **👥 Agentes** e selecione um grupo ou um agente sozinho. Agentes e grupos entram no backup.

## RAG 📚 (Retrieval-Augmented Generation)

A IA responde com base nos **seus documentos**, sem mandar nada para fora do PC.
1. Abra **RAG** na barra lateral e baixe o modelo de embeddings (Qwen3-Embedding 0.6B, ~610 MB, multilíngue).
2. Crie uma base escolhendo uma ou mais pastas e clique em **Indexar**. Lê texto, código, Markdown, PDF, Word, Excel e PowerPoint. Depois, **Atualizar índice** só processa o que mudou.
3. No chat (ou no modo 👥 Agentes), escolha a base no **📚** ao lado do 🌐 Web. A resposta cita os trechos como [D1], [D2]; clique para ver o arquivo.
4. Cada agente também pode ter uma base própria (campo *Base RAG* no editor de agentes).

## Conversas longas

Quando o contexto passa de ~80%, o app **resume a parte antiga da conversa** e continua dali, sem estourar o limite (Configurações → *Resumir a conversa antiga...*). O resumo aparece num divisor recolhível na conversa.

## Speculative decoding ⚡ (MTP, draft model e n-gram)

Alguns repositórios trazem arquivos `mtp-…gguf` (ou `…-FastMTP…`) de algumas centenas de MB. **Eles não são modelos sozinhos**: são um acelerador (Multi-Token Prediction) que adivinha os próximos tokens para o modelo grande conferir, deixando as respostas mais rápidas. Por isso eles não aparecem como modelos para baixar: ao baixar o modelo, marque **⚡ Incluir acelerador MTP**. Em **Meus modelos** dá para escolher ou tirar o acelerador de cada modelo. Se o motor não aceitar o arquivo, o modelo é carregado sem ele (aparece ⚠ no topo).

Outros tipos de speculative decoding em **Meus modelos**: **⚡ N-gram** (sem arquivo nenhum; reaproveita trechos que já apareceram no texto e acelera muito edições e reescritas de código, ~+40% nos testes) e **draft model** (um modelo bem menor da mesma família, como o Qwen2.5-Coder-0.5B para um Qwen2.5-Coder-7B, inclusive o draft model treinado no Fine-tuning).

## Fine-tuning 🧪 (treine a sua própria IA)

O botão **🧪 Treino** no trilho abre uma tela própria para fazer *fine-tuning* (LoRA / QLoRA) de um modelo pequeno com os seus exemplos, por exemplo uma IA dedicada a Unreal Engine 5 e C++.
1. **Ambiente:** instala uma vez, dentro do app (`engine/train`, ~4,5 GB): Python 3.12 portátil, PyTorch com CUDA, transformers, peft, bitsandbytes e os conversores do llama.cpp na mesma versão do motor. Não precisa de nada instalado no Windows.
2. **Dados:** crie um dataset e adicione exemplos (pedido + resposta ideal): importe as suas conversas, importe JSONL, escreva à mão ou **gere a partir de pastas** (ex.: a pasta `Source` do projeto da Unreal). O modelo carregado no topo cria perguntas e respostas a partir dos arquivos, e elas entram como *pendentes* para você revisar. Uma instrução de sistema do conjunto entra em todos os exemplos.
3. **Nova run:** escolha o modelo base (Qwen2.5-Coder 1.5B/3B/7B, Qwen3 1.7B/4B/8B ou qualquer repositório do Hugging Face), a intensidade (Rápido / Equilibrado / Qualidade) e, se quiser, os ajustes avançados (LoRA r e alpha, épocas, taxa de aprendizado, contexto, acúmulo de gradiente, 4 bits).
4. **Painel ao vivo:** passo, época, loss de treino e de avaliação, perplexidade, taxa de aprendizado, norma do gradiente, tempo restante, parâmetros totais e treináveis, LoRA r/α, camadas adaptadas, precisão de cálculo, tamanho dos pesos do adaptador, exemplos e tokens, velocidade, VRAM do treino (atual, pico e reservada), VRAM, uso, temperatura, consumo (W), energia gasta (Wh) e clock da GPU, com gráficos.
5. **Continuar treinando:** em *Nova run → Continuar uma IA já treinada*, escolha um treino anterior (ou a pasta de um adaptador LoRA) e um conjunto com o conteúdo novo. O treino parte do adaptador da IA anterior, com o mesmo modelo base, e por padrão revisa também os exemplos dos treinos anteriores para a IA não esquecer o que já aprendeu. Cada rodada vira uma nova versão (v2, v3...). Arquivos `.gguf` não podem ser treinados de novo: o treino continua a partir do adaptador salvo na execução.
6. **Draft model da sua IA (speculative decoding):** no painel de uma run concluída, *⚡ Treinar draft model* treina um modelo pequeno da mesma família (ex.: Qwen2.5-Coder-0.5B para uma IA baseada no 7B) com os mesmos exemplos. Ao gerar o GGUF dele, ele é ligado sozinho como draft model do modelo de origem: o pequeno escreve um rascunho e o grande confere, com a mesma qualidade.
7. **Modelo final:** junta o LoRA ao modelo base, converte para GGUF e quantiza (Q4_K_M a F16). O resultado aparece em **Meus modelos** (pasta `models/treinados`) e pode virar o modelo do modo Codex com um clique; pela API local, ele também chega ao Visual Studio.

Dica: a IA fica leve por causa do **modelo base pequeno**; o fine-tuning a especializa. Para os *fatos* (APIs, documentação), combine com uma base de conhecimento. A qualidade depende principalmente dos exemplos: revise os gerados antes de treinar.

## Integrações: Visual Studio, VS Code, Unreal Engine 🔗

Em **Configurações → Integrações → Ligar a API local**, o Arasaka Mikoshi vira um servidor de IA para outros programas do seu PC. A API é compatível com o **Ollama** (`/api/tags`, `/api/chat`, `/api/generate`...) e com a **OpenAI** (`/v1/chat/completions`, `/v1/models`...), na porta **11434** (a do Ollama, onde as IDEs já procuram).
- **Visual Studio** (versões novas, 2026 / 18.x): Copilot Chat → modo Agent → seletor de modelo → *Manage models* → **Ollama** (o endereço `http://127.0.0.1:11434/v1` é preenchido sozinho). O Visual Studio 2022 só aceita OpenAI, Anthropic e Google como modelo próprio.
- **VS Code**: Copilot Chat → *Manage Models* → **Ollama**.
- **Unreal Engine 5 e outros**: POST para `http://127.0.0.1:11434/v1/chat/completions` no formato da OpenAI (módulo HTTP do C++ ou um plugin de requisições no Blueprint).
- **Modelos**: `piphin-chat`, `piphin-codex` e `piphin-agentes` usam o modelo de cada modo; os modelos baixados também aparecem pelo nome. Eles carregam sob demanda.
- **Segurança**: só aceita programas do próprio PC, bloqueia páginas da web e pode exigir uma chave (`Authorization: Bearer <chave>`). Desligada por padrão. Se o Ollama de verdade estiver instalado e aberto, troque a porta.
- Dica: para mexer no código C++ do projeto da Unreal, o Codex do Arasaka Mikoshi também trabalha direto na pasta `Source` do projeto.

## Modelo de cada modo 🔁

Em **Configurações → Modelo e motor → Modelo de cada modo**, escolha um modelo para o **Chat**, o **Codex** e os **Agentes**, e o modelo de imagem. Ao entrar num modo, a IA que estiver ativa é descarregada (inclusive os modelos extras; o da pergunta rápida marcado como "manter carregado" fica) e o modelo daquele modo é carregado enquanto você escreve. Se você enviar antes de ele terminar, o app espera o modelo certo. Para imagens, dá para descarregar a IA de texto enquanto gera (ela volta depois).

## Ajustes por modelo ⚙️

Em **Modelos → Meus modelos → ⚙️**, cada modelo pode ter contexto, camadas na GPU, temperatura, top P/K, min P e penalidade próprios. Sem ajustes, o app usa a **amostragem recomendada da família** (Qwen3, Gemma, Llama, Mistral, DeepSeek R1...) e o resto vem das configurações globais.

## Área de trabalho e atalhos ⌨️

- **Trilho à esquerda:** modos (Chat, Codex, Imagem, Agentes), Bases, Modelos, Backup e Configurações. Cada modo tem a sua cor (Chat violeta, Codex verde-água, Imagem rosa, Agentes âmbar) e a sua tela inicial com sugestões.
- **Painel do sistema (▤ ou `Ctrl+I`):** VRAM e RAM reais ao vivo, modelos carregados (com ⏏ para descarregar), uso de contexto da conversa, ferramentas MCP e diagnóstico.
- **Paleta de comandos (`Ctrl+K`):** busca qualquer ação, modelo para carregar ou conversa.
- **Atalhos:** `Ctrl+1` a `Ctrl+4` trocam o modo, `Ctrl+N` nova conversa, `Ctrl+B` mostra/oculta as conversas.

## Travamentos e diagnóstico 🩺
- **Contexto maior que a placa aguenta:** se o contexto das configurações não cabe na memória de vídeo (ou passa do máximo do modelo, lido do próprio arquivo GGUF), a Mikoshi reduz o contexto até caber, carrega o modelo e avisa quanto usou. As configurações não mudam: ajuste em Configurações → Modelo e runtime para não esperar as tentativas. Até a 1.29.0, com um contexto grande demais (ex.: 720000), o modelo dava erro ao ser carregado de novo depois de descarregado.

- **Servidor interno:** se ele parar, o app reinicia sozinho (antes, uma caixa de erro travava o app inteiro até alguém clicar nela, mesmo escondida atrás das janelas).
- **Memória da placa de vídeo:** se ela encher (ex.: um jogo aberto junto com um modelo grande), o Windows passa a usar a RAM como memória de vídeo e tudo fica lento.
- O topo mostra a VRAM real (🎮) e avisa quando ela enche.
- **Proteção de VRAM** (ligada por padrão, em Configurações → Modelo e motor): se a VRAM ficar cheia por ~40 s sem nada sendo gerado, o app descarrega os modelos extras e depois o principal.
- Se a janela parar de responder, aparece a opção de **recarregar** ou **fechar**. A bandeja também tem *Recarregar a janela* e *Abrir relatório de diagnóstico*.
- Um relógio interno registra se o processo principal do app ficar parado por mais de 3 s.
- Tudo fica registrado em `diagnostico.log` (pasta `%APPDATA%\LLM Local` e pasta `data` do app): VRAM, RAM, travamentos da janela e quedas de processos.

## Pesquisa na web 🌐

Ligue o botão **🌐 Web**, ao lado da caixa de mensagem. A cada pergunta, o modelo:
1. cria uma consulta de busca a partir da conversa;
2. pesquisa e lê o texto das principais páginas;
3. responde citando as fontes com [1], [2]. Clique nos números para abrir o site.

Provedores (em Configurações → Pesquisa na web):
- **DuckDuckGo**: o padrão. É grátis e não precisa de chave.
- **Google**: usa a API oficial do Google (Programmable Search), com 100 pesquisas grátis por dia. Para usar, crie um mecanismo em programmablesearchengine.google.com marcando "Pesquisar em toda a Web" e ative a "Custom Search API" no Google Cloud para gerar a chave. O app não lê a página do Google direto porque isso viola os termos do Google e ele bloqueia com CAPTCHA.
- **SearXNG**: se você rodar sua própria instância.

## Contador de tokens

A barra embaixo da caixa de mensagem mostra:
- **Contexto**: quanto da memória do modelo a conversa já ocupa. Perto de 100%, comece uma nova conversa ou aumente o contexto.
- **Conversa**: tokens desta conversa, divididos em ↑ entrada (o que o modelo leu) e ↓ saída (o que ele escreveu).
- **Total geral**: o acumulado de todas as conversas. Dá para zerar em Configurações.

Enquanto o modelo escreve, a velocidade aparece ao vivo (⚡ tok/s) no topo da resposta.

## Idioma

Em **Configurações → Idioma** escolha a língua do app: **Português (Brasil)**, **English** ou **Español**. Vale para a janela principal, a pergunta rápida e o menu do ícone perto do relógio. Em **A IA responde**, escolha se a IA responde no idioma da pergunta ou sempre no idioma do app.

## Dicas

- **Prompt de sistema** (Configurações): instruções fixas que o modelo segue em toda conversa.
- **Backup**: o botão **Backup** na barra lateral gera um `.zip` com todas as conversas, anexos e imagens geradas. Em outro PC (ou depois de reinstalar), use **Restaurar backup**: as conversas são juntadas e nada é apagado.
- **Uso da CPU** (Configurações → Carregamento do modelo): por padrão o motor usa só os núcleos físicos (~50%). Aumente para 70% se o modelo roda total ou parcialmente na CPU. Acima de ~75% raramente fica mais rápido.
- **Contexto**: quanto o modelo "lembra" da conversa. Mais contexto usa mais VRAM. Com 16 GB, 8k–32k vai bem para modelos de 7B–14B.
- **Recusas**: o app não filtra nada. Se um modelo recusar pedidos, isso vem do treino do próprio modelo. Versões *abliterated* ou *uncensored* do Hugging Face são ajustadas para recusar menos.
- **Modelos com raciocínio** (Qwen3, DeepSeek-R1...): o "pensamento" aparece em um bloco recolhível.
- **API compatível com OpenAI**: com um modelo carregado, outros programas podem usar `http://127.0.0.1:8766/v1` (ex.: extensões de VS Code, scripts).

## Testes

`python -m unittest discover -s tests` roda os testes: unidade dos módulos, cliente MCP (com um servidor MCP falso), pixel art (`test_sprites.py`: PNG, fundo, paleta, folhas, escolha do pacote do motor no Linux, conexão com um Construct falso e o servidor MCP da Mikoshi) e integração (o servidor de verdade com um llama-server falso, um stable-diffusion.cpp falso e um Construct falso, sem GPU). No GitHub Actions eles rodam no Windows e no Linux a cada push e antes do instalador de cada Release (o workflow **Instalador Windows** só segue se os **Testes** passarem).

## Requisitos

- Windows 10/11 com Python 3.9+ instalado e no PATH (sem bibliotecas extras); no Linux, como módulo da Arasaka Central, o `python3` do sistema
- Placa NVIDIA (CUDA), AMD/Intel (Vulkan), ou só CPU

## Estrutura do código

| Caminho | O que é |
|---|---|
| `desktop/` | App Electron: janelas, bandeja, atalho global, atualização e empacotamento (.zip portátil) |
| `app/server.py` | Servidor interno (iniciado escondido pelo app): motor, modelos, chat e downloads |
| `app/websearch.py` | Pesquisa na web e leitura das páginas |
| `app/agent.py` | Codex: ferramentas, limite de pasta e confirmações |
| `app/catalog.py` | Etiquetas dos modelos (capacidades, tamanho, qualidade dos arquivos) |
| `app/agents.py` | Agentes personalizados, grupos e o validador com novas tentativas |
| `app/train.py` | Fine-tuning: ambiente, datasets, runs e exportação |
| `app/train_worker.py` | Treino LoRA/QLoRA e exportação para GGUF (roda no Python do treino) |
| `app/gateway.py` | API local compatível com Ollama e OpenAI para outros programas |
| `app/rea.py` | REA no motor: instala o Node.js portátil e o rea-agents e monta as instruções do Codex |
| `app/mcp.py` | Cliente MCP: conecta o Codex e os agentes a programas como o Roblox Studio; acha e conecta sozinho o Arasaka Construct |
| `app/pixel.py` | Pixel art sem bibliotecas: lê e grava PNG, tira o fundo, reduz sem borrar, paleta, contorno e folhas |
| `app/sprites.py` | Setor Sprites: gera com os modelos de pixel art (Qwen-Image, Z-Image, SDXL), envia ao Construct e o servidor MCP da Mikoshi (`/mcp`) |
| `app/kb.py` | RAG: índice vetorial, chunks e busca por embeddings |
| `app/modelsettings.py` | Ajustes por modelo e amostragem recomendada por família |
| `app/media.py` | Whisper, stable-diffusion.cpp, anexos e extração de texto de documentos |
| `app/web/i18n.js` | Traduções da interface (PT-BR, EN, ES) |
| `app/web/` | Interface: `index.html` (janela principal), `quick.html` (pergunta rápida), `common.js` (código compartilhado), `attach.js` (processamento dos anexos), `agents.js` (editor de agentes e grupos), `vendor/pdfjs` (leitor de PDF da Mozilla) |
