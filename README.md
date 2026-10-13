# LLM Local

Um app seu para rodar modelos de IA no seu PC. Sem conta, sem plano pago, sem telemetria e sem nada sendo enviado para a internet.

## Instalação

Rode **`desktop\dist\LLM Local Setup 1.0.0.exe`**. Ele cria atalhos no Menu Iniciar e na Área de Trabalho. Como o instalador não é assinado digitalmente, o Windows pode mostrar a tela "O Windows protegeu o computador". Clique em *Mais informações → Executar assim mesmo*.

### Segundo plano e pergunta rápida
- Fechar a janela **não encerra** o app: ele continua no ícone perto do relógio. Para sair de verdade, clique com o botão direito no ícone e escolha **Sair**.
- **`Ctrl+Shift+Espaço`**, de qualquer lugar do Windows, abre a **pergunta rápida**: uma janelinha flutuante para perguntar e receber a resposta na hora.
  - `Enter` envia · `Esc` para a resposta ou esconde a janela · `Ctrl+N` começa uma nova conversa · `Ctrl+Shift+C` copia a resposta · `Ctrl+O` continua a conversa no app completo
  - 📌 fixa a janela, para ela não sumir ao clicar fora
  - Se o modelo estiver descarregado, ela carrega o último modelo usado sozinha
- Em **Configurações → App desktop** você troca o atalho, liga ou desliga "Iniciar com o Windows" e muda a pasta de dados.
- Pelo menu do ícone perto do relógio dá para **descarregar o modelo** e liberar a GPU (para jogar, por exemplo) sem fechar o app.

### Gerar o instalador de novo (depois de mudar o código)
```
cd desktop
npm install
node node_modules\electron\install.js
npm run dist
```

## Como usar

1. Abra o **LLM Local**.
2. **Modelos → Motor**: clique em *Instalar* no **CUDA** (para placa NVIDIA). Isso baixa o `llama.cpp` direto do GitHub oficial.
3. **Modelos → Baixar modelos**: busque um modelo (ex.: `Qwen`, `gemma`) e baixe um arquivo **Q4_K_M**. A etiqueta verde "cabe na GPU" mostra o que roda rápido na sua placa.
4. Escolha o modelo no topo, clique em **Carregar** e converse.

Para encerrar de vez, clique com o botão direito no ícone perto do relógio e escolha **Sair**. O modelo é descarregado junto.

## Pastas

Ficam dentro da pasta de dados escolhida na primeira execução (dá para mudar em Configurações → App desktop).

| Pasta | Conteúdo |
|---|---|
| `models/` | Seus arquivos `.gguf`. Pode copiar modelos para cá manualmente. |
| `engine/` | O motor llama.cpp (CUDA / Vulkan / CPU) |
| `data/chats/` | Suas conversas, em JSON |
| `data/settings.json` | Suas configurações |

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
| `app/web/` | Interface: `index.html` (janela principal), `quick.html` (pergunta rápida), `common.js` (código compartilhado) |
