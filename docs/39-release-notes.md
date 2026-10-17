# 39 — Notas técnicas da entrega (modernização)

Base: 2.3.0. A versão do pacote **não foi alterada** (sugestão: 2.4.0 ao publicar). Nada foi
publicado, enviado ao remoto ou empacotado como release.

## Funcionalidades

* **Onde mostrar**: OBS Studio, janela no computador ou os dois, persistido. Janela transparente
  sem moldura, só personagem e balão, arrastar, redimensionar (alça, Ctrl+rolagem, P/M/G),
  manter acima, travar, clique através, ocultar da barra de tarefas, mover de tela, posição
  lembrada (KWin), ícone do personagem, menu contextual, sincronia total com o OBS, voz uma vez só.
* **Ollama sem terminal**: detecção real (não instalado / parado / iniciando / rodando / erro /
  remoto), instalação pelos repositórios com aceleração recomendada, iniciar/parar/reiniciar,
  iniciar com o computador, outras instâncias encontradas.
* **Modelos**: catálogo completo com capacidades e motivos, Em uso / Instalado / Carregado na
  memória separados, nunca troca silenciosa, sugestões com tamanho e encaixe no hardware, download
  com progresso, velocidade e cancelamento.
* **Voz**: estados reais por mecanismo, instalar mecanismo/voz pelo TTS BigLinux, vozes Kokoro,
  "Voz do personagem" com demonstração e restaurar padrões.
* **OBS na rede local** (real, opcional, restrito à sub-rede) com firewall e teste; **novo endereço
  secreto**.
* **Internet**: assistente em 5 etapas com diagnóstico real até o WebSocket.
* **Privacidade**: token e IP público sempre ocultos; Modo Privacidade para Lives; revelar por 15 s.
* **Iniciar com relatório**: bloqueia só pelo essencial, comprova IA e voz, mostra o que o
  personagem vai fazer; Saúde do sistema no Painel.
* **UX**: modo simples/avançado, assistente de 6 etapas, restaurar padrões por seção, novos
  componentes acessíveis, ~460 strings traduzidas.

## Arquivos

Novos (núcleo): `core/system.py`, `core/hardware.py`, `core/network.py`, `core/ollama_service.py`,
`core/tts_manager.py`, `core/remote_check.py`, `core/privacy.py`, `core/readiness.py`.
Novos (GUI): `gui/controller.py`, `gui/ai_center.py`, `gui/voice_center.py`, `gui/connectivity.py`,
`gui/session_report.py`, `gui/character_window.py`, `gui/kwin.py`; QML `CharacterWindow`,
`CharacterWindowCard`, `ChoiceCard`, `ConfirmDialog`, `DisplayModePicker`, `EngineCards`,
`ModelCatalog`, `ModelSuggestions`, `ObsAccess`, `OllamaPanel`, `Privacy` (singleton),
`RemoteWizard`, `SecretField`, `StartReport`, `StateChip`, `Steps`.
Alterados: `core/config.py`, `core/ollama.py`, `core/engine.py`, `core/overlay_server.py`,
`gui/app.py`, `gui/backend.py`, `gui/icons.py`, `qml/Main.qml`, `AppCombo`, `Section`, `Status`,
`FirstRunWizard`, `qml/qmldir`, páginas `AiPage`, `VoicePage`, `ObsPage`, `DashboardPage`,
`SettingsPage`, `PlatformsPage`, `web/overlay/overlay.js`, `overlay.css`, `i18n/*`,
`tools/update_translations.py`, `tools/translations_pt_BR.py`, `tests/test_gui.py`,
`tests/test_tts_overlay.py` (expectativas atualizadas por mudança intencional).
Testes novos: `test_system_network.py`, `test_ollama_management.py`, `test_tts_manager.py`,
`test_overlay_network.py`, `test_remote_privacy.py`, `test_character_window.py`.

## Dependências

Nenhuma nova obrigatória. Usados se presentes: `pkexec` (polkit), `systemctl`, `ip` (iproute2),
KWin (D-Bus), `ufw`/`firewalld`, `caddy`/`nginx`/`cloudflared`/`tailscale` (só detectados),
`pamac-manager`, `biglinux-tts`. `PySide6.QtDBus` faz parte do PySide6 já exigido. O `PKGBUILD`
não precisou mudar.

## Compatibilidade

Configurações e perfis da 2.3 carregam sem perda (teste dedicado); recursos novos começam
desligados (exibição = OBS, rede local desligada), exceto o Modo Privacidade (ligado). Perfis
exportados não levam token nem dados da rede local deste computador.
