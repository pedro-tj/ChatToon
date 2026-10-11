const fs = require('fs');

// Substitua pela URL da API de Live Stream fornecida pelo painel do Rumble
// A chave antiga foi exposta no commit e29b51a e deve ser REVOGADA no painel do Rumble.
const rumbleApiUrl = process.env.RUMBLE_API_URL;
if (!rumbleApiUrl) { console.error('Defina RUMBLE_API_URL com a URL da API (não versionar).'); process.exit(1); }

let ultimaMensagemID = "";

async function verificarChatRumble() {
    try {
        const response = await fetch(rumbleApiUrl);
        if (!response.ok) return;
        
        const data = await response.json();
        
        // Verifica se existem mensagens de chat recentes na live
        if (data.livestreams && data.livestreams.recent_chat_messages) {
            const mensagens = data.livestreams.recent_chat_messages;
            
            if (mensagens.length > 0) {
                // Pega a mensagem mais recente
                const ultima = mensagens[mensagens.length - 1];
                const identificadorUnico = `${ultima.username}-${ultima.time}`;
                
                // Se for uma mensagem nova que ainda não foi lida
                if (identificadorUnico !== ultimaMensagemID) {
                    ultimaMensagemID = identificadorUnico;
                    
                    const textoFormatado = `${ultima.username}: ${ultima.text}`;
                    console.log(`Nova mensagem do Rumble: ${textoFormatado}`);
                    
                    // Salva no arquivo que o HTML do ET lê
                    fs.writeFileSync('chat_recente.txt', textoFormatado, 'utf8');
                }
            }
        }
    } catch (error) {
        console.error('Erro ao buscar dados do Rumble:', error);
    }
}

// Fica checar o chat do Rumble a cada 2 segundos
setInterval(verificarChatRumble, 2000);
