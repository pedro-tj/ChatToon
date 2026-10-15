"""What each character knows and says on its own: curiosities, invitations and asides.

Lines are data, not code scattered around: each one has a *kind* so the avatar never
presents fiction as fact.

* ``fact`` — true and checkable (penguins, worms, owls, Linux history…). Spoken as
  written: the model never rewrites a fact, so it cannot distort it;
* ``fiction`` — the character's own lore ("on my planet…"), clearly a joke;
* ``invite``, ``humor``, ``reflection`` — invitations to talk and idle asides;
* ``channel`` — lines the streamer added (Characters › Curiosities), trusted as theirs.

Streamers extend it per character in the interface; nothing has to be edited here.
"""

from __future__ import annotations

import re
import zlib
from dataclasses import dataclass

CATEGORIES = ("invite", "curiosity", "context", "humor", "catchphrase", "cta", "reflection")


@dataclass(frozen=True)
class Line:
    text: str
    kind: str  # fact | fiction | invite | humor | reflection | channel
    category: str  # one of CATEGORIES

    @property
    def id(self) -> str:
        return f"{self.category}:{zlib.crc32(self.text.encode()):08x}"  # stable between runs


def _lines(category: str, kind: str, texts: tuple[str, ...]) -> list[Line]:
    return [Line(t, kind, category) for t in texts]


# -- shared Linux and free-software facts (said by the techie characters) --------------

_LINUX_FACTS = {
    "pt-BR": (
        "Linus Torvalds anunciou o Linux em 1991, numa mensagem para um grupo de discussão na internet.",
        "O Git, que quase todo programador usa, também foi criado pelo Linus Torvalds, em 2005.",
        "Desde 2017, todos os quinhentos supercomputadores mais rápidos do mundo rodam Linux.",
        "O Android usa o kernel Linux por baixo dos panos.",
        "O kernel Linux é escrito principalmente em C, e hoje também aceita partes em Rust.",
        "O BigLinux é uma distribuição brasileira baseada no Manjaro.",
    ),
    "en": (
        "Linus Torvalds announced Linux in 1991, in a message to an internet discussion group.",
        "Git, used by almost every programmer, was also created by Linus Torvalds, in 2005.",
        "Since 2017, all of the world's five hundred fastest supercomputers run Linux.",
        "Android runs on the Linux kernel under the hood.",
        "The Linux kernel is written mostly in C, and nowadays it also accepts parts in Rust.",
    ),
}

BANK: dict[str, dict[str, list[Line]]] = {
    "tux": {
        "pt-BR": [
            *_lines("curiosity", "fact", (
                "Vocês sabiam que eu virei o mascote do Linux em 1996? Quem me desenhou foi o Larry Ewing, usando o GIMP.",
                "O próprio Linus Torvalds conta que gosta de pinguins desde que foi bicado por um num zoológico. "
                "Eu prefiro acreditar que foi um beijinho.",
                "Pinguins não voam, mas o pinguim-gentoo nada a mais de trinta quilômetros por hora. Eu prefiro navegar "
                "pelos repositórios!",
                "O pinguim-imperador consegue mergulhar a mais de quinhentos metros de profundidade. Eu mergulho no "
                "código-fonte, que é mais quentinho.",
                "Dizem que o meu nome, Tux, vem de Torvalds UniX. Elegante até no nome, meu caro!",
                *_LINUX_FACTS["pt-BR"],
            )),
            *_lines("curiosity", "fiction", (
                "Minha cartola tem um compartimento secreto só para guardar pendrive bootável. Nunca se sabe quando "
                "alguém vai precisar!",
                "Eu passo as férias na Antártida compilando kernel no frio, que é pra CPU não esquentar.",
            )),
            *_lines("invite", "invite", (
                "Ei, você aí! Já fez uma pergunta pra mim hoje? Pode mandar, que eu respondo com toda a elegância.",
                "Alguém quer conversar sobre Linux? Prometo tentar não falar mal do Windows... tentar!",
                "O chat está tão silencioso que consigo ouvir os elétrons passando pelo processador! Manda uma "
                "mensagem aí.",
                "Tenho uma curiosidade guardada na cartola. Alguém quer ouvir? Escreve aí no chat!",
                "Prezados espectadores, este pinguim aceita perguntas de terminal, de distro e até de filosofia.",
            )),
            *_lines("humor", "humor", (
                "Ué, cadê todo mundo? Estão compilando o kernel ou foram buscar café?",
                "Enquanto vocês pensam numa pergunta, vou aproveitar para organizar meus bits.",
            )),
            *_lines("reflection", "reflection", (
                "Às vezes eu fico pensando: se um pinguim usa cartola, por que um sistema não pode ser livre?",
                "Silêncio no chat... deve ser todo mundo atualizando o sistema. Sem reiniciar, espero!",
            )),
        ],
        "en": [
            *_lines("curiosity", "fact", (
                "Did you know I became the Linux mascot in 1996? Larry Ewing drew me, using the GIMP.",
                "Penguins can't fly, but gentoo penguins swim faster than thirty kilometres per hour. I'd rather "
                "surf the repositories!",
                "Emperor penguins can dive deeper than five hundred metres. I dive into source code instead.",
                *_LINUX_FACTS["en"],
            )),
            *_lines("curiosity", "fiction", (
                "My top hat has a secret pocket just for a bootable USB stick. You never know!",
            )),
            *_lines("invite", "invite", (
                "Hey, you there! Have you asked me anything today? Go ahead, I answer with style.",
                "Anyone up for some Linux talk? I promise to try not to tease Windows... try!",
                "The chat is so quiet I can hear the electrons in the CPU! Send a message.",
            )),
            *_lines("humor", "humor", (
                "Where did everybody go? Compiling a kernel or grabbing coffee?",
                "While you think of a question, I'll tidy up my bits.",
            )),
        ],
    },
    "worm": {
        "pt-BR": [
            *_lines("curiosity", "fact", (
                "Vocês sabiam que as minhocas ajudam a arejar e adubar o solo? É praticamente uma manutenção "
                "preventiva da natureza!",
                "Minhoca respira pela pele, criatura! Por isso eu vivo úmida e cheia de charme.",
                "O Charles Darwin escreveu um livro inteirinho sobre minhocas, em 1881. Fã de carteirinha!",
                "Minhoca não tem olhos, mas sente a luz pela pele. Eu sei quando você liga a lanterna do celular!",
                "O húmus de minhoca é um dos melhores adubos que existem. Eu literalmente transformo lixo em ouro.",
            )),
            *_lines("curiosity", "fiction", (
                "Eu vivo debaixo da terra, mas meu conhecimento de tecnologia está nas nuvens!",
                "Lá embaixo a internet é cabeada de verdade: eu mesma passo os cabos.",
            )),
            *_lines("invite", "invite", (
                "Ô criatura, esse chat tá mais parado que minhoca no asfalto! Manda uma pergunta aí.",
                "Ei, você que tá só olhando! Fala comigo, que eu não mordo... nem tenho dente.",
                "Alguém aí quer conversar? Prometo que não vou zoar muito. Talvez um pouquinho.",
            )),
            *_lines("humor", "humor", (
                "Silêncio no chat... vou aproveitar e cavar um túnel até a próxima pergunta.",
                "Tô aqui me espreguiçando, que minhoca parada vira isca!",
            )),
            *_lines("reflection", "reflection", (
                "Às vezes eu penso: vocês na superfície reclamam do trânsito, e eu aqui só tenho uma direção: pra frente.",
            )),
        ],
        "en": [
            *_lines("curiosity", "fact", (
                "Did you know earthworms aerate and fertilize the soil? Nature's preventive maintenance!",
                "Worms breathe through their skin, buddy! That's why I stay moist and fabulous.",
                "Charles Darwin wrote a whole book about earthworms, in 1881. A true fan!",
            )),
            *_lines("invite", "invite", (
                "Hey, this chat is quieter than a worm on asphalt! Send a question.",
                "You, just watching! Talk to me, I don't bite... I don't even have teeth.",
            )),
            *_lines("humor", "humor", ("Quiet chat... I'll dig a tunnel to the next question.",)),
        ],
    },
    "alien": {
        "pt-BR": [
            *_lines("curiosity", "fact", (
                "Dado terráqueo interessante: a luz do Sol leva uns oito minutos para chegar até vocês.",
                "Fascinante: em Vênus, um dia dura mais do que um ano inteiro. Imagina esperar o fim de semana lá!",
                "A Estação Espacial Internacional dá uma volta na Terra a cada noventa minutos, mais ou menos. "
                "Quase tão rápido quanto a minha nave estacionando.",
                "As sondas Voyager, lançadas por vocês em 1977, já saíram da bolha de vento do Sol. Mandaram até um "
                "disco de ouro com músicas. Eu ainda estou ouvindo!",
            )),
            *_lines("curiosity", "fiction", (
                "Na minha galáxia ninguém usa Windows. Não porque seja proibido, mas porque até os alienígenas gostam "
                "de liberdade!",
                "Vocês chamam isso de inteligência artificial? No meu planeta chamamos de terça-feira!",
                "Lá no meu planeta, o maior insulto é chamar alguém de driver proprietário.",
            )),
            *_lines("invite", "invite", (
                "Atenção, terráqueos! Meus sensores não detectam mensagens no chat. Transmitam alguma coisa!",
                "Humanos, estou coletando dados para a minha pesquisa. Me contem: o que vocês estão fazendo agora?",
                "Alguém quer perguntar algo para um extraterrestre de verdade? A oferta acaba quando minha nave decolar!",
            )),
            *_lines("humor", "humor", (
                "Silêncio total no chat. No meu planeta isso significa que todos foram abduzidos.",
                "Enquanto vocês pensam, vou recalibrar minhas antenas. Bip, bop!",
            )),
            *_lines("reflection", "reflection", (
                "Observação científica: humanos olham para uma tela e chamam isso de descanso. Intrigante.",
            )),
        ],
        "en": [
            *_lines("curiosity", "fact", (
                "Interesting Earth data: sunlight takes about eight minutes to reach you.",
                "Fascinating: on Venus a day lasts longer than a whole year.",
            )),
            *_lines("curiosity", "fiction", (
                "In my galaxy nobody uses Windows. Not because it's forbidden — even aliens love freedom!",
                "You call that artificial intelligence? On my planet we call it Tuesday!",
            )),
            *_lines("invite", "invite", (
                "Attention, earthlings! My sensors detect no chat messages. Transmit something!",
            )),
            *_lines("humor", "humor", ("Total silence. On my planet that means everyone got abducted.",)),
        ],
    },
    "cat": {
        "pt-BR": [
            *_lines("curiosity", "fact", (
                "Os gatos dormem de doze a dezesseis horas por dia. Eu considero isso uma técnica avançada de economia "
                "de energia.",
                "Gatos adultos miam principalmente para conversar com humanos, não com outros gatos. Sintam-se "
                "privilegiados.",
                "O ronronar de um gato vibra mais ou menos entre vinte e cinco e cento e cinquenta hertz. Melhor que "
                "muita caixa de som por aí.",
                "Os bigodes ajudam o gato a perceber se cabe num espaço. Eu chamo isso de sensor de caixa de papelão.",
            )),
            *_lines("curiosity", "fiction", (
                "Vocês acham que humanos inventaram o modo repouso? Nós, gatos, usamos isso há milhares de anos!",
                "Sou uma gata tão tecnológica que até minhas sete vidas têm backup.",
            )),
            *_lines("invite", "invite", (
                "Humanos. Estou entediada. Alguém aí vai me fazer uma pergunta decente ou vou ter que derrubar algo da mesa?",
                "O chat está quieto. Isso é um convite para eu dormir no teclado. Última chance de falar comigo.",
                "Pode perguntar. Eu finjo que não estou interessada, mas respondo.",
            )),
            *_lines("humor", "humor", (
                "Silêncio no chat. Perfeito. Vou lamber a pata e fingir que não estou esperando ninguém.",
                "Se ninguém falar nada em cinco minutos, eu derrubo o copo. Estou avisando.",
            )),
            *_lines("reflection", "reflection", (
                "Às vezes eu me pergunto por que vocês chamam de mouse uma coisa que eu nem posso caçar.",
            )),
        ],
        "en": [
            *_lines("curiosity", "fact", (
                "Cats sleep twelve to sixteen hours a day. I call it advanced energy saving.",
                "Adult cats meow mostly to talk to humans, not to other cats. Feel privileged.",
            )),
            *_lines("invite", "invite", (
                "Humans. I'm bored. Is anyone asking me a decent question, or do I knock something off the desk?",
            )),
            *_lines("humor", "humor", ("Quiet chat. Perfect. I'll lick my paw and pretend I'm not waiting.",)),
        ],
    },
    "owl": {
        "pt-BR": [
            *_lines("curiosity", "fact", (
                "Uhuuu! Muitas corujas voam quase em silêncio, graças às bordas serrilhadas das penas. É o modo "
                "stealth da natureza!",
                "As corujas não conseguem mexer os olhos dentro da cabeça. Por isso giram o pescoço até uns duzentos e "
                "setenta graus.",
                "A coruja virou símbolo da sabedoria por causa da deusa grega Atena. Eu só aproveito a fama!",
                "Os olhos da coruja têm formato de tubo, não de bola. Por isso o olhar é tão... intenso.",
                *_LINUX_FACTS["pt-BR"],
            )),
            *_lines("curiosity", "fiction", (
                "As corujas são associadas à sabedoria. Eu prefiro dizer que tenho um ótimo sistema de busca!",
            )),
            *_lines("invite", "invite", (
                "Uhuuu! Aula aberta: qualquer pergunta sobre tecnologia, Linux ou ciência, é só mandar no chat.",
                "Estou de olhos bem abertos esperando uma pergunta. E olha que meus olhos são grandes!",
                "Quem quer uma curiosidade fresquinha? Manda um sim no chat!",
            )),
            *_lines("humor", "humor", (
                "Chat silencioso... perfeito para uma coruja. Mas eu prefiro conversa!",
            )),
            *_lines("reflection", "reflection", (
                "Pensamento da madrugada: todo bug é só uma pergunta que ainda não foi bem feita.",
            )),
        ],
        "en": [
            *_lines("curiosity", "fact", (
                "Hoo-hoo! Many owls fly almost silently thanks to the serrated edges of their feathers. Nature's "
                "stealth mode!",
                "Owls can't move their eyes, so they turn their heads up to about two hundred seventy degrees.",
                *_LINUX_FACTS["en"],
            )),
            *_lines("invite", "invite", ("Hoo-hoo! Open class: any tech, Linux or science question, send it!",)),
            *_lines("humor", "humor", ("A silent chat... perfect for an owl. But I prefer a good talk!",)),
        ],
    },
    "dog": {
        "pt-BR": [
            *_lines("curiosity", "fact", (
                "Au au! O nariz de cada cachorro tem um desenho único, como uma impressão digital!",
                "O olfato dos cães é dezenas de milhares de vezes mais sensível que o de vocês, segundo os cientistas. "
                "Eu conseguiria achar um bug pelo cheiro!",
                "Cachorro ouve sons agudos que os humanos nem escutam. Eu ouço até a ventoinha do seu PC pedindo "
                "limpeza!",
                "Cachorro sua principalmente pelas patas, e se refresca ofegando. Por isso eu vivo de língua de fora!",
            )),
            *_lines("curiosity", "fiction", (
                "Um cachorro feliz abana o rabo. Eu abano quando o sistema atualiza sem quebrar nada!",
                "Eu enterrei um bug no quintal ontem. Se ele voltar, a culpa não é minha!",
            )),
            *_lines("invite", "invite", (
                "Au au! Cadê todo mundo? Fala comigo, fala! Qualquer coisa! Eu adoro qualquer coisa!",
                "Ei, você! É, você mesmo! Vamos brincar de pergunta e resposta? Eu busco a resposta igual bolinha!",
                "Chat parado deixa esse filhote ansioso! Manda uma mensagem, por favor, por favor!",
            )),
            *_lines("humor", "humor", (
                "Enquanto ninguém fala, vou correr atrás do meu rabo. Já volto! Ou não, ele é rápido.",
            )),
            *_lines("reflection", "reflection", (
                "Às vezes eu penso: será que o carteiro também usa Linux? Preciso investigar.",
            )),
        ],
        "en": [
            *_lines("curiosity", "fact", (
                "Woof! Every dog's nose has a unique pattern, like a fingerprint!",
                "Dogs hear high-pitched sounds humans can't. I can hear your PC fan begging for a cleanup!",
            )),
            *_lines("invite", "invite", ("Woof! Where is everybody? Talk to me! Anything! I love anything!",)),
            *_lines("humor", "humor", ("While nobody talks, I'll chase my tail. Be right back!",)),
        ],
    },
}

# Short answers built around a verified result when the model fails to say it.
ANSWER = {
    "tux": {"pt-BR": "{result}, meu caro! Conta resolvida com a elegância de um pinguim de cartola.",
            "en": "{result}, my dear viewer! Solved with top-hat elegance."},
    "worm": {"pt-BR": "Dá {result}, criatura! Até uma minhoca faz essa conta de cabeça.",
             "en": "It's {result}, buddy! Even a worm does that one in her head."},
    "alien": {"pt-BR": "O resultado é {result}, terráqueo! Meus sensores conferiram duas vezes.",
              "en": "The result is {result}, earthling! My sensors checked twice."},
    "cat": {"pt-BR": "{result}. Fácil. Agora posso voltar a dormir?",
            "en": "{result}. Easy. Can I go back to sleep now?"},
    "owl": {"pt-BR": "Uhuuu! O resultado é {result}. Matemática afiada como coruja à noite!",
            "en": "Hoo-hoo! The result is {result}. Sharp as an owl at night!"},
    "dog": {"pt-BR": "Au au! Dá {result}! Achei a resposta mais rápido que a bolinha!",
            "en": "Woof! It's {result}! Fetched that faster than a ball!"},
}

# Lines for when the model fails (not for forbidden topics: those use the deflections).
CONFUSED = {
    "tux": {"pt-BR": ("Deu um pequeno segmentation fault aqui no pinguim. Pode repetir com outras palavras?",
                      "Meu caro, essa travou no meu processador. Manda de novo, por gentileza?"),
            "en": ("Small segmentation fault in this penguin. Could you say it another way?",)},
    "worm": {"pt-BR": ("Deu um nó aqui no meu corpinho. Manda de novo, criatura?",
                       "Essa eu não consegui cavar. Escreve de outro jeito?"),
             "en": ("Got myself in a knot. Send it again, buddy?",)},
    "alien": {"pt-BR": ("Interferência cósmica! Não captei direito. Transmite de novo, humano?",),
              "en": ("Cosmic interference! Didn't catch that. Transmit again, human?",)},
    "cat": {"pt-BR": ("Fiquei com preguiça de entender essa. Tenta de novo que eu finjo que presto atenção.",),
            "en": ("Too lazy to get that one. Try again and I'll pretend to pay attention.",)},
    "owl": {"pt-BR": ("Meus olhos enormes não enxergaram essa direito. Escreve de novo?",),
            "en": ("My huge eyes missed that one. Write it again?",)},
    "dog": {"pt-BR": ("Au? Não entendi, mas abanei o rabo mesmo assim! Manda de novo?",),
            "en": ("Woof? Didn't get it, but I wagged my tail anyway! Send it again?",)},
}


def _pick(table: dict, language: str):
    return table.get(language) or table.get(language.split("-")[0]) or table.get("pt-BR") or next(iter(table.values()))


def lines(character_id: str, language: str, extra: list[str] | None = None) -> list[Line]:
    """Every spontaneous line of a character, plus the streamer's own curiosities."""
    bank = BANK.get(character_id) or {}
    out = list(_pick(bank, language) if bank else [])
    for text in extra or []:
        text = " ".join(str(text).split())
        if 8 <= len(text) <= 300:
            out.append(Line(text, "channel", "curiosity"))
    return out


def answer(character_id: str, language: str, result: str) -> str:
    return _pick(ANSWER.get(character_id, ANSWER["tux"]), language).format(result=result)


def confused(character_id: str, language: str) -> tuple[str, ...]:
    return _pick(CONFUSED.get(character_id, CONFUSED["tux"]), language)


# -- verified reference sheet -------------------------------------------------------------
#
# A small, checked fact sheet about computing and Linux — the subjects of the channels
# ChatToon was made for. When an objective question mentions one of these subjects, the
# matching entries go to the model as "verified reference" (a tiny local retrieval: no
# embeddings, no download). The model still writes the answer in the character's voice;
# small local models just stop guessing what an acronym stands for.

REFERENCE: tuple[tuple[str, str, str], ...] = (
    # (pattern on accent-folded text, Portuguese, English)
    (r"\bcpu\b|\bprocessador\b", "CPU é a sigla de Central Processing Unit, em português Unidade Central de "
     "Processamento: o processador, que executa as instruções dos programas.",
     "CPU stands for Central Processing Unit: the processor, which runs the programs' instructions."),
    (r"\bgpu\b|placa de video", "GPU é a sigla de Graphics Processing Unit, Unidade de Processamento Gráfico: o chip da "
     "placa de vídeo, que desenha os gráficos e também faz cálculos em paralelo.",
     "GPU stands for Graphics Processing Unit: the graphics card's chip, which draws graphics and also runs parallel "
     "computations."),
    (r"\bram\b|memoria ram", "RAM é a sigla de Random Access Memory, memória de acesso aleatório: a memória rápida e "
     "temporária onde ficam os programas abertos; ela se apaga quando o computador desliga.",
     "RAM stands for Random Access Memory: fast, temporary memory for running programs; it is erased at power off."),
    (r"\bssd\b", "SSD é a sigla de Solid State Drive, unidade de estado sólido: armazenamento sem partes móveis, bem "
     "mais rápido que um HD.", "SSD stands for Solid State Drive: storage without moving parts, much faster than a hard "
     "disk."),
    (r"\bhdd?\b|disco rigido", "HD (Hard Disk) é o disco rígido: guarda os dados em discos magnéticos que giram; é mais "
     "lento que um SSD.", "An HDD (hard disk drive) stores data on spinning magnetic platters; slower than an SSD."),
    (r"\busb\b", "USB é a sigla de Universal Serial Bus, barramento serial universal: o padrão de conexão de periféricos.",
     "USB stands for Universal Serial Bus, the standard connector for peripherals."),
    (r"\bbios\b|\buefi\b", "BIOS e UEFI são o firmware da placa-mãe que liga o computador antes do sistema operacional; o "
     "UEFI é o sucessor moderno do BIOS.", "BIOS and UEFI are the motherboard firmware that starts the computer before "
     "the operating system; UEFI is BIOS's modern successor."),
    (r"\bhtml\b", "HTML é a sigla de HyperText Markup Language, linguagem de marcação de hipertexto: estrutura as páginas "
     "da web.", "HTML stands for HyperText Markup Language: it structures web pages."),
    (r"\burl\b", "URL é o endereço de uma página ou recurso na internet (Uniform Resource Locator).",
     "A URL (Uniform Resource Locator) is the address of a page or resource on the internet."),
    (r"\bdns\b", "DNS é o sistema que traduz nomes de sites em endereços IP (Domain Name System).",
     "DNS (Domain Name System) translates site names into IP addresses."),
    (r"\bo que (e|eh) (o )?linux\b|\blinux (e|eh) o que\b|\bwhat is linux\b",
     "Linux é um kernel, o núcleo de um sistema operacional, livre e criado por Linus Torvalds em 1991; junto com "
     "outros programas forma sistemas completos, as distribuições.", "Linux is a free operating system kernel created "
     "by Linus Torvalds in 1991; with other software it forms complete systems, the distributions."),
    (r"\bkernel\b|\bnucleo\b", "O kernel é o núcleo do sistema operacional: controla o hardware, a memória e os processos.",
     "The kernel is the core of the operating system: it controls hardware, memory and processes."),
    (r"\bdistro\b|\bdistribuic", "Uma distribuição Linux (distro) é um sistema operacional completo montado em volta do "
     "kernel Linux, como Ubuntu, Fedora, Debian, Arch, Manjaro e BigLinux.", "A Linux distribution (distro) is a "
     "complete operating system built around the Linux kernel, like Ubuntu, Fedora, Debian, Arch, Manjaro or BigLinux."),
    (r"\bbiglinux\b", "O BigLinux é uma distribuição Linux brasileira baseada diretamente no Manjaro (o Manjaro é que "
     "deriva do Arch Linux); usa o KDE Plasma.", "BigLinux is a Brazilian Linux distribution based on Manjaro (itself derived from Arch "
     "Linux); it uses KDE Plasma."),
    (r"\bmanjaro\b", "O Manjaro é uma distribuição baseada no Arch Linux, focada em facilidade de uso.",
     "Manjaro is an Arch-based distribution focused on ease of use."),
    (r"\barch\b", "O Arch Linux é uma distribuição minimalista de atualização contínua (rolling release); seu "
     "gerenciador de pacotes é o pacman.", "Arch Linux is a minimalist rolling-release distribution; its package "
     "manager is pacman."),
    (r"\bpacman\b|gerenciador de pacotes", "O pacman é o gerenciador de pacotes do Arch Linux e de derivados como Manjaro "
     "e BigLinux; Debian e Ubuntu usam o apt; o Fedora usa o dnf.", "pacman is the package manager of Arch Linux and "
     "derivatives like Manjaro and BigLinux; Debian and Ubuntu use apt; Fedora uses dnf."),
    (r"\bkde\b|\bplasma\b", "O KDE Plasma é um ambiente de desktop: a interface gráfica com área de trabalho, painel e "
     "janelas, feita pela comunidade KDE.", "KDE Plasma is a desktop environment (the graphical desktop, panel and "
     "windows) made by the KDE community."),
    (r"\bgnome\b", "O GNOME é um ambiente de desktop para Linux, o padrão do Ubuntu e do Fedora.",
     "GNOME is a Linux desktop environment, the default on Ubuntu and Fedora."),
    (r"\bwayland\b|\bx11\b|\bxorg\b", "O Wayland é o protocolo gráfico moderno do Linux, que substitui o antigo X11 "
     "(Xorg) na comunicação entre os aplicativos e a tela.", "Wayland is Linux's modern display protocol, replacing "
     "the old X11 (Xorg) between applications and the screen."),
    (r"\bterminal\b|\bshell\b|\bbash\b", "O terminal é onde se digitam comandos de texto; o shell, como o Bash, "
     "interpreta esses comandos.", "The terminal is where text commands are typed; a shell such as Bash interprets "
     "them."),
    (r"\blist\w*\b.{0,30}\b(arquivo|pasta|diretorio)|\bcomando ls\b|\bls\b", "No terminal, o comando ls lista os "
     "arquivos e pastas de um diretório.", "In the terminal, the ls command lists a directory's files and folders."),
    (r"\b(mud\w*|troc\w*|entr\w*)\b.{0,20}\b(diretorio|pasta)|\bcomando cd\b", "No terminal, o comando cd muda de "
     "diretório (pasta).", "In the terminal, the cd command changes directory."),
    (r"\b(pasta|diretorio)\b.{0,20}\b(atual|estou)|\bpwd\b", "No terminal, o comando pwd mostra o diretório (pasta) "
     "atual.", "In the terminal, the pwd command prints the current directory."),
    (r"\bsudo\b|\badministrador\b|\broot\b", "O sudo executa um comando com privilégios de administrador (root).",
     "sudo runs a command with administrator (root) privileges."),
    (r"\bgit\b|\bgithub\b", "O Git é um sistema de controle de versão criado por Linus Torvalds em 2005; o GitHub é um "
     "serviço na web para hospedar repositórios Git.", "Git is a version control system created by Linus Torvalds in "
     "2005; GitHub is a web service that hosts Git repositories."),
    (r"\bmascote\b|\b(o que|quem) (e|eh) o tux\b", "O Tux, um pinguim, é o mascote oficial do Linux, desenhado por Larry Ewing em 1996.",
     "Tux the penguin is the official Linux mascot, drawn by Larry Ewing in 1996."),
    (r"\bquem (criou|inventou|fez)\b.{0,10}\blinux\b|\blinus\b|\btorvalds\b", "O Linux foi criado por Linus Torvalds, "
     "que o anunciou em 1991.", "Linux was created by Linus Torvalds, who announced it in 1991."),
    (r"software livre|codigo aberto|open ?source|free software", "Software livre dá a todos a liberdade de usar, estudar, "
     "modificar e distribuir o programa; código aberto é um conceito parecido, centrado no código-fonte disponível.",
     "Free software gives everyone the freedom to use, study, change and share the program; open source is a similar "
     "idea centred on available source code."),
    (r"\bgpl\b|\blicenca\b", "A GPL é a licença de software livre da Free Software Foundation; o kernel Linux usa a GPL "
     "versão 2.", "The GPL is the Free Software Foundation's free software license; the Linux kernel uses GPL version 2."),
    (r"\bpython\b", "Python é uma linguagem de programação de sintaxe simples, muito usada em automação, ciência de dados "
     "e inteligência artificial.", "Python is a programming language with simple syntax, widely used for automation, "
     "data science and AI."),
    (r"\bqml\b|\bqt\b", "Qt é um framework em C++ para criar aplicativos com interface gráfica, e QML é a linguagem "
     "declarativa do Qt para desenhar essas interfaces; o KDE é feito com Qt.", "Qt is a C++ framework for graphical "
     "applications, and QML is Qt's declarative language for user interfaces; KDE is built with Qt."),
    (r"\brust\b", "Rust é uma linguagem de programação focada em segurança de memória e desempenho; o kernel Linux "
     "aceita partes em Rust.", "Rust is a programming language focused on memory safety and performance; the Linux "
     "kernel accepts parts in Rust."),
    (r"linguagem.{0,40}\bkernel\b|\bkernel\b.{0,40}linguagem", "O kernel Linux é escrito principalmente na linguagem C, "
     "com partes em assembly e, mais recentemente, em Rust.", "The Linux kernel is written mostly in C, with some "
     "assembly and, recently, Rust."),
    (r"\bollama\b|\bllm\b|modelo de linguagem", "O Ollama roda modelos de linguagem (LLMs, a inteligência artificial que "
     "gera texto) no próprio computador, sem nuvem.", "Ollama runs language models (LLMs, the AI that generates text) on "
     "the computer itself, no cloud."),
    (r"\bobs\b", "O OBS Studio é um programa livre de gravação e transmissão ao vivo.",
     "OBS Studio is a free program for recording and live streaming."),
    (r"\bproton\b|\bwine\b|jogos? (de windows )?no linux", "O Wine roda programas de Windows no Linux, e o Proton, da "
     "Valve, é baseado no Wine e roda jogos de Windows pela Steam.", "Wine runs Windows programs on Linux, and Valve's "
     "Proton, based on Wine, runs Windows games through Steam."),
    (r"\bandroid\b", "O Android é o sistema operacional para celulares mantido pelo Google, e usa o kernel Linux.",
     "Android is the mobile operating system maintained by Google, and it runs the Linux kernel."),
    (r"\bfirefox\b|\bmozilla\b", "O Firefox é o navegador livre da Mozilla.", "Firefox is Mozilla's free web browser."),
    (r"\bapt\b|\bubuntu\b|\bdebian\b", "O Ubuntu é baseado no Debian, e os dois usam o apt como gerenciador de pacotes.",
     "Ubuntu is based on Debian, and both use apt as their package manager."),
)

_REFERENCE = [(re.compile(pattern), pt, en) for pattern, pt, en in REFERENCE]


def reference(text: str, language: str = "pt-BR", limit: int = 2) -> list[str]:
    """Verified entries about the subjects of ``text`` (most specific first)."""
    from .intent import fold

    folded = fold(text)
    pt = language.lower().startswith("pt")
    found = [(m.end() - m.start(), pt_text if pt else en_text) for rx, pt_text, en_text in _REFERENCE
             if (m := rx.search(folded))]
    out: list[str] = []
    for _, entry in sorted(found, key=lambda f: -f[0]):
        if entry not in out:
            out.append(entry)
    return out[:limit]
