# 38 — Testes e validação

## Suíte automática

`python -m pytest -q` — antes: 450 passaram, 6 pulados. Depois: **548 testes, todos passando
exceto os mesmos 6 pulados** (exigem `--run-live`: Ollama/TTS/YouTube reais). Lint:
`ruff check chattoon tests` limpo (o único aviso do repositório, `tools/render_thumbnails.py`, já
existia). Catálogo pt-BR completo (`tests/test_i18n.py`).

Arquivos novos: `test_system_network.py` (27), `test_ollama_management.py` (20),
`test_tts_manager.py` (5), `test_overlay_network.py` (7), `test_remote_privacy.py` (26),
`test_character_window.py` (7). Dois testes antigos tiveram a expectativa ajustada por mudança
intencional: contagem de clientes agora inclui `browser`/`desktop`; o relatório de início sintetiza
um "Oi!" silencioso para provar a voz.

## Matriz de validação

Legenda: **A** = teste automático · **V** = executado ao vivo neste computador (KDE Plasma 6
Wayland, 3 monitores, perfil isolado em `XDG_*` temporário) · **—** = não executado (motivo).

| Área | Cenário | Resultado |
|---|---|---|
| Janela | KDE Plasma Wayland | **V** transparente, sem moldura, acima das janelas, KWin detectado, geometria salva |
| Janela | Sessão X11 | — sem sessão X11 disponível; caminho por flags Qt, sem captura |
| Janela | Troca de personagem | **A** título/ícone atualizados · **V** menu com os seis |
| Janela | Fechar e reabrir | **A** `window_open` persistido, app continua |
| Janela | Múltiplos monitores | **V** telas listadas (HDMI-A-1, DP-1, DP-2); posição por tela salva (`DP-1`) |
| Janela | Ícone e identificação | **A** ícone não nulo, título "Tux — ChatToon" · **V** a barra do Plasma agrupa e mostra o ícone do ChatToon (limitação documentada) |
| Janela | Balão de fala | **V** opaco e legível após correção do `will-change` |
| Janela | Clique através | **A/V** flag aplicada e janela visível; passagem do clique não automatizada |
| Ollama | Não instalado | **A** · **V** estado real deste computador |
| Ollama | Instalado e parado | **A** (comandos simulados) |
| Ollama | Serviço funcionando | **A** (API simulada + unidade ativa) |
| Ollama | Servidor remoto | **A** usado, nunca controlado |
| Ollama | Instalar | **V** diálogo com tamanhos reais do pacman · — instalação real (exige senha do administrador) |
| Modelos | Vários instalados / importado / personalizado / incompatível | **A** 9 tipos de modelo |
| Modelos | Download e seleção | **A** seleção, recusa de incompatível, nome validado, tamanho do manifest · — download real (Ollama ausente) |
| TTS | Mecanismo ausente / sem voz / voz de outro idioma | **A** |
| TTS | Estados reais | **V** Piper, Kokoro, RHVoice, espeak-ng prontos, com vozes pt-BR contadas |
| TTS | Instalação e teste de voz | **A** plano e instalação simulados · — instalação real (senha) |
| OBS | Mesmo computador | **A** · **V** endereço com a porta real e token mascarado |
| OBS | Outro computador na LAN | **A** listener, Host, sub-rede, token · — OBS real em outro computador |
| OBS | Overlay e janela juntos | **A** desktop não recebe áudio, OBS recebe uma vez |
| Rede | Porta padrão ocupada | **A** · **V** 8765 ocupada → 8766 mostrada |
| Remoto | Domínio HTTPS válido | **A** HTTPS real local com CA descartável, até o WebSocket |
| Remoto | Domínio inválido / DNS / certificado / proxy / token / Host | **A** |
| Remoto | CGNAT e porta indisponível | **A** porta recusada, classificação CGNAT · — rede real com CGNAT |
| Privacidade | IP público oculto | **A** · **V** mascarado na interface |
| Privacidade | Tokens ocultos | **A** toasts/relatório · **V** `/o/••••••/` |
| Início | Tudo pronto | **A** |
| Início | Configuração incompleta | **A** · **V** bloqueado com "O Ollama não está instalado" |
| UX | Tema claro e escuro | **A** contraste WCAG · **V** capturas nos dois temas |
| UX | Janela pequena e grande | **V** 1020×660 (mínimo) e 1360×880 |
| UX | Navegação por teclado | **A** parcial (atalhos e foco existentes); revisão manual dos novos componentes, sem leitor de tela |
| Compatibilidade | Perfis/configurações da 2.3 | **A** |

## Como verificar o que não foi executado

* **Instalar o Ollama**: Inteligência artificial → Instalar Ollama → Vulkan → senha. Depois:
  "Instalado e parado" → Iniciar → "Em execução"; os modelos que estavam em `/var/lib/ollama`
  (por exemplo `qwen3.5:2b`) devem aparecer no catálogo.
* **LAN**: Onde mostrar → Outro computador na mesma rede → Permitir → Liberar só a minha rede →
  abrir o endereço no navegador do outro computador.
* **X11**: entrar numa sessão Plasma X11 e repetir o modo Janela (manter acima, posição lembrada
  ao reabrir).
* **Internet**: assistente, etapa 5, com o domínio real; confirmar pelo celular nos dados móveis.
