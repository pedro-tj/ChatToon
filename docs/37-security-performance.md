# 37 — Segurança e desempenho

## Superfícies novas e como foram fechadas

| Superfície | Risco | Controle |
|---|---|---|
| Listener da rede local | Overlay alcançável por outros | Desligado por padrão; consentimento; um IPv4 privado (nunca `0.0.0.0`); Host = esse IP; cliente da mesma sub-rede; token; firewall só para a sub-rede |
| Token na URL | Credencial exposta | Mascarado sempre; copiar avisa; filtro de logs; "Novo endereço secreto" revoga todos os links |
| IP público | Vazamento na live | Consulta só com consentimento; só memória; mascarado; revelar por 15 s com aviso; filtro de logs |
| Teste remoto (`probe`) | Roubar o áudio / ser contado como OBS | Papel próprio: recebe `hello` e é fechado; nunca vira `obs` |
| Janela do desktop | Controlar o app pela página | Papel `desktop` só assiste; o WebSocket continua sem autoridade |
| Ponte KWin (D-Bus) | Qualquer processo da sessão pode chamar o método | Aceita só números finitos e pequenos, nome de tela curto; só altera a posição salva |
| Script KWin | Injeção pelo título | Título, estado e serviço entram como JSON; arquivo `mkstemp` 0600 no `XDG_RUNTIME_DIR`, removido ao descarregar |
| Instalação de pacotes | Root silencioso, partial upgrade | Confirmação com lista e tamanhos; `pkexec pacman -S --needed --noconfirm -- …` (nunca `-Sy`); nomes validados por regex; lista permitida (Ollama: `ollama` + aceleração; TTS: pacotes do mecanismo) |
| systemd | Ações arbitrárias | Só `ollama.service`, só start/stop/restart/enable/disable; o systemd pede a senha ao polkit |
| `ollama serve` iniciado pelo ChatToon | Ollama exposto na rede | Sempre `OLLAMA_HOST=127.0.0.1:<porta>`; se o host configurado for um IP de rede, recusa (`not-loopback`); encerrado com o ChatToon |
| Ollama remoto | Controlar outra máquina | Estado `remote`: só a API, nunca systemd |
| Download de modelo | Texto colado virar caminho | `valid_model_name()` antes de qualquer requisição |
| Firewall | Mudança sem permissão | Comando exibido; `pkexec` só após confirmação; regra limitada à sub-rede e removível |
| Abrir Pamac / TTS BigLinux | Comando injetado | argv fixo, nome de pacote validado, `start_new_session` |

Inalterado e reconferido: nenhum `shell=True`/`os.system` (teste `test_no_secrets_or_shell_in_code`),
conteúdo do chat nunca vira comando, perfis não exportam token nem os dados da rede local deste
computador, `settings.json` gravado 0600, sem telemetria. Chamadas externas novas — todas só por
ação explícita: `api.ipify.org` (IP público), `registry.ollama.ai` (tamanho exato antes de baixar
do mesmo registro), o próprio domínio do usuário (teste remoto) e os repositórios do sistema.

## Desempenho

* Nada novo bloqueia a GUI: comandos (`pacman`, `systemctl`, `ip`), descoberta de vozes e testes
  de rede rodam no loop do engine ou em `asyncio.to_thread`.
* Catálogo de modelos: um `/api/tags` + até 4 `/api/show` em paralelo, só ao verificar serviços
  (abrir a página, botão, após download) — sem polling.
* Download: no máximo ~7 atualizações por segundo chegam à interface.
* Estados dos mecanismos de voz e lista de vozes saem de **uma** descoberta (antes: só a lista).
* Janela do desktop: reutiliza a página e o WebSocket existentes; não gera resposta nem síntese a
  mais e não cria outro processo do ChatToon (o QtWebEngine usa os mesmos processos auxiliares da
  prévia). É um renderizador WebGL a mais **só depois de aberta pela primeira vez**; ocultada, a
  janela é escondida (não destruída) e o overlay deixa de desenhar quando o Chromium marca a página
  como `document.hidden`. Consumo de CPU/GPU da janela aberta **não foi medido** nesta entrega;
  o limite de FPS e a qualidade do OBS valem também para ela.
* Verificação do relatório: um `preload` (o mesmo que o aquecimento já fazia) e uma síntese de
  "Oi!" descartada.

## Riscos restantes

* O listener LAN usa a mesma porta do loopback; se outro programa ocupar essa porta só no IP da
  LAN, o modo rede local informa "porta em uso".
* Revelar mostra o valor real por 15 s; a responsabilidade de não fazê-lo ao vivo é do usuário
  (o aviso diz isso).
* O teste remoto contacta o domínio informado com o token na URL, por HTTPS verificado.
