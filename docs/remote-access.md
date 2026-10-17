# OBS em outro computador pela internet

Para quando o OBS **não** está na sua casa (um computador de transmissão em outro lugar, a casa
de um parceiro de live). Se o OBS está **neste computador** ou **na mesma rede de casa**, você
não precisa de nada disto: use **Onde mostrar → Onde está o seu OBS Studio?** no ChatToon.

O ChatToon tem um assistente com estas mesmas cinco etapas em **Onde mostrar → Outro
computador pela internet**, inclusive o teste final que diz exatamente o que está faltando.

> Troque `meucanal.exemplo.org` pelo **seu** domínio. Nunca mostre na live o endereço público do
> overlay nem o seu IP: o **Modo Privacidade para Lives** do ChatToon já esconde os dois.

## Como as peças se encaixam

```
OBS (em outro lugar)
   │  https://meucanal.exemplo.org:8443/o/<código secreto>/
   ▼
DNS ─────────── diz que meucanal.exemplo.org = o IP público da sua casa (ou o seu túnel)
   ▼
Roteador ────── encaminha 8443 e 80 para o seu computador   (ou: túnel, sem abrir portas)
   ▼
Caddy ───────── HTTPS com certificado automático, repassa para o ChatToon
   ▼
ChatToon em 127.0.0.1 ── nunca fica exposto direto na internet
```

## 1. Verificar a conexão

Seu computador tem um **IP privado** dentro de casa e a sua internet tem um **IP público**.
Muitas operadoras usam **CGNAT**: vários clientes dividem o mesmo IP público, e então
**nenhum encaminhamento de porta funciona**.

No assistente, **Descobrir meu IP público** pergunta ao `api.ipify.org` (só depois da sua
confirmação; o resultado fica oculto e só na memória). Compare com o **IP WAN** que aparece na
página de status do roteador:

* iguais → siga a rota "abrir portas";
* o roteador mostra `100.64.x.x`–`100.127.x.x`, `10.x`, `172.16–31.x` ou `192.168.x` → CGNAT ou
  NAT duplo: peça um IP público à operadora, coloque o modem dela em modo *bridge*, ou use a
  rota "túnel".

## 2. Domínio

O certificado HTTPS precisa de um nome. Use um domínio seu ou um nome grátis de DNS dinâmico
(DuckDNS, No-IP, DigitalPlat FreeDomain em <https://dash.domain.digitalplat.org>, Cloudflare…).
Crie um registro **A** apontando para o seu IP público (no túnel, o nome vem do próprio túnel).
Na Cloudflare, comece com a nuvem **cinza** (*Somente DNS*).

Se o seu IP público muda de vez em quando, use o cliente de DNS dinâmico do seu provedor (ou o
script de atualização da Cloudflare, rodando por um timer do systemd do seu usuário).

Digite o endereço no assistente, por exemplo `https://meucanal.exemplo.org:8443`. O ChatToon só
aceita `https://` com nome de domínio.

## 3. Chegar ao computador com segurança

**Rota A — abrir portas no roteador** (precisa de IP público de verdade):

1. Reserve no roteador o IP deste computador (*Reserva de DHCP*).
2. Encaminhe **TCP 8443** (HTTPS) e **TCP 80** (emissão e renovação do certificado) para ele.
3. **Nunca** encaminhe a porta do ChatToon (8765) nem a do Ollama (11434).
4. Com dois roteadores (operadora + Wi-Fi), encaminhe nos dois ou use modo *bridge*.

**Rota B — túnel, sem abrir portas** (funciona com CGNAT):

* Cloudflare Tunnel: `cloudflared tunnel --url http://127.0.0.1:8765` (um túnel rápido ganha um
  nome novo a cada início; para um nome fixo, crie um túnel nomeado na sua conta).
* Tailscale Funnel: `tailscale funnel 8765`.

Túneis já entregam HTTPS: pule a etapa 4 e use o nome `https://` do túnel na etapa 2.

## 4. HTTPS com o Caddy

```bash
sudo pacman -S --needed caddy
sudo systemctl enable --now caddy
```

Salve em `/etc/caddy/conf.d/chattoon.caddy` (o assistente gera o arquivo com o seu domínio e a
porta real do ChatToon; use **Copiar configuração do Caddy**):

```
meucanal.exemplo.org:8443 {
	reverse_proxy 127.0.0.1:8765
}
```

```bash
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo systemctl reload caddy
```

Com nginx, o assistente (modo avançado) gera um bloco equivalente com `proxy_set_header Upgrade`
e `Connection "upgrade"` para o WebSocket.

## 5. Testar

**Testar a conexão** no assistente percorre o caminho real e para no primeiro problema:

| Etapa | O que pode dar errado |
|---|---|
| Nome (DNS) | o nome não existe; aponta para um IP de rede de casa; aponta para outro IP público |
| Porta | não responde (encaminhamento, firewall, CGNAT); recusada (Caddy parado) |
| Certificado | ainda não emitido ou de outro nome; a porta não fala HTTPS |
| Proxy e ChatToon | o ChatToon não conhece o nome (o endereço da etapa 2 deve ser idêntico ao do proxy); código secreto antigo; o proxy não alcança o ChatToon (porta errada, app fechado) |
| Conexão ao vivo | o proxy não repassa o WebSocket |

Testar de dentro de casa pode falhar mesmo com tudo certo (muitos roteadores não fazem *NAT
loopback*). Confirme por um celular nos dados móveis. No OBS do outro computador: **Fontes → +
→ Navegador**, cole o endereço público, 1920 × 1080. Para a voz sair por esse OBS, escolha
**Voz → Saída de áudio → Dentro do OBS** e ative *Controlar áudio via OBS* na fonte.

**O endereço é como uma senha.** Se ele vazar, use **Onde mostrar → Novo endereço secreto**:
todos os links antigos param de funcionar na hora.

## Desfazer

1. ChatToon: apague o endereço da etapa 2.
2. `sudo rm /etc/caddy/conf.d/chattoon.caddy && sudo systemctl reload caddy`
3. Roteador: apague as regras de 8443 e 80 (ou pare o túnel).
4. DNS dinâmico: desligue o timer/cliente e revogue o token do provedor.
