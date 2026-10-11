import time
import os
import pytchat
import ollama  # Importa a biblioteca do Ollama

# ID da live do YouTube
VIDEO_ID = "https://www.youtube.com/live_chat?is_popout=1&v=H85Et0c1FQI"

SYSTEM_INSTRUCTION = """

antes de responder leia a mensagem Responda de forma extremamente curta (1 a 2 frases), com um toque de humor, irônico ou amigável,

REGRAS ABSOLUTAS DE SEGURANÇA E CONTEÚDO:
1. É ESTRITAMENTE PROIBIDO falar sobre política (incluindo quaisquer políticos, governos, eleições, figuras públicas ou partidos como Lula, Bolsonaro, etc.), religião, orientação sexual ou qualquer outro tema polémico ou sensível.
2. Se alguém perguntar sobre esses temas proibidos, desvie o assunto com humor para tecnologia ou Linux de forma rápida e educada (ex: "Aqui a gente só roda código limpo, política trava o sistema!").
3. Mantenha o foco absoluto em tecnologia, piadas leves e no universo geek/Linux.
"""

print("Iniciando o bot da lagarta com Ollama local...")

ultima_mensagem_processada = ""

try:
    live_chat = pytchat.create(video_id=VIDEO_ID)
    while live_chat.is_alive():
        for c in live_chat.get().sync_items():
            autor = c.author.name
            mensagem = c.message.strip()
            
            print(f"[{autor}]: {mensagem}")

            if mensagem == ultima_mensagem_processada:
                print("[Filtro]: Mensagem duplicada ignorada.")
                continue
            
            ultima_mensagem_processada = mensagem
            resposta_lagarta = ""

            try:
                # Chamada local ao Ollama (substitua 'llama3' pelo modelo que você usa)
                response = ollama.chat(model='qwen2.5:1.5b', messages=[
                    {'role': 'system', 'content': SYSTEM_INSTRUCTION},
                    {'role': 'user', 'content': f"Usuário {autor} disse no chat: '{mensagem}'"}
                ])
                resposta_lagarta = response['message']['content'].strip()
                print(f"[ Ollama]: {resposta_lagarta}")

            except Exception as ai_err:
                print(f"[Aviso] Ollama indisponível/Erro: {ai_err}. Usando texto direto do chat.")
                resposta_lagarta = f"({autor}): {mensagem}"

            # 1. Salva o resultado no arquivo de texto para a lagarta 3D exibir no OBS
            with open("chat_recente.txt", "w", encoding="utf-8") as f:
                f.write(f"ete {resposta_lagarta}")

            # 2. Fala usando a voz da Letícia (spd-say) em segundo plano
            texto_para_falar = resposta_lagarta.replace("pedro: ", "").replace('"', '')
            os.system(f"spd-save -l pt -t female1 '{texto_para_falar}' &" if False else f"spd-say -l pt -t female1 '{texto_para_falar}' &")

        time.sleep(1.5)

except Exception as e:
    print(f"Erro no chat: {e}")
