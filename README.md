# Piphin LLM

App da **Piphin Studio** para rodar modelos de IA no seu PC. Sem conta, sem plano pago, sem telemetria e sem nada sendo enviado para a internet. (Os arquivos e a pasta do programa ainda se chamam `LLM Local`, para as instalações existentes continuarem se atualizando.)

## Instalação

1. Baixe **`LLM-Local-X.Y.Z-win-x64.zip`** na página de [Releases](https://github.com/Ruiso-Outside/LLM/releases/latest).
2. Extraia numa pasta fixa (ex.: `C:\Programas\LLM Local` ou `G:\LLM\LLM Local`).
3. Abra o **`LLM Local.exe`**. Na primeira vez, o app oferece criar os atalhos no Menu Iniciar e na Área de Trabalho (dá para recriar depois pelo menu do ícone perto do relógio).

**Por que um .zip e não um instalador?** O **Controle Inteligente de Aplicativos** do Windows bloqueia programas sem assinatura digital, inclusive instaladores. O `LLM Local.exe` é o executável do Electron oficial, sem modificações, que o Windows já reconhece, por isso ele abre normalmente (o arquivo `.exe` mostra o ícone do Electron; os atalhos e a janela usam o do Piphin LLM). As atualizações também não executam instalador nenhum. Para desinstalar, apague a pasta do app (seus modelos e conversas ficam na pasta de dados escolhida na primeira execução).

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
Ao abrir (e a cada 6 horas), o app consulta os [Releases do GitHub](https://github.com/Ruiso-Outside/LLM/releases). Se houver versão nova, ele baixa só os arquivos do app (`app-patch-X.zip`, menos de 1 MB), confere o SHA-512 e pergunta se pode reiniciar. Se você escolher "Depois", a atualização é aplicada quando o app for fechado. Dá para verificar na hora em **Configurações → App desktop** ou no menu do ícone perto do relógio.

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

## Como usar

1. Abra o **Piphin LLM**.
2. **Modelos → Motor**: clique em *Instalar* no **CUDA** (para placa NVIDIA). Isso baixa o `llama.cpp` direto do GitHub oficial.
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

**Visão:** para o modelo enxergar imagens, ele precisa de um arquivo de visão (*mmproj*). Ao baixar um modelo com visão (Gemma 3, Qwen2.5-VL, Qwen3-VL...), deixe marcado **"Incluir visão"**. Para modelos já baixados, escolha o arquivo em **Modelos → Meus modelos**. O topo mostra `👁 visão` quando o modelo carregado enxerga.

### 🛠️ Codex (agente de programação)
O modelo cria e edita projetos de software sozinho, **somente** dentro das pastas que você liberar (escolha no seletor ao lado dos modos, ou em Configurações → Codex).
- Ele lista, lê, cria, edita, busca e apaga arquivos, roda comandos no PowerShell (instalar dependências, compilar, testar) e pode gerar imagens para o projeto.
- **Comandos e exclusões pedem sua confirmação** (Permitir / Sempre nesta conversa / Negar). Em Configurações dá para também pedir confirmação antes de alterar arquivos.
- Caminhos fora da pasta liberada são bloqueados.
- Funciona melhor com modelos bons em programação e em "tool calling", como Qwen3, Qwen3-Coder ou Devstral, e com contexto de 32k ou mais.

**Base de conhecimento no Codex:** escolha a base no 📚 da barra do Codex. O Codex ganha a ferramenta *search_knowledge* e consulta seus documentos (specs, documentação, código de referência) quantas vezes precisar enquanto trabalha, citando os trechos como [D1], [D2].

**Desfazer o que o Codex fez:** antes de alterar um arquivo, o Codex guarda a versão original. Na resposta aparecem **🔍 Ver alterações** (as diferenças, linha por linha) e **↩ Desfazer alterações** (tudo volta a ficar como antes do pedido; arquivos criados são removidos). Comandos executados não são desfeitos. Os pontos de restauração ficam 30 dias.

### 🔌 Ferramentas MCP (Roblox Studio e outros programas)
O Codex e os agentes podem controlar outros programas que falam **MCP** (Model Context Protocol). Configure em **Configurações → Ferramentas MCP**.
- **Roblox Studio:** clique em **+ Roblox Studio** (aparece se o Studio estiver instalado). Com o Studio aberto num jogo, a IA consegue consultar e alterar o jogo com código Luau, criar e editar scripts, entrar e sair do modo Play, rodar testes e ler o console para corrigir erros.
- **Outros servidores:** **+ Outro servidor** aceita um programa local (comando, ex.: `npx -y @modelcontextprotocol/server-filesystem "C:\Projetos"`) ou um servidor remoto (URL).
- **No Codex:** os servidores com *Usar no Codex* ficam disponíveis junto com a pasta. No seletor de pasta, **🔌 Sem pasta: só ferramentas MCP** usa apenas os programas (bom para trabalhar só no Roblox Studio).
- **Nos agentes:** marque os servidores no editor de cada agente (campo *Ferramentas MCP*). Um agente sozinho com ferramentas, ou dentro de um grupo, chama as ferramentas e mostra cada passo.
- **Confirmação:** ações que alteram algo pedem **Permitir / Sempre nesta conversa / Negar**. Ferramentas só de leitura não pedem. Marque *Não pedir confirmação* se confiar no servidor.

### 🔬 REA (engenharia reversa)
O [REA](https://github.com/morluto/rea) faz parte do motor: o Codex passa a entender programas sem o código-fonte (apps Electron/JavaScript, `.exe`/`.dll`, .NET, Go, Rust, pacotes, SQLite).
- **Instalar:** Configurações → **Codex** → **Instalar REA** (ou o indicador 🔬 na barra do modo Codex, ou Modelos → Motor). Baixa uma vez (~290 MB: um Node.js portátil oficial, conferido por SHA-256, e o `rea-agents` numa versão fixa) para `engine/rea`. Depois **funciona sem internet** e sem nada instalado no Windows.
- **No Codex:** com uma pasta de projeto, o Codex usa o REA pelo terminal com a saída limitada (`--token-limit`), sem gastar contexto com as 207 ferramentas dele. Dá para desligar em Configurações → Codex.
- **Como ferramentas MCP (opcional):** Configurações → Ferramentas MCP → **+ REA (MCP)** usa a mesma cópia local. O perfil **Essenciais** liga 8 ferramentas (~4,4 mil tokens) e **Windows completo**, 18. Em cada servidor MCP dá para ligar e desligar ferramentas uma a uma.

### 🎨 Imagem
Descreva a imagem (em português mesmo). O modelo de texto carregado melhora a descrição antes de gerar.
- Instale em **Modelos → Mídia**: o motor (*stable-diffusion.cpp*; Vulkan é o recomendado) e um modelo: **Z-Image Turbo** (melhor qualidade, ~6 GB) ou **SDXL Turbo** (mais rápido).
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

## Bases de conhecimento 📚

A IA responde com base nos **seus documentos**, sem mandar nada para fora do PC.
1. Abra **Conhecimento** na barra lateral e baixe o modelo de embeddings (Qwen3-Embedding 0.6B, ~610 MB, multilíngue).
2. Crie uma base escolhendo uma ou mais pastas e clique em **Indexar**. Lê texto, código, Markdown, PDF, Word, Excel e PowerPoint. Depois, **Atualizar índice** só processa o que mudou.
3. No chat (ou no modo 👥 Agentes), escolha a base no **📚** ao lado do 🌐 Web. A resposta cita os trechos como [D1], [D2]; clique para ver o arquivo.
4. Cada agente também pode ter uma base própria (campo *Base de conhecimento* no editor de agentes).

## Conversas longas

Quando o contexto passa de ~80%, o app **resume a parte antiga da conversa** e continua dali, sem estourar o limite (Configurações → *Resumir a conversa antiga...*). O resumo aparece num divisor recolhível na conversa.

## Acelerador MTP ⚡

Alguns repositórios trazem arquivos `mtp-…gguf` (ou `…-FastMTP…`) de algumas centenas de MB. **Eles não são modelos sozinhos**: são um acelerador (Multi-Token Prediction) que adivinha os próximos tokens para o modelo grande conferir, deixando as respostas mais rápidas. Por isso eles não aparecem como modelos para baixar: ao baixar o modelo, marque **⚡ Incluir acelerador MTP**. Em **Meus modelos** dá para escolher ou tirar o acelerador de cada modelo. Se o motor não aceitar o arquivo, o modelo é carregado sem ele (aparece ⚠ no topo).

## Ajustes por modelo ⚙️

Em **Modelos → Meus modelos → ⚙️**, cada modelo pode ter contexto, camadas na GPU, temperatura, top P/K, min P e penalidade próprios. Sem ajustes, o app usa a **amostragem recomendada da família** (Qwen3, Gemma, Llama, Mistral, DeepSeek R1...) e o resto vem das configurações globais.

## Área de trabalho e atalhos ⌨️

- **Trilho à esquerda:** modos (Chat, Codex, Imagem, Agentes), Bases, Modelos, Backup e Configurações. Cada modo tem a sua cor (Chat violeta, Codex verde-água, Imagem rosa, Agentes âmbar) e a sua tela inicial com sugestões.
- **Painel do sistema (▤ ou `Ctrl+I`):** VRAM e RAM reais ao vivo, modelos carregados (com ⏏ para descarregar), uso de contexto da conversa, ferramentas MCP e diagnóstico.
- **Paleta de comandos (`Ctrl+K`):** busca qualquer ação, modelo para carregar ou conversa.
- **Atalhos:** `Ctrl+1` a `Ctrl+4` trocam o modo, `Ctrl+N` nova conversa, `Ctrl+B` mostra/oculta as conversas.

## Travamentos e diagnóstico 🩺

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

`python -m unittest discover -s tests` roda os testes: unidade dos módulos, cliente MCP (com um servidor MCP falso) e integração (o servidor de verdade com um llama-server falso, sem GPU). Eles também rodam no GitHub Actions a cada push.

## Requisitos

- Windows 10/11 com Python 3.9+ instalado e no PATH (sem bibliotecas extras)
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
| `app/rea.py` | REA no motor: instala o Node.js portátil e o rea-agents e monta as instruções do Codex |
| `app/mcp.py` | Cliente MCP: conecta o Codex e os agentes a programas como o Roblox Studio |
| `app/kb.py` | Bases de conhecimento: índice, trechos e busca por embeddings |
| `app/modelsettings.py` | Ajustes por modelo e amostragem recomendada por família |
| `app/media.py` | Whisper, stable-diffusion.cpp, anexos e extração de texto de documentos |
| `app/web/i18n.js` | Traduções da interface (PT-BR, EN, ES) |
| `app/web/` | Interface: `index.html` (janela principal), `quick.html` (pergunta rápida), `common.js` (código compartilhado), `attach.js` (processamento dos anexos), `agents.js` (editor de agentes e grupos), `vendor/pdfjs` (leitor de PDF da Mozilla) |
