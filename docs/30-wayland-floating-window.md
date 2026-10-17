# 30 — Personagem numa janela na área de trabalho (Wayland e X11)

## Problema

O personagem só existia no OBS. O protótipo em `docs/exemplo/` (Electron) mostrava a ideia:
janela transparente, sem moldura, 400×600, acima das outras, perto do canto. Ele tinha
porém um token fixo na URL, `nodeIntegration: true` / `contextIsolation: false` e
`alwaysOnTop`/`x`/`y`, que **não funcionam no Wayland** para clientes comuns.

## Solução

| Arquivo | Papel |
|---|---|
| `chattoon/gui/character_window.py` | Controlador: abre/fecha, tamanho, flags, posição, ícone, persistência |
| `chattoon/gui/kwin.py` | Ponte KWin: carrega um script por D-Bus e recebe a geometria de volta |
| `chattoon/gui/qml/CharacterWindow.qml` | A janela: WebEngine transparente, arrastar, redimensionar, menu |
| `chattoon/gui/qml/CharacterWindowCard.qml`, `DisplayModePicker.qml` | Controles na página "Onde mostrar" |
| `chattoon/gui/icons.py` (`character_icon`) | Ícone do personagem 16–256 px, recortado e centralizado |
| `chattoon/web/overlay/overlay.js`, `overlay.css` | Papel `desktop`: enquadramento próprio, balão compacto |
| `chattoon/core/overlay_server.py` | Papel de WebSocket `desktop` (assiste, nunca recebe áudio) |
| `chattoon/core/config.py` (`DisplaySettings`) | Modo, tamanho, posição, tela, opções |

A janela carrega **a mesma página do OBS** com `?role=desktop&transparent=1`, obtida em tempo
de execução do servidor (porta e token reais). Assim animações, expressões, balão e lábios
ficam sincronizados com o OBS sem gerar respostas ou síntese duas vezes.

**Áudio:** o servidor só entrega o áudio ao último cliente `obs`. A janela nunca toca som; a voz
sai uma vez, no computador ou no OBS, como já era (`docs/12`).

## Capacidades por sessão (detectadas, nunca presumidas)

| Recurso | X11 sem KWin | X11/Wayland com KWin (KDE Plasma) | Wayland sem KWin |
|---|---|---|---|
| Transparência | sim (com compositor) | sim | sim |
| Arrastar (`startSystemMove`) | sim | sim | sim |
| Redimensionar (alça, Ctrl+rolagem) | sim | sim | sim |
| Cliques atravessam (`WindowTransparentForInput`) | sim | sim | sim |
| Manter acima | flag Qt | script KWin (`keepAbove`) | **não** (avisa na interface) |
| Posição lembrada / mover para outra tela | flag Qt | script KWin (`frameGeometry`) | **não** |
| Ocultar da barra de tarefas | `Qt.Tool` | script KWin (`skipTaskbar`) | **não** |
| Ícone do personagem | `_NET_WM_ICON` | `setIcon` (xdg-toplevel-icon) | ícone do app |

**Por que KWin scripting:** o Wayland não tem protocolo padrão para "sempre acima" nem posição
absoluta. O KWin aceita scripts JavaScript por `org.kde.KWin /Scripting` com os direitos do
usuário (sem senha, sem instalar nada, some ao encerrar a sessão). O script gerado identifica a
janela por **PID + título exato** (o título vai como JSON, nunca texto cru), aplica as opções e
chama `callDBus` de volta com `{x, y, width, height, output}`; o ChatToon valida os números
(qualquer processo da sessão pode chamar esse método) e salva 0,8 s depois do último movimento.
Na primeira abertura o script coloca a janela no canto inferior direito da **área útil**
(`workspace.clientArea(MaximizeArea)`, que exclui o painel) da tela ativa.

Alternativas avaliadas: `layer-shell-qt` (sem bindings PySide6; papel de "painel", não janela),
regras de janela manuais do KWin (exigiriam editar configuração de terceiros), Electron (mesmas
limitações do Wayland, mais peso).

## Menu do personagem

Abrir o ChatToon · Personagem › (seis) · Tamanho › pequeno/médio/grande · Mover para a tela ›
(se houver mais de uma) · Manter acima · Travar posição e tamanho · Balão de fala · Deixar os
cliques atravessarem · Ocultar o personagem · Sair do ChatToon. O menu é uma janela própria
(`popupType: Popup.Window`), então funciona mesmo com a janela pequena. Teclado: tecla Menu
abre o menu, Esc oculta.

Fechar a janela principal com o personagem aberto mantém o ChatToon rodando; o menu do
personagem traz "Abrir o ChatToon" e "Sair do ChatToon".

## Problemas encontrados e corrigidos durante a validação

1. **Janela coletada pelo garbage collector do QML** (objeto com posse JavaScript): posse C++
   explícita (`QQmlEngine.setObjectOwnership`).
2. **Motor QML mantido vivo pela referência do controlador** → avisos "of null" ao fechar:
   referência liberada no `shutdown()` e janela destruída antes do motor em `app.run()`.
3. **Primeira posição sobre o painel**: posicionamento inicial pelo `clientArea` do KWin.
4. **Balão translúcido só na janela do desktop**: camadas com `will-change: transform, opacity`
   são compostas com alfa errado pelo QtWebEngine numa janela transparente (teste isolado:
   `rgba(255,255,255,0.96)` comum ficou opaco; o mesmo com `will-change` ficou quase invisível).
   No modo desktop o balão não é promovido e usa fundo opaco. O OBS não é afetado.

## Validação

Executado ao vivo em KDE Plasma 6 Wayland (3 monitores), capturas pelo Spectacle:
transparência real sobre outras janelas; capacidades detectadas
`{platform: wayland, kwin: true, keepAbove, position, skipTaskbar, clickThrough, move: true}`;
geometria reportada pelo KWin e salva (`x=6448, y=776, screen=DP-1`); balão opaco acompanhando a
cabeça durante uma fala; troca do clique através em tempo de execução (flags com
`WindowTransparentForInput`, janela continua visível). Testes automáticos:
`tests/test_character_window.py`.

## Limitações restantes

* **Sessão X11** não foi testada ao vivo (o computador de validação usa Wayland); o caminho X11
  usa só APIs Qt padrão e está coberto pela lógica, não por captura.
* **Ícone por janela**: o Plasma agrupa as janelas do mesmo app (`chattoon`) na barra de tarefas
  e mostra o ícone do ChatToon. O ícone do personagem é enviado (`setIcon`), mas não foi
  confirmado visualmente no alternador de janelas. A interface diz isso honestamente.
* **Clique através no Wayland**: aplicado pela flag Qt (região de entrada vazia); a passagem real
  dos cliques não foi automatizada (exige injeção de entrada).
* GNOME/Wayland e outros compositores: sem manter acima / posição (sem protocolo); avisado na
  interface.

## 2.4.1 — enquadramento e menu

**Problema relatado:** na janela, o personagem aparecia cortado (pés fora da janela) e o balão
não cabia. Causa: a janela usava a câmera do OBS (pensada para 1920×1080) e os modelos têm
tamanhos muito diferentes — a cabeça do cachorro e o corpo da coruja enchiam a janela inteira, e
sem espaço acima da cabeça o balão ia para o lado e era cortado na borda.

**Correção:**
* `overlay.js` `frameDesktop()`: depois de carregar cada personagem, mede a caixa real do modelo
  (`Box3.setFromObject`) e calcula a distância e a altura da câmera para o corpo inteiro ocupar os
  60 % de baixo da janela (pés a 3,5 % da borda, folga para pulos, orelhas e asas), cabendo também
  na largura. Recalcula ao redimensionar.
* Balão na janela: sempre acima da cabeça, nunca ao lado; uma fala longa pode encostar na testa,
  mas nunca sai da janela. Fonte um pouco menor.
* Janela maior: pequeno 320×480, normal 440×660, grande 600×900 (mínimo 260×390). A área
  clicável acompanha o novo enquadramento.

Validado ao vivo com os seis personagens falando uma frase longa: todos inteiros, balão completo.

**Menu do botão direito** (`qml/CharacterMenu.qml`, substitui o `Menu` padrão): cabeçalho com o
personagem, avatares para trocar, tamanho (segmentado), quatro botões de liga/desliga com ícone
(acima das janelas, travar, balão, cliques atravessam), telas, e Abrir / Ocultar / Sair. Nos
tamanhos normal e grande ele é desenhado dentro da janela, exatamente no clique (no Wayland, um
menu em janela própria é posicionado pelo compositor e ia parar ao lado); enquanto aberto, a janela
inteira recebe o mouse. No tamanho pequeno, onde não cabe, abre em janela própria.
