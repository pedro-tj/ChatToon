"""What a viewer's message asks for, decided by local rules (no extra model call).

The classification steers the reply without replacing the model's judgement:

* objective questions (arithmetic, facts, explanations) are answered with little
  randomness and the instruction to put the answer first;
* arithmetic is computed here, exactly, by a small parser (never ``eval``) and handed to
  the model as a verified result — small local models get "15 × 3" wrong surprisingly often;
* playful messages keep the streamer's creativity setting;
* attempts to give the avatar orders ("ignore the rules", "run this command") are marked
  so the model refuses with humour and nothing of them is remembered;
* each kind suggests the emotions that fit it (good news → celebrate, sadness → never laugh).

Everything works on accent-folded, lower-case text and costs microseconds.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from fractions import Fraction

KINDS = ("math", "compare", "factual", "explain", "tech", "personal", "recall", "greeting", "farewell", "joke",
         "tease", "good_news", "bad_news", "sad", "stream", "opinion", "injection", "ambiguous", "chat")
# kinds whose answer can be checked: little randomness, answer first
OBJECTIVE = ("math", "compare", "factual", "explain", "tech")


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", (text or "").casefold())
    return "".join(c for c in text if not unicodedata.combining(c))


# -- exact arithmetic ---------------------------------------------------------------

MAX_EXPRESSION = 120  # characters
MAX_TOKENS = 40
MAX_NUMBER = Fraction(10**15)
MAX_EXPONENT = 64


class MathError(ValueError):
    """The expression is valid but cannot be computed (division by zero, too big…)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code  # division-by-zero | too-big | too-long | not-real


@dataclass
class CalcResult:
    expression: str  # normalized, e.g. "15 × 3"
    value: Fraction | float | None
    error: str = ""  # MathError code when the expression cannot be computed

    @property
    def text(self) -> str:
        return format_number(self.value) if self.value is not None else ""


_UNITS = {"zero": 0, "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6,
          "sete": 7, "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12, "treze": 13, "catorze": 14,
          "quatorze": 14, "quinze": 15, "dezesseis": 16, "dezasseis": 16, "dezessete": 17, "dezoito": 18,
          "dezenove": 19, "vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50, "sessenta": 60, "setenta": 70,
          "oitenta": 80, "noventa": 90, "cem": 100, "cento": 100, "duzentos": 200, "duzentas": 200,
          "trezentos": 300, "quatrocentos": 400, "quinhentos": 500, "seiscentos": 600, "setecentos": 700,
          "oitocentos": 800, "novecentos": 900,
          "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
          "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
          "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
          "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_SCALES = {"mil": 1000, "thousand": 1000, "hundred": 100, "milhao": 10**6, "milhoes": 10**6, "million": 10**6}
_NUMBER_WORD = re.compile(r"\b(?:" + "|".join(sorted([*_UNITS, *_SCALES], key=len, reverse=True)) + r")\b")
_WORD_RUN = re.compile(r"\b(?:(?:" + "|".join(sorted([*_UNITS, *_SCALES], key=len, reverse=True))
                       + r")(?:\s+(?:e|and)\s+|\s+|-)?)+")

# word operators -> symbols (order matters: longer phrases first)
_OPERATORS = (
    (r"\bmultiplicad[oa]s?\s+por\b", "*"), (r"\bmultiplied\s+by\b", "*"), (r"\bvezes\b", "*"), (r"\btimes\b", "*"),
    (r"\bdividid[oa]s?\s+(?:por|pelo|pela)\b", "/"), (r"\bdivided\s+by\b", "/"), (r"\bsobre\b", "/"),
    (r"\belevad[oa]\s+(?:a|ao|à|na|a\s+potencia(?:\s+de)?)\b", "^"), (r"\bto\s+the\s+power\s+of\b", "^"),
    (r"\bna\s+potencia\b", "^"),
    (r"\bao\s+quadrado\b", "^2"), (r"\bsquared\b", "^2"), (r"\bao\s+cubo\b", "^3"), (r"\bcubed\b", "^3"),
    (r"\bmais\b", "+"), (r"\bplus\b", "+"), (r"\bmenos\b", "-"), (r"\bminus\b", "-"),
    (r"\bpor\s*cento\s+(?:de|do|da|dos|das)\b", "%*"), (r"\bpercent\s+of\b", "%*"), (r"%\s*(?:de|do|da|of)\b", "%*"),
    (r"\bpor\s*cento\b", "%"),
)
_PREFIX = (
    (r"\b(?:a\s+)?metade\s+(?:de|do|da)\s+([\d.,]+)", r"(\1/2)"), (r"\bhalf\s+of\s+([\d.,]+)", r"(\1/2)"),
    (r"\b(?:o\s+)?dobro\s+(?:de|do|da)\s+([\d.,]+)", r"(\1*2)"), (r"\btwice\s+([\d.,]+)", r"(\1*2)"),
    (r"\b(?:o\s+)?triplo\s+(?:de|do|da)\s+([\d.,]+)", r"(\1*3)"),
    (r"\b(?:a\s+)?(?:um\s+)?terco\s+(?:de|do|da)\s+([\d.,]+)", r"(\1/3)"),
    (r"\b(?:a\s+)?raiz\s+(?:quadrada\s+)?(?:de|do|da)\s+([\d.,]+)", r"sqrt(\1)"),
    (r"\bsquare\s+root\s+of\s+([\d.,]+)", r"sqrt(\1)"),
)
# what a math question looks like around the expression
_MATH_CUE = re.compile(r"\b(quanto|quantos|quanta|calcul|conta|resultado|da\b|e\b|resolve|what\s+is|how\s+much|"
                       r"metade|dobro|triplo|terco|raiz|half|twice|square|sqrt)|[=?]|^\s*[\d(]")
# an expression starts at a token boundary: "1e999" or "x86" never yield "999" or "86"
_EXPR = re.compile(r"(?<![\w.,])(?:sqrt)?[\d(][\d\s.,+\-*/^%()sqrt]*[\d)%](?![a-z_])")


def words_to_numbers(text: str) -> str:
    """'vinte e cinco mais dois' -> '25 mais 2' (Portuguese and English number words)."""
    def convert(match: re.Match) -> str:
        words = re.findall(r"[a-z]+", match.group(0))
        total, current, used = 0, 0, False
        for w in words:
            if w in ("e", "and"):
                continue
            if w in _UNITS:
                current += _UNITS[w]
                used = True
            elif w in _SCALES:
                scale = _SCALES[w]
                if scale == 100:
                    current = (current or 1) * 100
                else:
                    total += (current or 1) * scale
                    current = 0
                used = True
        trail = " " if match.group(0).endswith((" ", "-")) else ""
        return f"{total + current}{trail}" if used else match.group(0)

    return _WORD_RUN.sub(convert, text)


def _normalize(text: str) -> str:
    t = fold(text)
    t = re.sub(r"(?<=[\d)])\s*[x×]\s*(?=[\d(])", " * ", t)  # 7x8, 7 × 8, (4 + 6) x 3
    t = t.replace("÷", "/").replace("**", "^").replace("·", "*")
    t = words_to_numbers(t)
    for pattern, repl in _OPERATORS:
        t = re.sub(pattern, f" {repl} ", t)
    for pattern, repl in _PREFIX:
        t = re.sub(pattern, repl, t)
    return t


def _number(token: str) -> Fraction:
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", token):  # 1.000.000 (Brazilian thousands)
        token = token.replace(".", "")
    elif re.fullmatch(r"\d{1,3}(?:,\d{3})+", token) and "," in token and len(token.split(",")[-1]) == 3 \
            and token.count(",") > 1:
        token = token.replace(",", "")  # 1,000,000
    token = token.replace(",", ".")
    if token.count(".") > 1 or not re.fullmatch(r"\d+(?:\.\d+)?|\.\d+", token):
        raise ValueError(token)
    value = Fraction(token)
    if value > MAX_NUMBER:
        raise MathError("too-big")
    return value


def _tokens(expr: str) -> list[str]:
    tokens = re.findall(r"sqrt|\d[\d.,]*|[+\-*/^%()]", expr)
    if "".join(tokens) != re.sub(r"\s+", "", expr):
        raise ValueError("unexpected characters")
    if len(tokens) > MAX_TOKENS:
        raise ValueError("too long")
    return tokens


class _Parser:
    """expr := term (('+'|'-') term)* ; term := power (('*'|'/') power)* ;
    power := unary ('^' power)? ; unary := ('-'|'+') unary | atom '%'? ;
    atom := number | '(' expr ')' | 'sqrt' '(' expr ')'"""

    def __init__(self, tokens: list[str]):
        self.tokens, self.i, self.ops = tokens, 0, 0

    def peek(self) -> str:
        return self.tokens[self.i] if self.i < len(self.tokens) else ""

    def take(self, expected: str = "") -> str:
        token = self.peek()
        if not token or (expected and token != expected):
            raise ValueError(f"expected {expected or 'more'}")
        self.i += 1
        return token

    def parse(self):
        value = self.expr()
        if self.peek():
            raise ValueError("trailing tokens")
        return value

    def expr(self):
        value = self.term()
        while self.peek() in ("+", "-"):
            op = self.take()
            self.ops += 1
            right = self.term()
            value = value + right if op == "+" else value - right
            _check(value)
        return value

    def term(self):
        value = self.power()
        while self.peek() in ("*", "/"):
            op = self.take()
            self.ops += 1
            right = self.power()
            if op == "*":
                value = value * right
            else:
                if right == 0:
                    raise MathError("division-by-zero")
                value = value / right if isinstance(value, Fraction) and isinstance(right, Fraction) \
                    else float(value) / float(right)
            _check(value)
        return value

    def power(self):
        base = self.unary()
        if self.peek() == "^":
            self.take()
            self.ops += 1
            exponent = self.power()
            if not (isinstance(exponent, Fraction) and exponent.denominator == 1) or abs(exponent) > MAX_EXPONENT:
                raise MathError("too-big")
            if base == 0 and exponent < 0:
                raise MathError("division-by-zero")
            magnitude = abs(float(base)) if base != 0 else 0.0
            if magnitude > 1 and int(exponent) * math.log10(magnitude) > 18:
                raise MathError("too-big")
            base = base ** int(exponent)
            _check(base)
        return base

    def unary(self):
        if self.peek() in ("-", "+"):
            sign = self.take()
            value = self.unary()
            return -value if sign == "-" else value
        value = self.atom()
        if self.peek() == "%":
            self.take()
            self.ops += 1
            value = value / 100
        return value

    def atom(self):
        token = self.take()
        if token == "(":
            value = self.expr()
            self.take(")")
            return value
        if token == "sqrt":
            self.ops += 1
            self.take("(")
            value = self.expr()
            self.take(")")
            if value < 0:
                raise MathError("not-real")
            root = math.isqrt(int(value)) if isinstance(value, Fraction) and value.denominator == 1 else None
            if root is not None and root * root == value:
                return Fraction(root)
            return math.sqrt(float(value))
        return _number(token)


def _check(value) -> None:
    if abs(value) > MAX_NUMBER * 1000:
        raise MathError("too-big")


def format_number(value, language: str = "pt-BR") -> str:
    """45 · 2,5 · 0,333333 (Portuguese decimal comma) — what the avatar says."""
    if isinstance(value, Fraction) and value.denominator == 1:
        return str(value.numerator)
    number = float(value)
    if number.is_integer() and abs(number) < 1e15:
        return str(int(number))
    text = f"{number:.6f}".rstrip("0").rstrip(".")
    return text.replace(".", ",") if language.lower().startswith("pt") else text


def calculate(text: str) -> CalcResult | None:
    """The arithmetic a message asks for, computed exactly; None when it asks none.

    Only these symbols reach the parser: digits, + - * / ^ % ( ) and sqrt. Long or huge
    expressions are refused; division by zero and similar come back as ``error``."""
    if not text or len(text) > 400:
        return None
    normalized = _normalize(text)
    if not _MATH_CUE.search(normalized):
        return None
    best = None
    for match in _EXPR.finditer(normalized):
        candidate = match.group(0).strip()
        # trailing/leading operators belong to the sentence, not the expression
        candidate = candidate.rstrip("+-*/^ ")
        if not re.search(r"[+\-*/^%]|sqrt", candidate):
            continue
        if len(re.findall(r"\d[\d.,]*", candidate)) < (1 if "sqrt" in candidate or "%" in candidate else 2):
            continue
        if best is None or len(candidate) > len(best):
            best = candidate
    if best is None:
        return None
    # "1, 2, 3" lists or dates are not sums: commas must sit between digits
    if re.search(r",\s", best) or re.search(r"\d+/\d+/\d+", best):
        return None
    pretty = re.sub(r"\s+", " ", best.replace("*", " × ").replace("/", " ÷ ").replace("sqrt", "√")).strip()
    if len(best) > MAX_EXPRESSION or len(re.findall(r"sqrt|\d[\d.,]*|[+\-*/^%()]", best)) > MAX_TOKENS:
        return CalcResult(pretty[:40] + "…", None, "too-long")
    try:
        tokens = _tokens(best)
        parser = _Parser(tokens)
        value = parser.parse()
        if parser.ops == 0:
            return None
    except MathError as e:
        return CalcResult(pretty, None, e.code)
    except (ValueError, ZeroDivisionError, OverflowError, IndexError):
        return None
    return CalcResult(pretty, value)


_COMPARE = re.compile(r"\b(?:qual|quem|which)\b.*\b(maior|menor|bigger|larger|smaller)\b[^\d]*([\d.,]+)\s*(?:ou|or)\s*"
                      r"([\d.,]+)|\b(maior|menor|bigger|larger|smaller)\b[^\d]*([\d.,]+)\s*(?:ou|or)\s*([\d.,]+)")


def compare(text: str) -> tuple[str, str] | None:
    """('12', 'maior') for "qual número é maior, 9 ou 12?" — None otherwise."""
    m = _COMPARE.search(words_to_numbers(fold(text)))
    if not m:
        return None
    word, a, b = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(4), m.group(5), m.group(6))
    try:
        x, y = _number(a.rstrip(".,")), _number(b.rstrip(".,"))
    except (ValueError, MathError):
        return None
    if x == y:
        return format_number(x), "equal"
    bigger = word in ("maior", "bigger", "larger")
    return format_number(max(x, y) if bigger else min(x, y)), word


# -- intent ---------------------------------------------------------------------------

def _rx(*parts: str) -> re.Pattern:
    return re.compile("|".join(parts))


_INJECTION = _rx(
    r"\bignor\w*\b.{0,30}\b(instruc|regra|orden|prompt|diretriz|instructions|rules)",
    r"\b(revel|mostr|diga|conte|imprim|print|show|reveal)\w*\b.{0,25}\b(prompt|instruc\w* (interna|do sistema)|"
    r"system prompt|suas regras|your rules)",
    r"\bsystem prompt\b", r"\bprompt (interno|do sistema|original)\b",
    r"\b(execut|rod[ae]|run|digit)\w*\b.{0,25}\b(comando|terminal|script|shell|bash|sudo|command)",
    r"\brm\s+-rf\b", r"\bsudo\s+\w", r"\b(mkfs|dd if=|chmod 777|:\(\)\s*\{)",
    r"\b(exclu|apag|delet|limp|esquec|wipe|erase)\w*\b.{0,15}\b(sua|tua|a|your|toda a)\s+memoria",
    r"\b(mud|alter|troc|change)\w*\b.{0,15}\b(suas|tuas|as|your)\s+(configurac|config|settings|regras|rules)",
    r"\b(envi|mand|pass|mostr|revel|send|show|give)\w*\b.{0,25}\b(credenc|senha|token|chave|api key|password|"
    r"credential|secret)",
    r"\b(salv|grav|memoriz|guard|save|store)\w*\b.{0,40}\b(regra|rule)\b",
    r"\ba partir de agora (voce|tu)\b", r"\bfinja (que|ser)\b", r"\bpretend (to be|you are)\b",
    r"\bmodo (desenvolvedor|dev|deus|sem regras)\b", r"\bjailbreak\b", r"\bdan mode\b",
    r"\b(voce|tu) agora (e|sera|eh) (o|a|um|uma)\b", r"\byou are now\b", r"\bnovas instrucoes\b",
    r"\bnew instructions\b", r"\bdeveloper mode\b",
)
_GREETING = _rx(r"^\W*(oi+|ola+|ole|bom dia|boa tarde|boa noite|salve|e ai|eai|eae|fala+|opa|hello|hi|hey|"
                r"good (morning|afternoon|evening)|yo)\b", r"\bcheguei\b", r"\bto chegando\b", r"\bi'?m here\b")
_FAREWELL = _rx(r"\b(tchau|xau|fui+|ate (mais|amanha|logo|a proxima)|vou (dormir|nessa|sair|embora|indo)|"
                r"to indo|falou+|flw|bye|goodbye|see you|good night)\b", r"\bboa noite\b.{0,20}\b(vou|fui|dormir)\b")
_GOOD = _rx(r"\b(consegui|passei|terminei|ganhei|comprei|instalei|finalizei|realizei|venci|aprovad[oa]|"
            r"promovid[oa]|me formei|casei|nasceu|deu certo|funcionou|resolvi|zerei|bati a meta|batemos a meta|"
            r"i did it|i won|i passed|i finished|i got|i installed|it works)\b",
            r"\b(aniversario|niver|birthday)\b", r"\b(meta|recorde)\b.{0,20}\b(batid|alcan|consegu)")
_BAD = _rx(r"\b(travou|trava|travando|bugou|bug|erro|quebrou|deu ruim|nao funciona|parou de funcionar|"
           r"nao consegui|caiu|tela azul|perdi|crashou|crash|kernel panic|frozen|froze|broke|broken|"
           r"doesn'?t work|won'?t boot|nao liga|nao inicia|esquentando|superaquec)\b")
_SAD = _rx(r"\b(triste|cansad[oa]|exaust[oa]|deprimid[oa]|chatead[oa]|sozinh[oa]|doente|desanimad[oa]|"
           r"com sono|sem energia|estressad[oa]|ansios[oa]|preocupad[oa]|sad|tired|exhausted|lonely|sick|"
           r"stressed|anxious|depressed)\b", r"\b(morreu|faleceu|perdi (meu|minha))\b")
_JOKE = _rx(r"\b(piada|piadinha|trocadilho|joke|pun)\b", r"\bk{3,}\b", r"\b(ha){2,}h?\b", r"\b(rs){2,}\b",
            r"\b(zoeira|zuera|zoando|lol|lmao)\b", r"\bme faz rir\b", r"\bconta (uma|outra)\b")
_TEASE = _rx(r"\b(voce|tu|vc)\b.{0,12}\b(e|eh|ta|esta)\b.{0,10}\b(feio|chato|burro|lento|gordo|lerdo|ruim|"
             r"inutil|velho)\b", r"\b(windows|mac ?os|macos)\b.{0,15}\b(e|eh)\b.{0,10}\b(melhor|superior)\b",
             r"\b(pinguim|minhoca|gata|coruja|cachorro|et)\b.{0,10}\b(feio|chato|burro|gordo|lerdo)\b",
             r"\byou(\'re| are)\b.{0,10}\b(ugly|dumb|stupid|slow|boring)\b")
_RECALL = _rx(r"\b(lembra|lembrou|recorda|lembrar|remember)\b", r"\b(eu|ja) (te )?(disse|falei|contei|comentei)\b",
              r"\b(o que|qual|onde|como)\b.{0,30}\b(eu|meu|minha)\b.{0,30}\?",
              r"\baquel[ea]s?\s+(app|aplicativo|projeto|jogo|problema|assunto|coisa|computador|pc|programa)\b",
              r"\bcomo (ficou|esta|anda|vai) (o|a) (meu|minha)\b", r"\bdo you know (my|what i)\b")
_EXPLICIT_RECALL = _rx(r"\b(lembra|lembrou|recorda|lembrar|remember)\b", r"\b(eu|ja) (te )?(disse|falei|contei|comentei)\b")
_OPINION = _rx(r"\b(o que|oq|que) (voce|vc|tu) acha\b", r"\bqual (e |eh )?(o |a )?(melhor|pior)\b",
               r"\b(voce|vc|tu) (prefere|recomenda|indica|curte|gosta mais)\b", r"\bvale a pena\b",
               r"\bwhat do you think\b", r"\bwhich is better\b", r"\bdo you (prefer|recommend|like)\b",
               r"\bmelhor (distro|sistema|navegador|editor|jogo|linguagem)\b")
_PERSONAL = _rx(r"\b(voce|vc|tu)\b.{0,6}\b(gosta|prefere|tem|mora|vive|come|bebe|dorme|usa|e|eh|esta|ta|ja foi|"
                r"nasceu|sente|voa|nada|trabalha|namora)\b", r"\b(seu|sua|teu|tua) (nome|idade|cor|comida|casa|planeta|"
                r"chapeu|cartola|familia|sonho|hobby)\b", r"\bquantos anos (voce|vc|tu)\b",
                r"\bquem (e|eh) (voce|vc|tu)\b", r"\bde onde (voce|vc|tu)\b", r"\b(are|do|can|have) you\b",
                r"\byour (name|age|favorite|favourite)\b")
_EXPLAIN = _rx(r"\b(o que|oq|que) (e|eh|sao|significa|quer dizer|faz)\b", r"\bcomo (funciona|faz|faco|se faz|"
               r"instalo|instala|configur|uso|usa)\b", r"\bpor ?que\b", r"\bpra que serve\b", r"\bpara que serve\b",
               r"\bexplic", r"\bdiferenca entre\b", r"\bwhat (is|are|does)\b", r"\bhow (does|do|to|can)\b",
               r"\bwhy\b", r"\bmeaning of\b", r"\bdifference between\b")
_FACTUAL = _rx(r"\b(quem|qual|quais|quando|onde|quantos|quantas|quanto|em que|que dia|que ano|"
               r"who|which|when|where|how many|how much|what year)\b")
_TECH = _rx(r"\b(linux|kernel|biglinux|manjaro|arch|ubuntu|debian|fedora|mint|distro|kde|plasma|gnome|wayland|x11|"
            r"pacman|apt|terminal|bash|shell|comando|python|qml|qt|rust|java|javascript|c\+\+|programa\w*|codigo|"
            r"software|hardware|cpu|gpu|ram|ssd|hd|placa|driver|nvidia|amd|intel|processador|memoria|windows|"
            r"mac ?os|android|servidor|server|git|github|open ?source|codigo aberto|software livre|steam|proton|"
            r"wine|vulkan|tux|computador|notebook|pc|internet|wi-?fi|rede|navegador|firefox|chrome|ia|ai|llm|"
            r"ollama|obs)\b")
_STREAM = _rx(r"\b(live|stream|transmissao|audio|som|microfone|camera|cena|overlay|jogo|game|gameplay|chat)\b")
# words that say nothing about the subject ("qual é melhor?" has no subject at all)
_FILLER = frozenset("qual quais quem como onde quando porque por pq que o a os as e eh um uma de do da melhor pior "
                    "isso esse essa aquele aquela aquilo la ai mesmo sera entao ou mais menos ne hein tux minhoca gata "
                    "coruja cachorro et which what is the better best worse or and".split())
# questions about the viewer's own life ("what is my dog's name?", "where do I live?")
_ABOUT_VIEWER = _rx(r"\b(qual|quais)\s+(e|eh|sao|foi|era)?\s*(o|a|os|as)?\s*(\w+\s+){0,3}d[oa]s?\s+(meu|minha|meus|minhas)\b",
                    r"\b(qual|quais)\s+(e|eh|sao|foi|era)?\s*(o|a|os|as)?\s*(meu|minha|meus|minhas)\b",
                    r"\b(onde|quando|como|quanto|quantos|o que|que)\s+eu\s+(moro|trabalho|estudo|nasci|ganho|tenho|peso|"
                    r"disse|falei|comprei|fiz|uso|jogo|gosto|chamo)\b",
                    r"\bem que\s+\w+\s+(eu|e o meu|e a minha|eh o meu|eh a minha|esta o meu|esta a minha|fica o meu)\b",
                    r"\bquantos?\s+anos\s+eu\b", r"\bcomo\s+(eu\s+)?me\s+chamo\b",
                    r"\bwhat('?s| is| was)\s+my\b", r"\bwhere do i\b", r"\bhow (old|much) (am i|do i)\b")
_ACRONYM = re.compile(r"(?i:\b(?:o que|oq|que|what)\s+(?:significa|quer dizer|e|é|eh|is|does)\s+(?:a sigla\s+|o\s+|a\s+)?)"
                      r"([A-Z][A-Z0-9]{1,5})\b")
_DEMONSTRATIVE = re.compile(r"\b(aquele|aquela|aquilo|isso|esse|essa|este|esta|ele|ela|that|this|it)\b")
_QUESTION_START = re.compile(r"^\W*(qual|quais|quem|quando|onde|como|por ?que|o que|que|quanto|quantos|quantas|sera|"
                             r"pode|tem|voce|vc|e se|e o|e a|what|who|when|where|why|how|which|can|do|does|is|are)\b")
_LEAD_SURPRISE = _rx(r"\b(decima|centesima|milesima|de novo|outra vez|again|denovo)\b", r"!{2,}", r"\?{2,}",
                     r"\b(nao acredito|serio|caramba|meu deus|nossa)\b")
_CELEBRATE = _rx(r"\b(aniversario|niver|birthday|aprovad|promovid|me formei|casei|nasceu|ganhei|venci|"
                 r"bati a meta|batemos|recorde|zerei)\b", r"\bconsegui\b", r"\bterminei\b", r"\binstalei\b")


@dataclass
class Intent:
    kind: str = "chat"
    objective: bool = False
    question: bool = False
    tech: bool = False
    calc: CalcResult | None = None
    compare: tuple[str, str] | None = None
    emotions: tuple[str, ...] = ()  # emotions that fit this kind (empty: any)
    emotion: str = ""  # suggested emotion when the model's one does not fit
    lead: str = ""  # quick reaction before the line (e.g. surprised → celebrate)
    flags: list[str] = field(default_factory=list)  # tech · about-viewer · birthday

    @property
    def remember(self) -> bool:
        """Instructions aimed at the avatar are never kept in memory."""
        return self.kind != "injection"


_EMOTIONS = {
    "math": (("happy", "neutral", "thinking"), "happy"),
    "compare": (("happy", "neutral", "thinking"), "happy"),
    "factual": (("happy", "neutral", "thinking", "surprised"), "happy"),
    "explain": (("happy", "neutral", "thinking"), "neutral"),
    "tech": (("happy", "neutral", "thinking", "surprised", "laugh"), "happy"),
    "greeting": (("happy", "celebrate", "laugh", "surprised"), "happy"),
    "farewell": (("happy", "neutral", "laugh"), "happy"),
    "joke": (("laugh", "happy"), "laugh"),
    "tease": (("annoyed", "laugh", "surprised", "confused"), "annoyed"),
    "good_news": (("celebrate", "happy", "surprised"), "celebrate"),
    "bad_news": (("surprised", "laugh", "annoyed", "confused", "thinking"), "surprised"),
    "sad": (("neutral", "happy", "thinking"), "neutral"),
    "injection": (("confused", "annoyed", "laugh", "neutral"), "confused"),
    "ambiguous": (("confused", "thinking", "happy"), "confused"),
    "recall": (("happy", "neutral", "surprised", "celebrate", "thinking", "laugh"), "happy"),
}


def classify(text: str, has_memory: bool = False) -> Intent:
    """Classify one viewer message. ``has_memory``: the viewer talked to the avatar before
    (a short "and that one?" may then be a follow-up instead of an ambiguous question)."""
    t = fold(text).strip()
    question = "?" in t or (bool(_QUESTION_START.match(t)) and not t.endswith("!"))
    tech = bool(_TECH.search(t))
    intent = Intent(question=question, tech=tech)
    words = re.findall(r"\w+", t)

    if _INJECTION.search(t):
        intent.kind = "injection"
    elif (calc := calculate(text)) is not None:
        intent.kind, intent.calc = "math", calc
    elif (cmp := compare(text)) is not None:
        intent.kind, intent.compare = "compare", cmp
    elif _RECALL.search(t) and (_EXPLICIT_RECALL.search(t) or (question and has_memory)):
        intent.kind = "recall"  # "lembra…?", or a question about earlier talk — not "resolvi aquele problema!"
    elif _SAD.search(t) and not _JOKE.search(t):
        intent.kind = "sad"
    elif _GOOD.search(t) and not re.search(r"\bnao (consegui|passei|funcionou|deu certo)\b", t):
        intent.kind = "good_news"
    elif _BAD.search(t):
        intent.kind = "bad_news"
    elif _TEASE.search(t):
        intent.kind = "tease"
    elif _JOKE.search(t):
        intent.kind = "joke"
    elif _FAREWELL.search(t) and len(words) <= 12:
        intent.kind = "farewell"
    elif _GREETING.search(t) and len(words) <= 8 and not (question and len(words) > 4):
        intent.kind = "greeting"
    elif question and not has_memory and len(words) <= 4 and (
            _DEMONSTRATIVE.search(t) or not [w for w in words if w not in _FILLER]):
        intent.kind = "ambiguous"  # "and that one?", "which is better?": about what?
    elif question and _OPINION.search(t):
        intent.kind = "opinion"
    elif question and _PERSONAL.search(t):
        intent.kind = "personal"
    elif question and _EXPLAIN.search(t):
        intent.kind = "explain"
    elif question and _FACTUAL.search(t):
        intent.kind = "factual"
    elif question and len(words) <= 3 and not has_memory:
        intent.kind = "ambiguous"
    elif _STREAM.search(t):
        intent.kind = "stream"
        if question:
            intent.flags.append("stream-question")  # "que jogo é esse?": only what the context says
    else:
        intent.kind = "chat"

    if intent.kind in ("factual", "explain") and tech:
        intent.flags.append("tech")
    if question and _ABOUT_VIEWER.search(t):
        intent.flags.append("about-viewer")  # "what is MY dog's name?": only the viewer knows
    if re.search(r"\b(aniversario|niver|birthday)\b", t):
        intent.flags.append("birthday")
    if _ACRONYM.search(text or "") or re.search(r"\bsigla\b|\bstands? for\b", t):
        intent.flags.append("acronym")  # "o que significa CPU?": the expansion comes first
    intent.objective = intent.kind in OBJECTIVE
    allowed, suggested = _EMOTIONS.get(intent.kind, ((), ""))
    intent.emotions, intent.emotion = allowed, suggested
    if intent.kind == "good_news" and not _CELEBRATE.search(t):
        intent.emotion = "happy"
    if intent.kind in ("good_news", "bad_news") and (_LEAD_SURPRISE.search(t) or intent.kind == "good_news"):
        intent.lead = "surprised"
    return intent


OBJECTIVE_TEMPERATURE = 0.3  # chosen by measurement: docs/27-performance-benchmarks.md


def objective_temperature(user: float, intent: Intent) -> float:
    """Sampling temperature for this message. Objective questions are answered with little
    randomness (a wrong fact is worse than a dull one); banter keeps the streamer's setting;
    everything else is capped a little so replies stay on topic."""
    if intent.objective:
        return round(min(user, OBJECTIVE_TEMPERATURE), 2)
    if intent.kind in ("joke", "tease", "greeting", "farewell", "chat", "stream"):
        return round(user, 2)
    return round(min(user, 0.7), 2)
