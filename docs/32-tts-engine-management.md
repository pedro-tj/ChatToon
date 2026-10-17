# 32 — Voz: mecanismos e vozes do TTS BigLinux

## Problema

A página só mostrava "pronto" ou "não instalado" por mecanismo e, sem o TTS BigLinux, um comando
de terminal. "Instalado" e "tem uma voz no idioma da live" eram confundidos.

## Solução (reuso, sem gerenciador duplicado)

`core/tts_manager.py` usa os módulos do próprio TTS BigLinux, já carregados pelo adaptador
`BigLinuxTTS`:

| Necessidade | Módulo do TTS BigLinux |
|---|---|
| Programa instalado? Tem vozes? | `voice_manager.discover_voices()` + `engine_availability()` |
| Pacotes, grafias (`piper-voices-pt-br` / `-pt-BR`), AUR | `package_installer.resolve/query/install/install_aur` |
| Vozes Kokoro (download do Hugging Face para o `voices.bin`) | `kokoro_voice_service.get_voice_status/download_voice` |

O ChatToon só instala o próprio `tts-biglinux` quando ele falta (`core/system.py`, mesmas regras:
`pkexec pacman -S --needed`).

Estados: **Não instalado** · **Precisa de voz** (programa sem voz, ou só vozes de outro idioma) ·
**Pronto para usar** · **Erro** · **Precisa do TTS BigLinux**. "Em uso" destaca o mecanismo da
voz que o personagem realmente usa.

Pacotes por mecanismo (nomes confirmados no `pacman -Si` do BigLinux):
Piper `piper-tts-bin` + `piper-voices-pt-BR` (pt), `-en-US`, `-es-ES`; Kokoro
`biglinux-kokoro-tts`; RHVoice `rhvoice` + `rhvoice-voice-leticia-f123` (pt) / `-clb` (en);
espeak-ng `espeak-ng`.

Ações contextuais: **Instalar mecanismo**, **Baixar voz** (Piper/RHVoice por pacote, Kokoro pela
lista de vozes com progresso e cancelamento), **Testar voz**, **Mais vozes**, **Gerenciar vozes no
TTS BigLinux** (abre `biglinux-tts`, que tem o gerenciador completo). A confirmação lista cada
pacote, de onde vem (repositório / AUR / já instalado) e o tamanho.

"Voz do <personagem>": mecanismo + voz que será usada, **Pronta para falar** / sem voz / mudo,
**Ouvir demonstração**, velocidade, tom (desabilitado onde não existe, ex. Kokoro), volume e
**Restaurar padrões**. Se a voz escolhida foi desinstalada, avisa que a automática está em uso.

A proteção contra reprodução dupla não mudou (`engine._play`, `docs/12`).

## Testes

`tests/test_tts_manager.py` (TTS BigLinux falso: mecanismo ausente, sem voz, só voz em inglês,
TTS BigLinux ausente, plano com grafias e AUR, recusa de pacotes fora do mecanismo).
Ao vivo neste computador: os quatro mecanismos detectados como prontos, com contagem de vozes
pt-BR (Piper 4, Kokoro 3, RHVoice 1, espeak-ng 2). **Não executado:** instalação real de pacotes
(pede senha) e download de voz Kokoro (rede + escrita no `voices.bin` do usuário).
