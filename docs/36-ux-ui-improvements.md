# 36 — Interface: simplicidade, assistente e acessibilidade

## Modo simples e avançado

`Settings.advanced` (desligado por padrão). **Simples** — menu: Painel, Personagens, Inteligência
artificial, Voz, Plataformas, Onde mostrar, Chat ao vivo, Configurações. **Avançado** acrescenta
Personalidade, Contexto da live e Histórico, e nas páginas: endereço do servidor Ollama, geração,
qualidade das respostas, diagnóstico, baixar qualquer modelo pelo nome, rotação/zoom/luz/qualidade
/FPS do OBS, "novo endereço secreto", interfaces de rede não domésticas. Nada foi removido.
Ctrl+1…9 segue o menu visível; as setas no menu abrem a página.

## Assistente de primeira execução (6 etapas)

Boas-vindas → Personagem → **IA** (painel do Ollama com instalar/iniciar, modelos e 3 sugestões)
→ **Voz** (mecanismos com instalar/testar, voz que será usada + ouvir) → **Onde mostrar** →
Pronto (chips de IA/voz/exibição, "Testar o personagem agora"). Cada etapa mostra um resultado
verificável ("Pronto — gemma3:4b", "Ainda não está pronto"), usa os mesmos componentes das
páginas (sem ir e voltar) e deixa terminar depois. A altura acompanha a etapa atual.

## Design system

Novos componentes: `ChoiceCard` (opção grande e acessível por teclado), `StateChip` (estado
com ícone + texto + cor — nunca só cor), `SecretField` (valor mascarado + olho + copiar),
`ConfirmDialog` (uma pergunta antes de instalar, senha, revelar), `Steps`, `OllamaPanel`,
`ModelCatalog`, `ModelSuggestions`, `EngineCards`, `DisplayModePicker`, `CharacterWindowCard`,
`ObsAccess`, `RemoteWizard`, `StartReport`, singleton `Privacy`. Ícones novos (Lucide, ISC):
eye, eyeOff, cpu, package, server, wifi, appWindow, network, checkCircle, cloud, router, pin,
undo, move, pointer, heart. Mesmos tokens de cor do `Theme.qml` (contraste WCAG AA testado).

Correções: o `AppCombo` cortava listas longas sem rolagem; o cabeçalho de `Section` sem
descrição puxava as ações para a esquerda; RAM/VRAM em unidades binárias ("16 GB", não "17,1").

**Restaurar padrões por seção** (Configurações e nas próprias seções): geração da IA, voz, leitura,
animações, aparência no OBS, janela — sem tocar em modelo, host, token, plataformas ou logins.

## Acessibilidade

Todos os controles novos têm `Accessible.name`/`role`; opções e passos navegáveis por Tab e
ativáveis por Espaço/Enter; estados com texto e ícone; tooltips nos botões só com ícone; menu do
personagem pela tecla Menu; foco inicial no botão de confirmar dos diálogos.

## Internacionalização

Todas as ~460 strings novas em inglês com `qsTr`/`self.tr` e traduzidas em
`tools/translations_pt_BR.py` (catálogo completo, testado). O `tools/update_translations.py`
agora lista os `.py` da GUI um a um: o `lupdate` ignora `.py` quando varre uma pasta.

## Validação visual

Capturas da aplicação real (perfil isolado) em pt-BR: tema escuro a 1360×880 (Painel com relatório,
IA, Voz, Onde mostrar, assistente, diálogo de instalação) e **tema claro no tamanho mínimo
1020×660** (IA, Onde mostrar, Voz). Corrigido por causa delas: o chip de privacidade era cortado na
barra lateral (rótulo encurtado para "Privacidade: ligada").
