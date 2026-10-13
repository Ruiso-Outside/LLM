# LLM Local

Um app seu para rodar modelos de IA no seu PC. Sem conta, sem plano pago, sem telemetria e sem nada sendo enviado para a internet.

## Instalação

Rode **`desktop\dist\LLM Local Setup 1.7.0.exe`**. Ele cria atalhos no Menu Iniciar e na Área de Trabalho. Como o instalador não é assinado digitalmente, o Windows pode mostrar a tela "O Windows protegeu o computador". Clique em *Mais informações → Executar assim mesmo*. O executável do app é o do Electron oficial, sem modificações, para que o **Controle Inteligente de Aplicativos** do Windows não o bloqueie. Por isso o arquivo .exe mostra o ícone do Electron, mas os atalhos e a janela usam o ícone do LLM Local.

### Segundo plano e pergunta rápida
- Fechar a janela **não encerra** o app: ele continua no ícone perto do relógio. Para sair de verdade, clique com o botão direito no ícone e escolha **Sair**.
- **`Ctrl+Shift+Espaço`**, de qualquer lugar do Windows, abre a **pergunta rápida**: uma janelinha flutuante para perguntar e receber a resposta na hora.
  - `Enter` envia · `Esc` para a resposta ou esconde a janela · `Ctrl+N` começa uma nova conversa · `Ctrl+Shift+C` copia a resposta · `Ctrl+O` continua a conversa no app completo
  - 📌 fixa a janela, para ela não sumir ao clicar fora
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
O comando confere a tag, cria **um único** Release, gera o instalador e o pacote de atualização (`app-patch-X.zip` + `patch.json`), envia tudo e no fim verifica se tudo baixa. Ele cria o Release `v1.3.0` com os arquivos que o app usa para se atualizar (`latest.yml`, instalador e `.blockmap`).

### Gerar o instalador de novo, sem publicar
```
cd desktop
npm install
node node_modules\electron\install.js
npm run dist
```

## Como usar

1. Abra o **LLM Local**.
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

## Dicas

- **Prompt de sistema** (Configurações): instruções fixas que o modelo segue em toda conversa.
- **Backup**: o botão **Backup** na barra lateral gera um `.zip` com todas as conversas, anexos e imagens geradas. Em outro PC (ou depois de reinstalar), use **Restaurar backup**: as conversas são juntadas e nada é apagado.
- **Uso da CPU** (Configurações → Carregamento do modelo): por padrão o motor usa só os núcleos físicos (~50%). Aumente para 70% se o modelo roda total ou parcialmente na CPU. Acima de ~75% raramente fica mais rápido.
- **Contexto**: quanto o modelo "lembra" da conversa. Mais contexto usa mais VRAM. Com 16 GB, 8k–32k vai bem para modelos de 7B–14B.
- **Recusas**: o app não filtra nada. Se um modelo recusar pedidos, isso vem do treino do próprio modelo. Versões *abliterated* ou *uncensored* do Hugging Face são ajustadas para recusar menos.
- **Modelos com raciocínio** (Qwen3, DeepSeek-R1...): o "pensamento" aparece em um bloco recolhível.
- **API compatível com OpenAI**: com um modelo carregado, outros programas podem usar `http://127.0.0.1:8766/v1` (ex.: extensões de VS Code, scripts).

## Requisitos

- Windows 10/11 com Python 3.9+ instalado e no PATH (sem bibliotecas extras)
- Placa NVIDIA (CUDA), AMD/Intel (Vulkan), ou só CPU

## Estrutura do código

| Caminho | O que é |
|---|---|
| `desktop/` | App Electron: janelas, bandeja, atalho global e instalador |
| `app/server.py` | Servidor interno (iniciado escondido pelo app): motor, modelos, chat e downloads |
| `app/websearch.py` | Pesquisa na web e leitura das páginas |
| `app/agent.py` | Codex: ferramentas, limite de pasta e confirmações |
| `app/catalog.py` | Etiquetas dos modelos (capacidades, tamanho, qualidade dos arquivos) |
| `app/agents.py` | Agentes personalizados, grupos e o validador com novas tentativas |
| `app/media.py` | Whisper, stable-diffusion.cpp, anexos e extração de texto de documentos |
| `app/web/` | Interface: `index.html` (janela principal), `quick.html` (pergunta rápida), `common.js` (código compartilhado), `attach.js` (processamento dos anexos), `agents.js` (editor de agentes e grupos), `vendor/pdfjs` (leitor de PDF da Mozilla) |
