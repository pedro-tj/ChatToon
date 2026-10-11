import time
import os
import subprocess
import pytchat
import ollama  # Importa a biblioteca do Ollama

# ID da live do YouTube
VIDEO_ID = "https://www.youtube.com/live_chat?is_popout=1&v=ndweu4rdNHk"

SYSTEM_INSTRUCTION = """
Você é uma ete 3D virtual que interage com o chat em uma transmissão ao vivo.
antes de responder leia a mensagem e Responda de forma curta (1 a 2 frases), com um toque de humor, irônico ou amigável, e sotaque brasileiro informal.
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
                response = ollama.chat(model='llama3', messages=[
                    {'role': 'system', 'content': SYSTEM_INSTRUCTION},
                    {'role': 'user', 'content': f"Usuário {autor} disse no chat: '{mensagem}'"}
                ])
                resposta_lagarta = response['message']['content'].strip()
                print(f"[Cobra Ollama]: {resposta_lagarta}")

            except Exception as ai_err:
                print(f"[Aviso] Ollama indisponível/Erro: {ai_err}. Usando texto direto do chat.")
                resposta_lagarta = f"({autor}): {mensagem}"

            # 1. Salva o resultado no arquivo de texto para a lagarta 3D exibir no OBS
            with open("chat_recente.txt", "w", encoding="utf-8") as f:
                f.write(f"Cobra: {resposta_lagarta}")

            # 2. Fala usando a voz da Letícia (spd-say) em segundo plano
            texto_para_falar = resposta_lagarta.replace("Cobra: ", "").replace('"', '')
            subprocess.Popen(['spd-say', '-l', 'pt', '-t', 'female1', '--', texto_para_falar])  # sem shell: sem injeção

        time.sleep(1.5)

except Exception as e:
    print(f"Erro no chat: {e}")
