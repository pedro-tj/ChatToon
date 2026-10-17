# 33 — OBS: neste computador e na rede local

## Problema

O servidor do overlay escuta só em `127.0.0.1`. Trocar o IP no endereço por `192.168.x.y` não
funciona: nada escuta nesse endereço, e o *guard* recusaria o cabeçalho Host.

## Solução

"Onde está o seu OBS Studio?" → **Neste computador** · **Outro computador na mesma rede** ·
**Outro computador pela internet** ([34](34-remote-access-privacy.md)).

**Rede local (opcional, desligada por padrão, pede consentimento):**

* `core/network.py` lista os IPv4 por `ip -j addr` e classifica cada interface pelo `/sys`
  (cabo, Wi-Fi, VPN — ZeroTier/Tailscale/WireGuard —, virtual — Docker/libvirt/pontes) e pelo
  escopo (privado, CGNAT, link-local, público). A interface da rota padrão vem primeiro
  (`ip route get` só consulta a tabela local; nada é enviado). Só cabo/Wi-Fi privados são
  oferecidos no modo simples; o avançado mostra os demais.
* `OverlayServer.set_lan(ip, prefixo)` abre **um** listener extra nesse IP (nunca `0.0.0.0`),
  na mesma porta real do servidor. Pedidos que chegam por ele só são atendidos se:
  o cabeçalho Host for exatamente esse IP (contra DNS rebinding), o IP de quem pede estiver
  **na mesma sub-rede** (um encaminhamento de porta vindo da internet é recusado) e o token
  estiver certo. A CSP permite o WebSocket desse endereço. O WebSocket passa pelo mesmo guard.
* Se o endereço sumir (outro Wi-Fi, cabo desligado), o listener é fechado e a interface avisa
  ("este endereço não está mais neste computador").
* **Firewall**: detecta `ufw`/`firewalld` ativos (o computador de validação tem `ufw`). Mostra o
  comando exato e, com consentimento, executa por `pkexec` uma regra **só para a sub-rede**:
  `ufw allow from 192.168.0.0/24 to any port 8765 proto tcp comment "ChatToon overlay"`.
* **Testar deste computador**: busca o endereço da LAN; prova que o listener e o guard funcionam.
  Não prova o firewall (tráfego local não passa por ele) — a interface diz isso.
* **Novo endereço secreto** (avançado): troca o token e reinicia o servidor; todo link antigo
  passa a dar 404.

**Endereços sempre reais:** a porta mostrada é a que o servidor conseguiu abrir (8765, ou a
próxima livre). Validado ao vivo: com a 8765 ocupada pela instância já aberta, a segunda abriu
na **8766** e a página mostrou `http://127.0.0.1:8766/o/••••••/`.

**Papéis no WebSocket:** `obs` (único que recebe áudio), `preview`, `browser`, `desktop`
(assistem) e `probe` (teste de conexão: recebe `hello` e é fechado, sem ser contado).

## Arquivos

`core/overlay_server.py`, `core/network.py`, `core/engine.py` (`apply_network`, `rotate_token`),
`gui/connectivity.py`, `qml/ObsAccess.qml`, `qml/SecretField.qml`, `qml/pages/ObsPage.qml`.

## Testes

`tests/test_overlay_network.py` — listener em 127.0.0.2 (Linux responde todo 127.0.0.0/8):
200 com o Host certo, 403 com outro Host, 403 para cliente fora da sub-rede, 404 com token
errado, desligar fecha mesmo o listener, erros de endereço, papéis `desktop`/`probe`, token novo
invalida o antigo, porta ocupada; `tests/test_system_network.py` — classificação das interfaces e
comandos de firewall.

**Não executado:** um OBS real em outro computador da LAN e a mudança real do `ufw` (pede senha).
Para verificar: ligar a rede local, liberar o firewall, abrir o endereço da LAN no navegador do
outro computador (deve mostrar o personagem; com outro Host ou de outra rede, `forbidden`).
