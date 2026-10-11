# Protótipos antigos (obsoletos)

Primeira versão do ChatToon, substituída pelo aplicativo em `chattoon/`. Mantidos só como
referência histórica. **Não use em transmissões.**

Problemas encontrados (ver `docs/01-audit.md`):

- `index.js` tinha a chave da API de livestream do Rumble no código (commit `e29b51a`, já
  publicado). Ela foi removida daqui, mas continua no histórico do Git: **revogue-a no painel
  do Rumble**. Agora o script lê `RUMBLE_API_URL` do ambiente.
- `bot_chat*.py` chamavam `os.system(f"spd-say '...{texto}'")` com texto vindo do chat e da IA:
  injeção de comandos (uma mensagem com `'; rm -rf ~ #` seria executada). Trocado por
  `subprocess.Popen([...])` sem shell.
- Voz duplicada: o Python falava com `spd-say` e a página falava de novo com `SpeechSynthesis`.
- Duplicatas detectadas só comparando com a última mensagem; URL inteira passada como ID do vídeo;
  `pytchat` sem manutenção; modelos e URLs fixos no código; bot do Gemini com chave em texto.
