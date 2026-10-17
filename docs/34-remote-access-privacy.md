# 34 — Acesso pela internet e privacidade

## Assistente (5 etapas)

Substitui o campo solto "Acesso de outro computador". Uma única implementação: o mecanismo do
[21](21-dominio-proprio.md) (proxy HTTPS neste computador → `127.0.0.1:<porta>`, endereço público em
`overlay.public_address`, Host aceito pelo guard). O guia 21 continua válido como passo a passo
detalhado do DigitalPlat + Cloudflare; o assistente cobre qualquer provedor.

1. **Verificar a conexão** — IP privado vs público explicado em uma frase. O IP público só é
   consultado com consentimento (`api.ipify.org`, diálogo explica quem vê o pedido), fica só na
   memória, aparece **mascarado** (`***.***.***.***`) e entra no filtro de logs. CGNAT detectado
   quando o IP é 100.64.0.0/10; caso contrário a orientação é comparar com o "IP WAN" do roteador.
   IPv6 público é apontado como alternativa.
2. **Domínio** — qualquer provedor (domínio próprio, DuckDNS, No-IP, DigitalPlat FreeDomain,
   Cloudflare…); validação de formato (só `https://` + nome de domínio; IP puro é recusado, pois
   não há certificado para ele). O campo fica oculto (••••) no modo privacidade quando não está em
   edição.
3. **Chegar com segurança** — duas rotas comparadas: abrir portas no roteador (8443 e 80, só para o
   Caddy; **nunca** a porta do ChatToon nem a 11434 do Ollama) ou **túnel** sem abrir portas
   (Cloudflare Tunnel, Tailscale Funnel, com detecção do que está instalado e o comando pronto).
4. **HTTPS** — estado do Caddy/nginx; configuração gerada com o domínio e a **porta real**;
   nginx com `Upgrade`/`Connection` para o WebSocket.
5. **Testar** — `core/remote_check.py` testa o caminho real e para na primeira falha:
   formato → DNS (falhou / aponta para rede privada / aponta para outro IP público) → porta
   (tempo esgotado / recusada) → certificado (inválido, com o motivo) / porta sem HTTPS → HTTP
   (Host não aceito pelo ChatToon / token antigo / proxy 502–504 / outro status) → WebSocket
   (`role=probe`, espera o `hello`). A conexão vai ao IP que o DNS respondeu. A nota sobre NAT
   loopback ("teste pelo 4G") aparece sempre.

## Privacidade

| Sempre mascarado | Também no "Modo Privacidade para Lives" (ligado por padrão) |
|---|---|
| Token dentro de qualquer endereço do overlay (`/o/••••••/`) | IP da LAN, domínio público, IPs em erros e diagnósticos |
| IP público (`***.***.***.***`) | Login da conta da Twitch |
| Segredos registrados (token, IP público) em toasts e logs | Campo do domínio fora de edição |

* **Revelar** é deliberado: ícone de olho → aviso ("quem assiste também verá") → visível por
  **15 segundos**, depois tudo volta a ser oculto. Copiar copia o valor real e avisa que contém
  um código secreto.
* Um chip "Privacidade para lives: ligada/desligada" fica sempre na barra lateral.
* `core/privacy.scrub()` passa em **todo** toast e erro do engine antes de chegar à tela;
  `qml/Privacy.qml` aplica as mesmas regras na exibição. O token e o IP público entram no
  `REDACTOR` de logs (`core/credentials.py`).
* O relatório de início não contém tokens nem endereços (teste dedicado).
* A configuração persiste entre reinicializações (`privacy_mode` no `settings.json`).

## Testes

`tests/test_remote_privacy.py`: o caminho inteiro com **HTTPS real local** (certificado de uma CA
descartável, Overlay real atrás de um site TLS, WebSocket `probe`), certificado não confiável,
Host desconhecido, token antigo, proxy 502, HTTP puro na porta HTTPS, porta fechada, falhas de DNS
e o mascaramento. **Não executado:** um domínio real, um roteador real e um túnel real.
