const fs = require('fs');

// Substitua pela URL da API de Live Stream fornecida pelo painel do Rumble
const rumbleApiUrl = 'https://rumble.com/-livestream-api/get-data?key=dzQkOLTgdFrJGNQIFkb7tbdOrvDceDjS0A9zASrYuYk2mkU93Lbou5NOqi8f-DF9ncu8X12YmtfR5IHATMMI_g';

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
