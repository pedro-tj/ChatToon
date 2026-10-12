# 21 — Seu próprio domínio para o overlay (DigitalPlat + Cloudflare + roteador)

Este guia é para quem quer abrir o overlay do ChatToon **em outro computador** (por exemplo, o
OBS numa máquina de transmissão separada, ou na casa de um parceiro de live) usando um endereço
HTTPS como `https://meucanal.dpdns.org:8443/o/<token>/`.

Se o OBS roda **no mesmo computador** que o ChatToon, nada disso é necessário: use o endereço
`http://127.0.0.1:8765/o/<token>/` da página **OBS Studio**.

> Em todo o guia, troque `meucanal.dpdns.org` pelo **seu** domínio, `203.0.113.10` pelo **seu**
> IP público e `192.168.0.50` pelo IP **do seu computador** na rede de casa. Cada pessoa
> configura o seu; não use o domínio de outra pessoa.

## Como as peças se encaixam

```
OBS (outro computador)
   │  https://meucanal.dpdns.org:8443/o/<token>/
   ▼
Cloudflare (DNS) ── diz que meucanal.dpdns.org = seu IP público
   ▼
Seu roteador ────── encaminha as portas 80 e 8443 para o seu computador
   ▼
Caddy (no seu computador) ── HTTPS com certificado automático
   ▼
ChatToon em 127.0.0.1:8765 ── nunca fica exposto direto na internet
```

| Peça | Para que serve | Custo |
|---|---|---|
| **DigitalPlat FreeDomain** | registra o nome `meucanal.dpdns.org` | grátis |
| **Cloudflare** | responde quem é `meucanal.dpdns.org` (DNS) | grátis (plano Free) |
| **Roteador** | deixa a internet chegar ao seu computador | — |
| **Caddy** | HTTPS e certificado automáticos, repassa para o ChatToon | grátis |

**Tempo estimado:** 30 a 60 minutos, a maior parte esperando o DNS propagar.

## Antes de começar: confira se a sua internet aceita conexões de fora

Muitas operadoras usam **CGNAT**: vários clientes dividem o mesmo IP público, e aí nenhum
encaminhamento de porta funciona. Confira antes de gastar tempo:

1. Descubra o seu IP público, no computador:
   ```bash
   curl -4 https://ifconfig.me
   ```
2. Entre no roteador (passo 4) e procure o **IP da WAN / IP da internet** na página de status.
3. Compare:
   - **iguais** → ótimo, siga o guia;
   - WAN começa com `100.64.` a `100.127.`, `10.`, `172.16.`–`172.31.` ou `192.168.` → você está
     atrás de **CGNAT** ou de **NAT duplo**. Peça à operadora um **"IP público"/"IP válido"**
     (algumas cobram), ou coloque o modem da operadora em **modo bridge** se houver um segundo
     roteador. Sem isso, este guia não funciona.

## Passo 1 — Registre o domínio no DigitalPlat

O DigitalPlat FreeDomain oferece domínios grátis como `.dpdns.org`, `.qzz.io`, `.us.kg`,
`.xx.kg` e `.qd.je`. Hoje o limite padrão é **1 domínio por conta**.

1. Acesse **https://dashboard.digitalplat.org** (também responde em
   `https://dash.domain.digitalplat.org`) e crie a conta. Entrar com o **GitHub** costuma agilizar
   a verificação. Use dados verdadeiros: nome, e-mail que você acessa, telefone e endereço.
2. Escolha **Register**, digite o nome desejado (ex.: `meucanal`), escolha o final
   (`.dpdns.org`) e clique em **Check availability**.
3. Se o painel pedir **nameservers** já no registro, deixe esta aba aberta, faça o passo 2 até
   receber os dois nameservers da Cloudflare e volte aqui. Se não pedir, conclua o registro e
   preencha depois.
4. Em **Domain List** confira o domínio e anote a **data de expiração**. Coloque um lembrete
   no celular para renovar antes disso; se expirar, o endereço do overlay para de funcionar.

## Passo 2 — Coloque o domínio na Cloudflare

1. Crie uma conta grátis em **https://dash.cloudflare.com** (o painel pode ser usado em
   português).
2. Clique em **Adicionar um domínio** (*Add a domain*), digite `meucanal.dpdns.org` e escolha
   o plano **Free**.
3. A Cloudflare pode procurar registros DNS existentes; para um domínio novo não haverá nenhum.
   Continue.
4. Ela vai mostrar **dois nameservers**, parecidos com `nome1.ns.cloudflare.com` e
   `nome2.ns.cloudflare.com`. Copie os dois.
5. Volte ao **DigitalPlat**, abra o seu domínio, procure o campo **Nameservers (NS)**, cole os
   **dois** nomes exatamente como a Cloudflare mostrou e salve. Coloque **nomes**, nunca IPs.
6. Espere a Cloudflare mostrar o domínio como **Ativo** (*Active*); ela também manda um e-mail.
   Leva de minutos a algumas horas. Para conferir no terminal:
   ```bash
   dig NS meucanal.dpdns.org +short   # deve listar os dois nameservers da Cloudflare
   ```

### Crie o registro que aponta para a sua casa

Na Cloudflare, com o domínio ativo:

1. Menu **DNS → Registros** (*DNS → Records*) → **Adicionar registro** (*Add record*).
2. Preencha:

   | Campo | Valor |
   |---|---|
   | Tipo (*Type*) | `A` |
   | Nome (*Name*) | `@` (o próprio domínio) |
   | Endereço IPv4 | o seu IP público (`curl -4 https://ifconfig.me`) |
   | Status do proxy | **Somente DNS** (nuvem **cinza**) |
   | TTL | Automático |

3. Salve e confira (pode levar alguns minutos):
   ```bash
   dig +short meucanal.dpdns.org    # deve mostrar o seu IP público
   ```

**Nuvem cinza ou laranja?** Comece pela **cinza** (*DNS only*): é a configuração mais simples e
a que este guia testa. A nuvem **laranja** (proxy da Cloudflare) também funciona na porta 8443 e
esconde o IP da sua casa, mas exige o modo **SSL/TLS → Full (strict)** e complica a primeira
emissão do certificado. Só ligue depois que tudo estiver funcionando com a cinza.

Com a nuvem cinza, o seu IP público fica visível para quem consultar o domínio. É o mesmo IP que
qualquer site que você visita já vê, mas não divulgue o link do overlay.

## Passo 3 — Instale e configure o Caddy no computador do ChatToon

O Caddy recebe as conexões HTTPS, obtém o certificado sozinho (Let's Encrypt) e repassa para o
ChatToon, que continua escutando só em `127.0.0.1`.

1. Instale e ligue o Caddy (BigLinux, Manjaro, Arch):
   ```bash
   sudo pacman -S caddy
   sudo systemctl enable --now caddy
   ```
2. Crie o arquivo `/etc/caddy/conf.d/chattoon.caddy` (o `Caddyfile` padrão do Arch já inclui
   essa pasta):
   ```bash
   sudo mkdir -p /etc/caddy/conf.d
   sudo tee /etc/caddy/conf.d/chattoon.caddy >/dev/null <<'EOF'
   # Overlay do ChatToon por HTTPS na porta 8443. Apague este arquivo para desfazer.
   meucanal.dpdns.org:8443 {
   	reverse_proxy 127.0.0.1:8765
   }
   EOF
   ```
   O `8765` é a porta do overlay mostrada no endereço local da página **OBS Studio**. Se ali
   aparecer outra (porque a 8765 estava ocupada), use a mesma aqui.
3. Confira e recarregue:
   ```bash
   sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
   sudo systemctl reload caddy
   ```

**Por que a porta 8443?** É uma porta HTTPS alternativa e padrão, aceita também pelo proxy da
Cloudflare, e não briga com outro site que você já tenha na 443. Se a 443 estiver livre, pode
usar `meucanal.dpdns.org { ... }` (sem `:8443`) e encaminhar a 443 no roteador em vez da 8443;
o endereço fica sem número de porta.

## Passo 4 — Configure o roteador

### 4.1 Fixe o IP do computador na rede de casa

O encaminhamento aponta para um IP da rede local; se ele mudar, tudo para.

1. Descubra o IP do computador:
   ```bash
   ip -4 route get 1.1.1.1 | grep -oP 'src \K\S+'    # ex.: 192.168.0.50
   ```
2. No roteador, procure **Reserva de DHCP / Reserva de endereço / DHCP estático** (*DHCP
   Reservation*) e reserve esse IP para o seu computador (ele aparece na lista de dispositivos
   conectados).

### 4.2 Encaminhe as portas

1. Abra o painel do roteador no navegador, geralmente `http://192.168.0.1` ou
   `http://192.168.1.1` (o endereço, usuário e senha costumam estar na etiqueta embaixo do
   aparelho).
2. Procure o menu de encaminhamento. O nome muda conforme a marca: **Encaminhamento de
   portas**, **Redirecionamento de portas**, **Servidor virtual**, **NAT**, **Port
   Forwarding** ou **Virtual Server** (TP-Link, Intelbras, Mercusys, roteadores das operadoras…).
3. Crie **duas** regras:

   | Nome | Protocolo | Porta externa | IP interno | Porta interna |
   |---|---|---|---|---|
   | ChatToon HTTPS | TCP | 8443 | 192.168.0.50 | 8443 |
   | Certificado (Caddy) | TCP | 80 | 192.168.0.50 | 80 |

   A porta **80** é usada pelo Caddy para provar ao Let's Encrypt que o domínio é seu e para
   renovar o certificado a cada poucos meses. Sem ela, o HTTPS não é emitido.
4. Salve (alguns roteadores pedem para reiniciar).

**Não** encaminhe a porta 8765 do ChatToon: ela só funciona dentro do computador, de propósito.
Se você criou essa regra antes, apague.

Se existir um **segundo roteador** (o da operadora + o seu Wi-Fi), faça o encaminhamento nos
dois, ou coloque o da operadora em modo bridge.

## Passo 5 — Ative no ChatToon

1. Abra o ChatToon → página **OBS Studio** → seção **Acesso de outro computador**.
2. Digite `https://meucanal.dpdns.org:8443` e aperte Enter.
3. Logo abaixo aparece o **endereço público do overlay**. Clique em **Copiar**.

O ChatToon só aceita esse domínio, e só com `https://`. Qualquer outro endereço recebe
**forbidden**.

## Passo 6 — Teste e use no OBS

1. **Teste pelo 4G do celular** (Wi-Fi desligado) abrindo o endereço público. Testar dentro de
   casa pode falhar mesmo com tudo certo: muitos roteadores não suportam *NAT loopback*.
2. No OBS do outro computador: **Fontes → + → Navegador**, cole o endereço público, largura
   **1920**, altura **1080**.
3. Para a voz sair pelo OBS: no ChatToon, página **Voz → Saída de áudio → Dentro do OBS**; no
   OBS, ative **Controlar áudio via OBS** (*Control audio via OBS*) nas propriedades da fonte.
4. Só fontes do OBS recebem a voz. Abrir o link num navegador comum mostra o avatar, mas não
   rouba o áudio do OBS.

**O link é como uma senha:** quem tiver o endereço com o token vê o avatar e ouve a voz. Não
mostre na tela nem cole no chat.

## Opcional — IP que muda sozinho (DDNS)

A maioria das operadoras residenciais troca o seu IP público de vez em quando (ao reiniciar o
modem, por exemplo). Quando isso acontece, o domínio continua apontando para o IP antigo. O
script abaixo atualiza o registro na Cloudflare automaticamente.

1. Crie um token na Cloudflare: ícone do perfil → **Meu perfil → Tokens de API** (*My Profile →
   API Tokens*) → **Criar token** (*Create Token*) → modelo **Editar DNS da zona** (*Edit zone
   DNS*) → em *Zone Resources* escolha **Include → Specific zone → meucanal.dpdns.org** →
   crie e copie o token (ele aparece uma vez só).
2. Salve o script em `~/.local/bin/cloudflare-ddns`:
   ```bash
   #!/bin/bash
   # Atualiza o registro A do domínio na Cloudflare com o IP público atual.
   TOKEN="cole-o-token-aqui"
   ZONA="meucanal.dpdns.org"   # o domínio adicionado na Cloudflare
   NOME="meucanal.dpdns.org"   # o registro A (o próprio domínio, no exemplo)
   API="https://api.cloudflare.com/client/v4"

   cf() { curl -fsS -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" "$@"; }
   campo() { python3 -c "import json,sys; r=json.load(sys.stdin)['result']; r=r[0] if isinstance(r,list) else r; print($1)"; }

   IP=$(curl -fsS4 https://api.ipify.org) || exit 1
   ZONA_ID=$(cf "$API/zones?name=$ZONA" | campo "r['id']") || exit 1
   read -r REG_ID ATUAL < <(cf "$API/zones/$ZONA_ID/dns_records?type=A&name=$NOME" | campo "r['id'], r['content']") || exit 1
   [ "$IP" = "$ATUAL" ] && exit 0
   cf -X PATCH --data "{\"content\":\"$IP\"}" "$API/zones/$ZONA_ID/dns_records/$REG_ID" >/dev/null \
     && echo "IP atualizado: $ATUAL -> $IP"
   ```
   ```bash
   chmod 700 ~/.local/bin/cloudflare-ddns   # o token fica só para você
   ~/.local/bin/cloudflare-ddns && echo ok
   ```
3. Rode a cada 5 minutos com um timer do systemd do usuário:
   ```bash
   mkdir -p ~/.config/systemd/user
   cat > ~/.config/systemd/user/cloudflare-ddns.service <<'EOF'
   [Unit]
   Description=Atualiza o IP do domínio na Cloudflare

   [Service]
   Type=oneshot
   ExecStart=%h/.local/bin/cloudflare-ddns
   EOF
   cat > ~/.config/systemd/user/cloudflare-ddns.timer <<'EOF'
   [Unit]
   Description=Atualiza o IP do domínio na Cloudflare a cada 5 minutos

   [Timer]
   OnBootSec=1min
   OnUnitActiveSec=5min

   [Install]
   WantedBy=timers.target
   EOF
   systemctl --user daemon-reload
   systemctl --user enable --now cloudflare-ddns.timer
   ```
   Para ver o que ele fez: `journalctl --user -u cloudflare-ddns`.

## Solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| **forbidden** | o ChatToon não conhece o domínio | preencha **Acesso de outro computador** com o endereço exato (`https://`, domínio e porta) |
| Conexão recusada / site não pode ser acessado | porta 8443 não encaminhada, IP do computador mudou, CGNAT | confira o passo 4 e a seção sobre CGNAT; teste pelo 4G |
| Funciona no 4G, mas não em casa | o roteador não faz *NAT loopback* | normal; em casa use `http://127.0.0.1:8765/o/<token>/` |
| Erro de certificado | porta 80 não encaminhada ou DNS ainda não propagado | encaminhe a 80, confira `dig +short meucanal.dpdns.org` e veja `journalctl -u caddy` |
| Erro 521/522 da Cloudflare | nuvem laranja ligada sem o caminho funcionando | volte para a nuvem cinza até tudo funcionar |
| **502 Bad Gateway** | o ChatToon está fechado ou usa outra porta | abra o ChatToon; confira a porta no endereço local e no `chattoon.caddy` |
| `dig` mostra outro IP | o IP público mudou | atualize o registro A, ou use o DDNS acima |
| Domínio parou do nada | domínio expirou no DigitalPlat | renove no painel do DigitalPlat |
| Avatar aparece, voz não sai no OBS | *Controlar áudio via OBS* desligado, ou voz em *Neste computador* | veja o passo 6 |

Comandos úteis:

```bash
dig NS meucanal.dpdns.org +short                 # nameservers (Cloudflare?)
dig +short meucanal.dpdns.org                    # IP para onde o domínio aponta
curl -4 https://ifconfig.me                      # seu IP público agora
systemctl status caddy                           # Caddy rodando?
journalctl -u caddy --since "-15 min"            # erros de certificado
ss -ltn | grep -E ':8443|:80 |:8765'             # quem está escutando
```

## Desfazer tudo

1. ChatToon: apague o campo **Acesso de outro computador**.
2. `sudo rm /etc/caddy/conf.d/chattoon.caddy && sudo systemctl reload caddy`
3. Roteador: apague as regras das portas 8443 e 80.
4. Se usou DDNS: `systemctl --user disable --now cloudflare-ddns.timer`, apague o script e
   revogue o token na Cloudflare.
