# ChatToon 2.0.0

**Um personagem 3D que participa da sua live no YouTube:** ele lê o chat, responde com humor
próprio usando a **IA local do BigLinux** (Ollama), fala com voz de verdade pelo
**TTS BigLinux** e se mexe no ritmo da fala — tudo num overlay com fundo transparente para o
OBS Studio. Fora o chat do YouTube, tudo roda no seu computador: sem nuvem, sem chave de API,
sem mensalidade.

> **Autor:** Pedro Bezerra — canal **InfoRecarga** ([youtube.com/@pedro_bezerra](https://www.youtube.com/@pedro_bezerra))
> **Colaborador:** Rafael Ruscher ([github.com/ruscher](https://github.com/ruscher))
> Os dois são voluntários do projeto [BigLinux](https://www.biglinux.com.br).

![O elenco: Minhoca, E.T. e Tux](docs/screenshots/cast.png)

| Painel | Personagens |
|---|---|
| ![Painel](docs/screenshots/dashboard.png) | ![Personagens](docs/screenshots/characters.png) |
| **Falando (o balão acompanha a voz)** | **Português, tema escuro** |
| ![Falando](docs/screenshots/speaking.png) | ![Painel em português](docs/screenshots/dashboard-pt-dark.png) |

---

## A história

### Uma live, um chat lotado e uma ideia

Quem acompanha o **Pedro Bezerra** no canal **InfoRecarga** sabe como é: live de tecnologia e
Linux, gente chegando de todo canto, o chat correndo mais rápido do que dá para ler. Pergunta
sobre driver, alguém dizendo que o Windows travou de novo, um "boa noite" de quem acabou de
entrar, piada interna, Super Chat… e um apresentador só para dar conta de tudo isso e ainda
tocar o conteúdo da live.

Foi daí que veio a ideia do Pedro: **e se a live tivesse um coapresentador?** Não um bot que
cola respostas prontas, mas um bichinho 3D na tela, com personalidade, que lê o chat,
responde com bom humor e **fala em voz alta**, como se fosse mais um participante do programa.

### O protótipo do Pedro (a "versão 1")

O Pedro não ficou só na ideia — foi para o código. O primeiro protótipo, guardado até hoje em
[`legacy/`](legacy/), era uma colagem engenhosa de peças:

- um script Python com `pytchat` lendo o chat da live do YouTube;
- a primeira personagem era uma **cobra 3D** em Three.js, feita de "gominhos" articulados, que
  depois virou uma **lagarta** — a avó direta da nossa Minhoca;
- a resposta vinha primeiro do **Gemini, na nuvem**; depois o Pedro testou o **Ollama local**
  com um modelo mais pesado e um **Qwen** mais leve, porque IA rodando na própria máquina
  significa não depender de chave, cota nem internet boa;
- um prompt de personalidade já com as regras de ouro do canal: respostas curtas, humor
  leve, foco em tecnologia e Linux e **nada de política, religião ou tema polêmico** — "aqui a
  gente só roda código limpo, política trava o sistema!";
- a resposta era gravada num arquivo de texto, uma página HTML aberta no OBS ficava
  consultando esse arquivo, mostrava um balão de quadrinho e falava com a voz do navegador;
- e ainda um script em Node.js para experimentar o mesmo truque no chat do Rumble.

Funcionava — e funcionava o bastante para provar que a ideia era boa. Mas era um protótipo de
verdade: vários scripts para rodar na mão, a voz às vezes saía duas vezes (uma do Python, outra
do navegador), a configuração ficava espalhada pelo código e o texto do chat chegava perto
demais do terminal.

### Entra o Rafael — e nasce o "ChatToon"

O Pedro mostrou o protótipo para o amigo **Rafael Ruscher**, também voluntário do BigLinux. O
Rafael olhou aquilo e viu na hora o potencial: um bichinho de desenho animado conversando com o
chat — um *cartoon* do *chat*. Daí o nome: **ChatToon**.

E veio a pergunta seguinte: *e se isso fosse um aplicativo de verdade, que qualquer pessoa que
faz live no BigLinux pudesse instalar e usar?* O BigLinux já tinha as duas peças mais difíceis
prontas:

- a **IA local** — o Ollama, que as Configurações do BigLinux já sabem instalar;
- o **TTS BigLinux** — o leitor de texto do sistema, com vozes naturais em português (Piper,
  RHVoice, espeak-ng) e todo o tratamento de números, abreviações e horários que um texto
  precisa para soar bem em voz alta.

Faltava juntar tudo num programa só, bonito, seguro e fácil de usar.

### Da ideia ao aplicativo (a versão 2.0.0)

A partir do protótipo do Pedro, o ChatToon foi reconstruído do zero, mantendo o espírito
original e resolvendo um por um os problemas encontrados (a auditoria está em
[docs/01-audit.md](docs/01-audit.md)):

- **um aplicativo de desktop** em PySide6/QML, com assistente de primeira execução, tema claro
  e escuro e interface traduzida para português;
- **três personagens 3D originais**, modelados por código: a **Minhoca** (herdeira da lagarta
  do Pedro), o **E.T.** e o **Tux**, com expressões, piscadas, olhar, gestos e boca que se
  mexe de acordo com o áudio real;
- **personalidade configurável**, com memória curta, consciência do horário, contexto do
  canal e as mesmas regras de conteúdo que o Pedro escreveu no primeiro prompt;
- **uma única voz por resposta**, sempre — o problema da voz duplicada deixou de existir por
  projeto;
- **segurança de verdade**: nada que vem do chat é executado, o overlay só escuta no próprio
  computador, e quem está no chat não consegue "reprogramar" o personagem.

O protótipo foi a versão 1. Este aplicativo é a **versão 2.0.0** — e o InfoRecarga é, com
orgulho, o canal onde tudo começou.

### Software livre, feito por voluntários

O ChatToon é software livre (GPL-3.0-or-later) e nasceu dentro da comunidade **BigLinux**, feito
por voluntários no tempo livre. Se você faz live, use, teste, abra *issues*, mande sugestões e
melhorias. É assim que o projeto cresce.

---

## Recursos

- **Três personagens 3D procedurais** (Three.js, sem downloads nem modelos de terceiros):
  **Minhoca**, uma minhoca atrevida saindo da terra, com pele articulada; **E.T.**, um alienígena
  que levita com antenas de mola; **Tux**, um pinguim geek com bico articulado. Expressões
  (feliz, rindo, surpreso, confuso, irritado, comemorando, pensando), piscadas, olhar, gestos e
  **sincronia labial pelo envelope de volume do áudio real**.
- **Motor de personalidade com IA local**: predefinições (Amigável, Comediante, Zoeiro,
  Geek, Caos controlado, Personalizado), nove ajustes de humor, contexto do canal, noção do
  horário real, memória de curto prazo, bordões e chamadas para ação ocasionais. As mensagens
  dos espectadores são tratadas como dados, **nunca como instruções**.
- **Chat ao vivo do YouTube** a partir do link colado (watch, live, youtu.be, live_chat,
  pop-out): sem login, sem chave de API, sem duplicatas (pelo id da mensagem), reconexão com
  espera progressiva e detecção de fim de transmissão.
- **Seleção de mensagens**: inteligente, todas, menções, perguntas, moderadores, membros,
  aleatória ou manual; intervalo por espectador, validade da mensagem, limite de fila, palavras
  bloqueadas e prioridade para Super Chat.
- **Três modos**: Demonstração (sem YouTube), Assistido (você aprova cada resposta) e
  Automático.
- **Uma voz por resposta, sempre**: vozes do TTS BigLinux (Piper, RHVoice, espeak-ng) geradas
  uma única vez e tocadas pelo aplicativo **ou** pela fonte do OBS — nunca pelos dois.
- **Overlay para o OBS** num endereço local secreto: fundo transparente ou chroma key, balão de
  fala, controles de tamanho, posição, câmera, luz, qualidade e FPS, com prévia ao vivo dentro do
  aplicativo.
- **Controles ao vivo**: iniciar, pausar, parar, interromper, silenciar, limpar fila, mandar o
  personagem dizer uma frase, disparar reações e um **botão de emergência** que cala tudo de uma
  vez.
- Tema claro/escuro/sistema, atalhos de teclado, assistente de primeira execução, interface em
  inglês com tradução completa para português do Brasil, perfis de transmissão (exportados sem
  segredos).

## Instalação (BigLinux / Manjaro / Arch)

```bash
git clone https://github.com/ruscher/ChatToon.git
cd ChatToon/packaging/arch
makepkg -si
```

Depois abra **ChatToon** pelo menu (ou rode `chattoon`). Para conferir a versão:
`chattoon --version` → `chattoon 2.0.0`. Para remover: `sudo pacman -R chattoon`.

| Tipo | Pacotes |
|---|---|
| Obrigatórios | `python`, `pyside6`, `python-aiohttp`, `qt6-svg`, `qt6-webengine` |
| Para compilar | `python-build`, `python-installer`, `python-setuptools`, `python-wheel`, `qt6-tools` |
| Opcionais | `tts-biglinux` (voz, repositório do BigLinux), `ollama` (IA — ou um Ollama em outra máquina da rede), `pipewire-audio` / `pulseaudio-utils` / `alsa-utils` (áudio no desktop), `obs-studio` |

O PKGBUILD compila a partir deste repositório (nada é baixado durante o build): gera a tradução
com `lrelease`, monta o *wheel* com `python -m build`, instala com `python -m installer` e
coloca o atalho `.desktop`, o ícone, este README e a licença do Three.js nos lugares certos.

Para rodar direto do código-fonte, sem instalar:

```bash
sudo pacman -S --needed pyside6 python-aiohttp qt6-svg qt6-webengine
python -m chattoon            # aplicativo
python -m chattoon doctor     # verifica Ollama, TTS BigLinux e áudio
python -m chattoon ask "Meu Windows travou!" --character tux
```

### IA local (Ollama)

O ChatToon usa o Ollama já instalado na máquina (as Configurações do BigLinux sabem instalar)
e **nunca altera a configuração dele**. Escolha qualquer modelo de conversa instalado na página
**Inteligência artificial**, ou baixe um dos sugeridos ali mesmo, com barra de progresso.
`gemma3:4b` (3,3 GB) é a sugestão padrão: bom português do Brasil, cerca de 20 tokens/s numa
GTX 1050 Ti. Detalhes de latência em [docs/04-ollama.md](docs/04-ollama.md).

### Voz (TTS BigLinux)

Instale o `tts-biglinux`. O ChatToon importa o catálogo de vozes, a normalização de texto e o
sintetizador nativo dele, então **toda voz que você instalou no TTS BigLinux aparece no
ChatToon**. Cada personagem pode ter sua própria voz, velocidade e tom (página **Voz**, com
botão de prévia). Detalhes em [docs/06-tts.md](docs/06-tts.md).

## Como usar

1. **Primeira execução**: o assistente verifica o Ollama e a voz e deixa você escolher o
   personagem.
2. **Experimente** no modo **Demonstração**: digite no Painel como se fosse alguém do chat.
3. Página **Chat do YouTube**: cole o link da live e escolha como as mensagens são selecionadas.
4. Página **Contexto da live**: canal, assunto, convidados, temas proibidos e chamadas
   para ação.
5. Página **OBS Studio**: copie o endereço do overlay → no OBS, adicione uma fonte
   **Navegador** com esse endereço, em 1920×1080. Se a voz deve sair pelo OBS, escolha
   *Dentro do OBS* na página Voz e ative *Control audio via OBS* nas propriedades da fonte no OBS.
6. Mude para **Assistido** ou **Automático** e aperte **Iniciar** (`Ctrl+Espaço`).

Atalhos: `Ctrl+Espaço` iniciar/pausar · `Ctrl+.` interromper · `Ctrl+M` silenciar ·
`Ctrl+Shift+X` ou `Pause` parada de emergência · `Ctrl+1…9` páginas.

## Detalhes técnicos

### Arquitetura

```
┌──────────────────────── processo do desktop ─────────────────────┐
│  thread principal do Qt             thread asyncio (core/runtime) │
│  ┌──────────────┐  slots/props   ┌─────────────────────────────┐ │
│  │ páginas QML  │◄──────────────►│ gui/backend.py (ponte)      │ │
│  │ (gui/qml)    │  sinais Qt em  │   ▲ EventBus (core/events)  │ │
│  └──────────────┘     fila       │   │                         │ │
│        │ prévia QtWebEngine      │ ChatToonEngine (core/engine)│ │
│        ▼                         │  ├ LiveChatClient (youtube) │ │
│  página do overlay (prévia)      │  ├ MessageSelector          │ │
│                                  │  ├ Brain (personalidade)    │ │
│                                  │  ├ OllamaClient ──► Ollama  │ │
│                                  │  ├ BigLinuxTTS ──► módulos do tts-biglinux
│                                  │  ├ AudioPlayer (pw-play…)   │ │
│                                  │  └ OverlayServer (aiohttp)  │ │
│                                  └──────────┬──────────────────┘ │
└─────────────────────────────────────────────┼────────────────────┘
              127.0.0.1:<porta>/o/<token>/ (HTTP + WebSocket, só eventos)
                                              ▼
                                Fonte Navegador do OBS
```

| Componente | Módulo |
|---|---|
| Controlador (máquina de estados `stopped/running/paused/emergency`, fases `idle/thinking/speaking`) | `chattoon/core/engine.py` |
| Configurações (dataclasses, leitura tolerante, gravação atômica com permissão 0600, perfis) | `chattoon/core/config.py` |
| Leitor do chat do YouTube | `chattoon/core/youtube_chat.py` |
| Fila e seleção de mensagens | `chattoon/core/messages.py` |
| Personalidade e personagens | `chattoon/core/brain.py`, `chattoon/core/characters.py` |
| Cliente do Ollama (streaming, *schema* JSON, *timeout*, cancelamento) | `chattoon/core/ollama.py` |
| Voz (TTS BigLinux, reprodução) | `chattoon/core/tts.py` |
| Servidor do overlay (aiohttp + WebSocket) | `chattoon/core/overlay_server.py` |
| Barramento de eventos | `chattoon/core/events.py` |
| Laço asyncio em thread própria | `chattoon/core/runtime.py` |
| Interface (PySide6 + QML) | `chattoon/gui/` |
| Animação dos personagens | `chattoon/web/overlay/rig.js`, `chattoon/web/overlay/characters/*.js` |
| Linha de comando (`gui`, `doctor`, `ask`, `--version`) | `chattoon/cli.py` |

### O caminho de uma mensagem

```
mensagem do chat
 → validação (limpeza, caracteres de controle/bidi, tamanho)
 → filtro (vazia, !comandos, palavras bloqueadas, duplicadas, repetidas, modo menções)
 → seleção (modo, pontuação, intervalo por espectador, validade)
 → contexto (prompt do sistema + memória + contexto da live)
 → Ollama (schema JSON, streaming, timeout, cancelamento)
 → validação da resposta (JSON, remove Markdown/emoji/URL, limite de frases e caracteres,
   checagem de temas proibidos, frase segura de reserva)
 → chamada para ação opcional
 → TTS (um único WAV + envelope de volume)
 → evento "falar" no overlay + reprodução em um único destino
 → histórico
```

Só uma resposta é processada por vez, então as falas nunca se atropelam e as gerações nunca
disputam a GPU. Trabalho bloqueante (síntese de voz, espera do player de áudio) vai para
`asyncio.to_thread`; a interface conversa com o motor por `run_coroutine_threadsafe` e recebe os
eventos por sinais Qt em fila, por isso **nunca trava** esperando a rede, o modelo ou a voz.

### Voz e sincronia labial

1. Lista as vozes de todos os motores prontos do TTS BigLinux; cada personagem recebe a voz
   escolhida ou a mais adequada (ex.: Minhoca → Letícia/RHVoice), com a voz padrão do TTS
   BigLinux como reserva.
2. Normaliza o texto com o `process_text` do TTS BigLinux (emoji removido antes, URLs não são
   lidas).
3. Gera **um WAV**: Piper e espeak-ng pelo módulo nativo `tts_engine`, RHVoice pelo
   `RHVoice-test`; o texto sempre vai por *stdin*, nunca por um shell.
4. Calcula o envelope de volume (RMS, 50 por segundo, normalizado no percentil 95) que move a
   boca do personagem.
5. Toca **uma vez**: pelo `pw-play`/`paplay`/`aplay` no desktop **ou** dentro da fonte do OBS.

| Voz | Duração do áudio | Tempo de síntese |
|---|---|---|
| Letícia (RHVoice) | 3,1 s | 0,49 s |
| Faber (Piper, medium) | 1,9 s | 1,6 s a frio, 0,07 s aquecido |
| espeak-ng pt-br | 2,4 s | 0,01 s |

### Segurança e privacidade

- **Nada do chat é executado**: não há shell em lugar nenhum; o texto chega à voz por *stdin*.
- **Ninguém do chat reprograma o personagem**: as mensagens vão num bloco de dados delimitado e
  escapado, as regras proíbem seguir instruções embutidas e a resposta é validada.
- **A saída da IA nunca é executada**: é só texto e uma emoção de uma lista fixa.
- **Overlay protegido**: escuta só em `127.0.0.1`, exige um token secreto no endereço, recusa
  `Host` que não seja local (contra *DNS rebinding*), usa CSP `default-src 'self'` e ignora
  qualquer comando vindo pelo WebSocket.
- **Limites**: 300 caracteres por mensagem, quadros WebSocket de 4 KB, requisições de 64 KB e
  *timeouts* em tudo que é rede.
- **Permissões mínimas**: roda como usuário comum, nunca pede root; configurações com permissão
  0600, áudios temporários em pasta 0700.
- **Sem telemetria**: as únicas conexões externas são o chat do YouTube e o Ollama configurado.

Mais em [docs/09-security.md](docs/09-security.md).

### Onde ficam os dados

| Caminho | Conteúdo |
|---|---|
| `~/.config/chattoon/settings.json` | configurações (permissão 0600) |
| `~/.config/chattoon/profiles/*.json` | perfis de transmissão salvos (sem segredos) |
| `$TMPDIR/chattoon-tts-*/` | últimas 20 respostas geradas (0700), apagadas ao sair |

### Desempenho medido

- Latência por resposta com `gemma3:4b` numa GTX 1050 Ti: ~8–9 s, estável ao longo da live.
  Síntese de voz: 0,1–0,5 s.
- Memória do motor após 800 mensagens pelo caminho completo: **+3 KB** nas últimas 400.
- Overlay após 400 falas e 57 trocas de personagem: geometrias e texturas de volta ao ponto de
  partida.

### Testes

```bash
sudo pacman -S --needed python-pytest
python -m pytest
```

São mais de 100 casos de teste cobrindo motor, seleção de mensagens, configurações, Ollama, personalidade, TTS,
overlay, chat do YouTube, tradução, interface e empacotamento (incluindo a checagem de que o
`pkgver` do PKGBUILD é igual à versão do projeto).

## Solução de problemas

| Problema | O que fazer |
|---|---|
| Ollama "Parado" | `sudo systemctl start ollama` (ou instale nas Configurações do BigLinux) e clique em *Verificar de novo* |
| Nenhum modelo | Baixe um modelo sugerido na página de IA |
| Voz "Indisponível" | `sudo pacman -S tts-biglinux` |
| Chat "indisponível"/"desativado" | A live não está no ar, o chat está desligado ou é só para membros; a mensagem diz qual |
| OBS não mostra nada | O aplicativo precisa estar aberto; confira o endereço; deixe *Shutdown source when not visible* desmarcado na fonte do OBS |
| Voz duas vezes | Não acontece por projeto; se ouvir eco, o OBS está capturando o *Áudio do desktop* **e** a fonte |
| Respostas lentas | Diminua a *Memória da conversa*, use um modelo menor, deixe só um modelo carregado |

## Limitações conhecidas e próximos passos

- A fala começa depois que a resposta inteira é gerada (ainda sem *streaming* por frase).
- Vozes Kokoro aparecem no TTS BigLinux mas ainda não são sintetizadas pelo ChatToon.
- A fonte do OBS é adicionada à mão (com passo a passo no aplicativo); sem obs-websocket ainda.
- A boca acompanha o volume, não os fonemas.
- Conectores para Twitch e Rumble ainda não existem — a interface de conector já está pronta
  (`ChatMessage` tem o campo `platform`), retomando a ideia do script de Rumble do protótipo.

Lista completa em [docs/11-release.md](docs/11-release.md).

## Documentação

[Auditoria](docs/01-audit.md) · [Arquitetura](docs/02-architecture.md) · [UI/UX](docs/03-ui-ux.md) ·
[Ollama](docs/04-ollama.md) · [YouTube](docs/05-youtube.md) · [TTS](docs/06-tts.md) ·
[Avatares](docs/07-avatars.md) · [OBS](docs/08-obs.md) · [Segurança](docs/09-security.md) ·
[Testes](docs/10-testing.md) · [Lançamento](docs/11-release.md)

## Histórico de versões

- **2.0.0** — o aplicativo ChatToon: interface desktop PySide6/QML, três personagens 3D,
  IA local (Ollama), voz do TTS BigLinux, overlay seguro para o OBS, tradução pt-BR e pacote
  para Arch/BigLinux.
- **1.x** — o protótipo original do Pedro Bezerra (InfoRecarga): scripts em Python e Node.js com
  a cobra/lagarta 3D, preservados em [`legacy/`](legacy/) como registro histórico.

## Autoria, licença e créditos

- **Autor e criador da ideia:** Pedro Bezerra, do canal
  [InfoRecarga](https://www.youtube.com/@pedro_bezerra).
- **Colaborador:** Rafael Ruscher, que batizou o projeto de ChatToon e o transformou em
  aplicativo.
- Feito por voluntários do projeto [BigLinux](https://www.biglinux.com.br).

O ChatToon é licenciado sob a **GPL-3.0-or-later**.

- [Three.js](https://threejs.org) 0.186.1 — MIT, incluído em `chattoon/web/vendor/three`.
- Ícones da interface no estilo [Lucide](https://lucide.dev) — ISC.
- O pinguim é um modelo procedural original inspirado no **Tux**, criado por Larry Ewing
  (lewing@isc.tamu.edu) com o GIMP.
- Vozes e tratamento de texto pelo [TTS BigLinux](https://github.com/biglinux/tts-biglinux);
  IA pelo [Ollama](https://ollama.com).
