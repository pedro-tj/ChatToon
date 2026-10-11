import time
import pytchat
import os
import subprocess
import pytchat
from google import genai

# 1. Configurar a API do Gemini (substitua pela sua chave gratuita do Google AI Studio)
client = genai.Client(api_key="AQUI-VAI-TUA-API-DA-IA-NA-NUVEM")

# ID da live do YouTube
VIDEO_ID = "LINK-DOCHAT-DO-YouTube"

# Personalidade da Cobra (System Prompt)
SYSTEM_INSTRUCTION = """
Você é uma cobra 3D virtual que interage com o chat em uma transmissão ao vivo de tecnologia e Linux.
Responda de forma curta (1 a 2 frases), com um toque de humor, irônico ou amigável, e sotaque brasileiro informal.
"""

print("Iniciando o bot da cobra com controle de duplicatas e voz do sistema...")

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
            resposta_cobra = ""

            try:
                # Tenta chamar a IA
                prompt_usuario = f"Usuário {autor} disse no chat: '{mensagem}'"
                response = client.models.generate_content(
                    model='gemini-3.8-flash',
                    contents=prompt_usuario,
                    config={
                        'system_instruction': SYSTEM_INSTRUCTION,
                        'max_output_tokens': 100,
                        'temperature': 0.7,
                    },
                )
                resposta_cobra = response.text.strip()
                print(f"[Cobra AI]: {resposta_cobra}")

            except Exception as ai_err:
                # Fallback se a IA falhar
                print(f"[Aviso] IA indisponível/Erro: {ai_err}. Usando texto direto do chat.")
                resposta_cobra = f"({autor}): {mensagem}"

          # 1. Salva o resultado no arquivo de texto para a cobra 3D exibir no OBS
            with open("chat_recente.txt", "w", encoding="utf-8") as f:
                f.write(f"Cobra: {resposta_cobra}")

            # 2. Fala usando a voz da Letícia (spd-say) em segundo plano
            texto_para_falar = resposta_cobra.replace("Cobra: ", "").replace('"', '')
            subprocess.Popen(['spd-say', '-l', 'pt', '-t', 'female1', '--', texto_para_falar])  # sem shell: sem injeção

        time.sleep(1.5)

except Exception as e:
    print(f"Erro no chat: {e}")
