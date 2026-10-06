"""English grammar correction on this machine, for the slips rules cannot fix.

``cleanup.tidy`` handles the mistakes that have exactly one right answer.
Everything else - tense, word order, a missing "to", "since five years" -
needs something that has read a lot of English. That is CoEdIT (Grammarly's
instruction-tuned flan-T5-large), run through the same CTranslate2 engine
and SentencePiece tokeniser the offline translator already uses, and fetched
the same way: once, from this repository's ``models`` release, verified
against a SHA-256 pinned below. It is the big download in this app, about
710 MB, and the only one that is optional: it is fetched the first time
"Rules + grammar" is used, not before.

Why that model and not a smaller one: four candidates were tried on dictated
sentences. The T5-small, T5-base and flan-T5-large grammar-synthesis models
all invented names ("Jose Mondragon" came back as "Marco Polo", "Jesper
Monaghan" and "Jose Mondrian") and swapped nouns ("gizmo" to "wifi",
"deploy" to "the war begins"). CoEdIT-large changed nothing it was not asked
to, in nineteen sentences out of nineteen.

A model that rewrites can still rewrite wrongly, so every sentence it
returns is checked against the one that went in, and the original is kept
whenever the proposal changed too many words, lost a name or a number,
introduced a name that was never said, or brought in a content word the
speaker did not use. The model may polish; it may not put words in anyone's
mouth. The flan-T5 results above are what that check was built against.
"""

import re
from difflib import SequenceMatcher

from .local_mt import ModelSpec, _split_sentences, install, models_dir

#: The grammar model as published: grammarly/coedit-large converted to int8.
#: The hash is of the zip; ``scripts/convert_mt_models.py`` prints it.
SPEC = ModelSpec(
    "en", "en",
    "94beeeea804d1e0bafa3a92691fa3cc46793a46711bc50a5f244583f6156a2e1", 712,
    files=("model.bin", "spiece.model"), folder="coedit-large")

#: CoEdIT is instruction-tuned: the task is stated in front of the sentence,
#: and this exact wording is the one its card gives for grammar.
PROMPT = "Fix grammatical errors in this sentence: "

#: Sentences longer than this many tokens are left alone rather than cut:
#: a cut sentence would come back incomplete, which is worse than uncorrected.
_MAX_TOKENS = 256

#: Below this share of words in common, the proposal is a rewrite, not a
#: correction, whatever the words are. A loose backstop: the word-by-word
#: check in ``_is_grammatical_change`` is what does the real work.
MIN_SIMILARITY = 0.5

_WORD_RE = re.compile(r"[\w'’]+")
_HAS_DIGIT = re.compile(r"\d")

#: Words a correction may add freely: articles, auxiliaries, prepositions,
#: pronouns - the glue of English, none of which carries the meaning of a
#: sentence on its own.
_FUNCTION_WORDS = frozenset("""
a an the and or but nor so yet for of in on at to from by with without
about into onto over under between among through during before after
since until as than is are was were be been being am do does did done
have has had having will would shall should can could may might must
not no nor n't i me my mine you your yours he him his she her hers it
its we us our ours they them their theirs this that these those there
here who whom whose which what when where why how if then too very also
just only own same such any some each every all both few more most
other another much many little less any up down out off again further
once ever never always
""".split())

#: Irregular verbs, so "go" may become "went" and "buy" "bought": the
#: inflection check below cannot see those as the same word.
_IRREGULAR = {
    "be": "am is are was were been being", "go": "went gone goes going",
    "buy": "bought", "bring": "brought", "think": "thought",
    "teach": "taught", "catch": "caught", "seek": "sought",
    "fight": "fought", "send": "sent", "spend": "spent", "build": "built",
    "lend": "lent", "bend": "bent", "lose": "lost", "leave": "left",
    "feel": "felt", "keep": "kept", "sleep": "slept", "meet": "met",
    "mean": "meant", "say": "said", "pay": "paid", "lay": "laid",
    "make": "made", "have": "had has", "do": "did done does",
    "take": "took taken", "give": "gave given", "see": "saw seen",
    "come": "came", "become": "became", "get": "got gotten",
    "forget": "forgot forgotten", "write": "wrote written",
    "speak": "spoke spoken", "break": "broke broken",
    "choose": "chose chosen", "drive": "drove driven",
    "ride": "rode ridden", "rise": "rose risen", "eat": "ate eaten",
    "fall": "fell fallen", "know": "knew known", "grow": "grew grown",
    "throw": "threw thrown", "fly": "flew flown", "draw": "drew drawn",
    "show": "showed shown", "begin": "began begun", "drink": "drank drunk",
    "sing": "sang sung", "swim": "swam swum", "run": "ran",
    "sit": "sat", "stand": "stood", "understand": "understood",
    "find": "found", "hold": "held", "tell": "told", "sell": "sold",
    "read": "read", "lead": "led", "feed": "fed", "hear": "heard",
    "hide": "hid hidden", "bite": "bit bitten", "win": "won",
    "wear": "wore worn", "tear": "tore torn", "swear": "swore sworn",
    "steal": "stole stolen", "freeze": "froze frozen", "lie": "lay lain",
    "put": "put", "cut": "cut", "let": "let", "set": "set", "hit": "hit",
    "hurt": "hurt", "cost": "cost", "shut": "shut", "quit": "quit",
    "deal": "dealt", "dream": "dreamt", "light": "lit", "wake": "woke",
    "stick": "stuck", "strike": "struck", "dig": "dug", "hang": "hung",
    "shoot": "shot", "feel": "felt", "can": "could", "will": "would",
    "shall": "should", "may": "might", "mouse": "mice", "child": "children",
    "person": "people", "man": "men", "woman": "women", "foot": "feet",
    "tooth": "teeth", "goose": "geese", "life": "lives", "wife": "wives",
    "knife": "knives", "leaf": "leaves", "half": "halves",
}
_FORMS = {}
for _base, _inflected in _IRREGULAR.items():
    _family = {_base, *_inflected.split()}
    for _form in _family:
        _FORMS.setdefault(_form, set()).update(_family)


def _words(text):
    return [w.lower() for w in _WORD_RE.findall(text)]


def _names(text):
    """Capitalised words that are not the first word and not "I"."""
    found = _WORD_RE.findall(text)
    return {w for w in found[1:] if w[:1].isupper() and w != "I"}


_CONTRACTIONS = re.compile(r"(n't|n’t|'s|’s|'re|’re|'ve|’ve|'ll|’ll|'d|’d|'m|’m)$")


def _same_stem(a, b):
    """Share the first three or four letters: "day" / "days",
    "explain" / "explained", "loud" / "loudly"."""
    n = min(len(a), len(b), 4)
    return n >= 3 and a[:n] == b[:n]


def _is_grammatical_change(new_word, original_words):
    """Could ``new_word`` be a correction of something in the original?

    Yes for function words, for another form of a word that was said
    ("apple" to "apples", "explain" to "explained", "go" to "went"), and for
    nothing else: a content word the speaker never said is the model
    changing what was meant.
    """
    bare = _CONTRACTIONS.sub("", new_word)
    if new_word in _FUNCTION_WORDS or bare in _FUNCTION_WORDS:
        return True
    if new_word in _FORMS and _FORMS[new_word] & set(original_words):
        return True
    return any(_same_stem(bare, w) for w in original_words)


def accept(original: str, proposed: str) -> str:
    """The proposal if it is a correction of ``original``, else the original.

    A proposal is rejected when it is empty, shares too few words with the
    original, drops or adds a capitalised word (a name the model replaced,
    or one it invented), changes any number, or brings in a content word
    the speaker never said.
    """
    proposed = proposed.strip()
    if not proposed:
        return original
    before, after = _words(original), _words(proposed)
    if not before:
        return original
    if SequenceMatcher(None, before, after).ratio() < MIN_SIMILARITY:
        return original
    # Every name said must survive, and no name may appear that was not
    # said. Compared without case so a word the model merely capitalised
    # does not count as a new name.
    if any(name.lower() not in after for name in _names(original)):
        return original
    if any(name.lower() not in before for name in _names(proposed)):
        return original
    digits_before = sorted(w for w in before if _HAS_DIGIT.search(w))
    digits_after = sorted(w for w in after if _HAS_DIGIT.search(w))
    if digits_before != digits_after:
        return original
    said = set(before)
    for word in after:
        if word not in said and not _is_grammatical_change(word, before):
            return original
    return proposed


class LocalGrammar:
    """Lazily loads the grammar model and corrects English text."""

    def __init__(self, root=None, ensure=install):
        """
        Args:
            root: Models folder. Defaults to ``local_mt.models_dir()``.
            ensure: ``callable(spec, root, progress) -> Path`` that makes the
                model available; ``install`` by default, a stub in tests.
        """
        self._root = root
        self._ensure = ensure
        self._engine = None

    def _get_engine(self, progress=None):
        if self._engine is None:
            root = self._root or models_dir()
            folder = self._ensure(SPEC, root, progress)
            self._engine = _Engine(folder)
        return self._engine

    def correct(self, text: str, progress=None) -> str:
        """Correct ``text`` sentence by sentence, keeping any the model
        would have rewritten rather than corrected.

        Args:
            text: English text.
            progress: Passed to the model download when one is needed;
                ``callable(done_bytes, total_bytes)``.

        Returns:
            str: The corrected text ("" for empty input).

        Raises:
            Exception: A download that failed (offline, or verification).
        """
        text = text.strip()
        if not text:
            return ""
        engine = self._get_engine(progress)
        sentences = _split_sentences(text)
        proposals = engine.correct(sentences)
        return " ".join(accept(original, proposed)
                        for original, proposed in zip(sentences, proposals))


class _Engine:
    """The CTranslate2 model plus its SentencePiece tokeniser."""

    def __init__(self, folder):
        import ctranslate2
        import sentencepiece as spm

        from pathlib import Path
        folder = Path(folder)
        self._translator = ctranslate2.Translator(str(folder), device="cpu",
                                                  compute_type="int8")
        self._tokens = spm.SentencePieceProcessor(
            model_file=str(folder / "spiece.model"))

    def correct(self, sentences):
        """One proposal per sentence. A sentence too long for the model is
        returned as it came, so the caller's check keeps it."""
        batch, index = [], []
        for i, sentence in enumerate(sentences):
            tokens = self._tokens.encode(PROMPT + sentence, out_type=str)
            if len(tokens) > _MAX_TOKENS:
                continue
            batch.append(tokens + ["</s>"])
            index.append(i)
        out = list(sentences)
        if not batch:
            return out
        results = self._translator.translate_batch(
            batch, beam_size=4, max_decoding_length=_MAX_TOKENS + 50)
        for i, result in zip(index, results):
            out[i] = self._tokens.decode(result.hypotheses[0]).strip()
        return out
