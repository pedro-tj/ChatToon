# 31 — Ollama: instalação, serviço e modelos

## Por que "alguns modelos não aparecem em Modelo em uso"

A investigação encontrou **cinco** causas independentes, todas corrigidas:

| Causa | Efeito | Correção |
|---|---|---|
| A lista suspensa (`AppCombo`) tinha altura máxima de 300 px, **sem barra de rolagem** e sem `margins` | Com mais de ~9 modelos, ou com a lista perto da borda da janela, itens ficavam cortados sem nenhuma indicação | A escolha agora é um catálogo de cartões; o `AppCombo` ganhou rolagem e fica dentro da janela |
| `_autoselect` trocava o modelo quando o salvo não estava na lista | Uma escolha válida do usuário era substituída em silêncio (ex.: Ollama de outro computador momentaneamente fora) | Só escolhe sozinho quando **nenhum** modelo foi escolhido; se o escolhido sumir, avisa e o relatório de início bloqueia |
| Modelos com "embed" no nome eram descartados sem explicação | Pareciam "não instalados" | O catálogo lista **todos** e explica por que não conversam |
| Várias instâncias do Ollama com pastas de modelos diferentes | `ollama list` no terminal (ou o Alpaca) mostra modelos que o ChatToon não vê: o serviço do sistema usa `/var/lib/ollama`, um `ollama serve` manual usa `~/.ollama`, o Alpaca (Flatpak) roda outro Ollama na porta 11435 | O painel detecta outros Ollama nas portas conhecidas e oferece "Usar este" |
| Capacidades não consultadas | Modelos importados/personalizados, multimodais ou de nuvem não eram classificados | `/api/show` de cada modelo (até 4 em paralelo): `completion`, `vision`, `tools`, `thinking`, `embedding`; contexto; versões antigas sem capacidades → estimativa marcada |

## Arquivos

* `core/ollama.py` — `catalog()`, `show()`, `running()` (`/api/ps`), `registry_size()`,
  `valid_model_name()`, `SUGGESTED`, eventos de `pull` com `digest`.
* `core/ollama_service.py` — `OllamaService`: fatos (binário, pacote, aceleração, unidade do
  sistema e do usuário), `status()`, `start/stop/restart/set_enabled`, `install`, outras instâncias.
* `core/system.py` — pacman (`-Q`, `-Si`, `pkexec pacman -S --needed`), systemd, distribuição.
* `core/hardware.py` — CPU, RAM, GPU/VRAM por `/proc` e `/sys` (sem comandos).
* `gui/ai_center.py`, `qml/OllamaPanel.qml`, `qml/ModelCatalog.qml`, `qml/ModelSuggestions.qml`.

## Estados do Ollama

`not_installed` (sem binário **e** sem pacote) · `stopped` (instalado, API não responde) ·
`starting` (após iniciar, até 40 s esperando a API) · `running` (a API respondeu de verdade) ·
`error` (a unidade systemd está `failed`) · `remote` (o host configurado não é deste computador —
só a API é usada, nunca o systemd). Uma falha de conexão sozinha **nunca** vira "não instalado".

Quem gerencia: `system` (ollama.service), `user` (unidade de usuário), `chattoon` (`ollama serve`
iniciado pelo ChatToon, só em 127.0.0.1, encerrado junto com o app) ou `external` (aberto por
outro programa: não é parado pelo ChatToon).

## Instalação

No BigLinux/Manjaro/Arch o pacote `ollama` do repositório `extra` é a base; a aceleração por GPU
é um pacote complementar que depende dele (`ollama-vulkan`, `ollama-cuda`, `ollama-rocm`).
O diálogo mostra versão, repositório e **tamanhos reais do `pacman -Si`**, e recomenda pela GPU
detectada (NVIDIA → CUDA; AMD/Intel → Vulkan, 7 MB; ROCm fica como escolha manual, ~1 GB).
Executa `pkexec env LC_ALL=C pacman -S --noconfirm --needed -- <pacotes>` (nunca `-Sy`), com
progresso pelas etapas `(n/m)` do pacman e erros explicados (senha cancelada, pacote ausente,
banco travado, rede, conflito, disco). Em outras distribuições: orientação + "Abrir na central de
programas" (Pamac no BigLinux, `pamac-manager --details=ollama`).

Iniciar/parar/ativar usa `systemctl [--user] start|stop|restart|enable|disable ollama.service`;
para a unidade do sistema o próprio systemd pede a senha ao polkit (diálogo do KDE). Sem unidade,
o ChatToon roda `ollama serve` com `OLLAMA_HOST=127.0.0.1:<porta>`. Parar durante uma resposta pede
confirmação.

## Modelos

Catálogo com: nome, tamanho, família, parâmetros, quantização, contexto, capacidades e estados
separados — **Em uso** (borda verde + ✓), **Instalado**, **carregado na memória** (`/api/ps`),
**na nuvem**. Os que não conversam aparecem em "Instalados, mas não respondem ao chat" com o
motivo (embedding, sem geração, ilegível + erro).

Sugestões: tamanho aproximado medido nos manifests do registro (2026-10-17), características,
idiomas, e um indicativo de encaixe no hardware ("Cabe na sua placa de vídeo"…), sem bloquear
nada. "Baixar e instalar" lê o **tamanho exato** do manifest antes de confirmar. Download com
porcentagem, bytes, velocidade (média móvel), estado (Preparando / Baixando / Conferindo /
Finalizando) e **Cancelar** (o Ollama guarda as partes para retomar). No modo avançado, qualquer
modelo pode ser baixado pelo nome (validado antes de virar requisição).

## Testes

`tests/test_ollama_management.py` (servidor Ollama falso com 9 modelos, incluindo namespace,
Hugging Face, personalizado, multimodal, nuvem, embedding, ilegível e versão antiga; estados do
serviço; iniciar/parar; instalação; seleção e não substituição) e `tests/test_system_network.py`.
Ao vivo: estado "Não instalado" e o diálogo de instalação com tamanhos reais verificados neste
computador. **Não executado:** a instalação real (pede a senha de administrador) e o controle de um
`ollama.service` ativo — ver [38](38-testing-validation.md).
