# 29 — Modernização: auditoria, arquitetura e plano

Ponto de partida: ChatToon **2.3.0** (`pyproject.toml`, `PKGBUILD`), branch `main` em `fdb7a4f`.
A versão **não** foi alterada neste trabalho; as notas estão em [39-release-notes.md](39-release-notes.md).

## Auditoria (fase 1)

| Área | Situação encontrada | Problema real |
|---|---|---|
| Exibição | Só o overlay do OBS (fonte Navegador) e a prévia no app | Não havia personagem no desktop |
| Ollama | `check_services` chamava `/api/tags` e mostrava nomes num `AppCombo` | Ver [31](31-ollama-management.md): troca silenciosa do modelo, lista suspensa sem rolagem, instâncias diferentes do Ollama, modelos de embedding escondidos sem aviso |
| Serviço Ollama | Só um texto: `sudo systemctl start ollama` | Sem instalação, controle ou distinção entre "não instalado" e "parado" |
| Voz | Chips "pronto / não instalado" por mecanismo | Sem instalação, sem distinguir "sem voz no idioma", texto `sudo pacman -S tts-biglinux` |
| OBS / rede | Servidor só em `127.0.0.1`; campo "acesso de outro computador" | Colar o IP da LAN no campo não funciona (o servidor não escuta na rede) |
| Acesso externo | Campo de endereço público + `docs/21` | Sem teste real; IP público aparecia em instruções; nada mascarado |
| Iniciar | `engine.start()` direto | Nenhum resumo; falhas viravam só toasts |
| UX | 11 páginas sempre visíveis | Sem modo simples/avançado; assistente com 4 passos sem ações |

Ambiente de validação: BigLinux (Manjaro), KDE Plasma 6 em **Wayland**, 3 monitores (HDMI-A-1,
DP-1, DP-2), Ryzen 7 5700G + Radeon RX 9060 XT 16 GB, PySide6 6.11.2, TTS BigLinux 4.1.0 com
Piper, Kokoro, RHVoice e espeak-ng, **Ollama não instalado** (modelos antigos em `/var/lib/ollama`),
`ufw` ativo, Docker, ZeroTier e Tailscale com interfaces próprias.

## Arquitetura

Princípio: **nada novo roda na thread da interface**. Todo trabalho usa o loop asyncio do
engine (`core/runtime.py`) e volta à GUI por sinal. Cada recurso novo é um *controlador*
(QObject) pendurado no `Backend` e acessado do QML como `backend.<nome>`:

```
QML  ──>  backend.aiCenter        gui/ai_center.py        ──> core/ollama_service.py, core/ollama.py, core/hardware.py
          backend.voiceCenter     gui/voice_center.py     ──> core/tts_manager.py (módulos do TTS BigLinux)
          backend.connectivity    gui/connectivity.py     ──> core/network.py, core/remote_check.py, core/overlay_server.py
          backend.sessionReport   gui/session_report.py   ──> core/readiness.py, engine.verify()
          backend.characterWindow gui/character_window.py ──> gui/kwin.py (KWin via D-Bus), qml/CharacterWindow.qml
                                  gui/controller.py        (base comum: submit() no loop, later() de volta à GUI)
```

Módulos de núcleo sem Qt (testáveis isoladamente): `core/system.py` (comandos, pacman,
systemd), `core/network.py`, `core/hardware.py`, `core/ollama_service.py`, `core/tts_manager.py`,
`core/remote_check.py`, `core/privacy.py`, `core/readiness.py`.

## Decisões principais

1. **Janela flutuante nativa (Qt), sem Electron.** Um protótipo provou transparência real do
   QtWebEngine numa `Window` sem moldura no KWin Wayland. Electron traria um segundo runtime
   Chromium (~200 MB) e um segundo processo para a mesma página. Ver [30](30-wayland-floating-window.md).
2. **KWin scripting por D-Bus** para manter acima, posicionar e ler a geometria no Wayland,
   com detecção de capacidade e alternativa por flags Qt no X11.
3. **Reuso do TTS BigLinux**: `voice_manager`, `package_installer` e `kokoro_voice_service`.
   O ChatToon só instala o próprio `tts-biglinux` quando ele falta.
4. **Rede local opcional e restrita**: um segundo listener num único IPv4 privado, nunca `0.0.0.0`,
   aceitando só clientes da mesma sub-rede e com o mesmo token.
5. **Privacidade por padrão**: token e IP público sempre mascarados; "Modo Privacidade para
   Lives" (ligado por padrão) mascara também IPs locais, domínios e logins.
6. **Iniciar passa pelo relatório**: requisitos essenciais (IA + plataforma fora do modo
   demonstração) bloqueiam; voz e exibição são avisos.

## Ordem executada

Fases 1–10 do pedido, nesta ordem, cada uma com testes antes da seguinte. Os documentos 30–38
registram cada fase e o [38](38-testing-validation.md) registra o que foi e o que **não** foi
executado ao vivo.
