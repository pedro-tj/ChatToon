# 35 — Iniciar: relatório da sessão

## Comportamento

**Iniciar** (barra lateral, Painel ou Ctrl+Espaço) agora:

1. confere os serviços de novo (`engine.check_services`) e o estado do Ollama (`OllamaService`);
2. monta o relatório (`core/readiness.build`) — só fatos, em códigos;
3. **só inicia se nada essencial faltar**: IA (Ollama respondendo + modelo de conversa instalado e
   escolhido) e, fora do modo Demonstração, uma plataforma ativa. Nunca mostra "Executando" com
   falha crítica;
4. abre o resumo (`qml/StartReport.qml`) e, em segundo plano, **comprova**: carrega o modelo
   (`preload`, mostra o tempo) e sintetiza "Oi!" com a voz do personagem **sem tocar** — o
   resultado atualiza o relatório ("respondeu em 1,8 s", "✓ pronta para falar").

Vermelho = obrigatório (bloqueia, com botão **Configurar IA / voz / plataforma** que leva à
página certa); amarelo = opcional (voz ausente, OBS ainda não conectado, janela fechada);
**Tentar de novo** refaz tudo.

Conteúdo: personagem (imagem, nome, personalidade, estado), IA (modelo, versão, problema),
voz (mecanismo, voz, destino, teste), plataformas (habilitadas, modo de interação), onde
aparece (OBS e quantas fontes, janela, LAN, endereço público) e **o que o personagem vai fazer**,
cada item calculado das configurações reais: responder ao chat, ler quem enviou, ler a mensagem,
reagir com emoções, animações ociosas, falar sozinho, contar curiosidades, lembrar da conversa
(e entre lives), conversar com as plataformas, usar o contexto da live, falar com voz.

**Saúde do sistema** (Painel) roda as mesmas verificações sem entrar ao vivo; **Relatório da
sessão** reabre o último. Escrever no "Fale com o avatar" no modo Demonstração inicia sem abrir
o relatório, que só aparece se algo essencial faltar.

## Arquivos

`core/readiness.py`, `gui/session_report.py`, `core/engine.py` (`verify`), `qml/StartReport.qml`,
`qml/pages/DashboardPage.qml`, `gui/backend.py` (`start`, `startQuietly`).

## Testes e validação

`tests/test_remote_privacy.py` (tudo pronto; sete formas de IA faltando; plataforma obrigatória
fora do modo demo; avisos opcionais; nenhum token no relatório) e
`tests/test_character_window.py` (relatório pela interface). Ao vivo: com o Ollama realmente
ausente, Iniciar mostrou "Falta pouco!", IA "Obrigatório — O Ollama não está instalado", voz
"Piper — Faber" e não iniciou. Bug encontrado na validação e corrigido: o atributo `_report` do
controlador sobrescrevia o callback da classe base.
