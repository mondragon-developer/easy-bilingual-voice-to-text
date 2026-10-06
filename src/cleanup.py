"""Tidying dictated speech before it is shown, copied or translated.

Whisper writes down what it hears, and what it hears is speech: "I, I think
we, we should", "like, like the other one", "um, you was there". Read back,
none of that is what the speaker meant to say. This module takes the
transcript and makes it read the way the sentence was intended, in three
passes:

1. **Fillers** - standalone "um", "uh", "erm", "hmm" and their longer
   spellings go, with the comma that belonged to them. Whisper drops most of
   these on its own; this catches the ones it keeps.
2. **Repeats** - a word said twice or more in a row becomes one ("I I I" ->
   "I", "like, like" -> "like"), and so does a short phrase said twice
   ("I will I will help you" -> "I will help you"). Doubles that are real
   English ("had had", "that that") are left alone.
3. **Grammar** (English only) - the handful of slips a Spanish speaker makes
   in English that have exactly one right answer: "you was" -> "you were",
   "he don't" -> "he doesn't", "a apple" -> "an apple", "more better" ->
   "better", "people is" -> "people are".

Everything here is a rule, not a model. A rule only fires when the input is
wrong in a way that has a single correct fix, so the output is never a
rewrite of what was said - a sentence that was already right comes back
unchanged. What a rule cannot do is reorder words: "a professional player
soccer" stays as it was, because deciding what was meant needs a reader,
not a pattern. Those are left for the editable panes.

No dependency, no download, runs in microseconds, and works offline like
everything else that touches the text.
"""

import re

#: Non-words a speaker makes while thinking. Each alternative allows the
#: stretched spellings ("ummm", "uhhh") Whisper sometimes produces.
#: "ah" and "oh" are deliberately absent: "Ah, I see" and "Oh no" are words.
_FILLER = r"(?:u+h+m*|u+m+|erm+|er|e+h+m*|h+m+|m+m+)"

#: A filler that opens a sentence takes its trailing punctuation with it, and
#: the word after it becomes the new start of the sentence.
_LEADING_FILLER = re.compile(
    rf"(?i)(^|[.!?…]\s+){_FILLER}(?:[,.;:!?]\s*|\s+|$)")

#: A filler inside a sentence, with the commas on either side of it.
_INNER_FILLER = re.compile(
    rf"(?i)(?P<before>[^\s,]+)?(?P<lead>\s*,)?\s*(?<![\w'-])(?:{_FILLER})"
    r"(?![\w'-])(?P<trail>\s*,)?")

#: Words after which a comma marks a real pause, so "Well, um, I think"
#: keeps its comma while "I want to, um, schedule" loses both of them.
_PAUSE_WORDS = frozenset({
    "well", "yes", "yeah", "no", "okay", "ok", "so", "and", "but", "or",
    "also", "then", "now", "actually", "basically", "anyway", "right",
    "look", "see", "hello", "hi", "hey", "oh", "ah", "thanks", "sorry",
    "sure", "bueno", "sí", "si", "pues", "entonces", "y", "pero", "o",
    "hola", "gracias", "claro", "vale",
})

#: Doubled words that are correct English, kept out of the repeat pass.
_LEGIT_DOUBLES = frozenset({"had", "that", "bye", "ha"})

_WORD = r"[\w'’-]+"

#: One word said two or more times in a row, commas allowed between.
_WORD_REPEAT = re.compile(
    rf"(?i)(?<![\w'’-])({_WORD})(?:,?\s+\1(?![\w'’-]))+")

#: A phrase of two to four words said twice or more in a row, inside one
#: sentence. A sentence boundary is not crossed: "Does he have a car? He
#: has a car." is two sentences, not a stutter.
_PHRASE_REPEAT = re.compile(
    rf"(?i)(?<![\w'’-])((?:{_WORD}\s+){{1,3}}{_WORD})(?:,?\s+\1(?![\w'’-]))+")

#: A whole sentence said twice or more in a row, punctuation included. This
#: is Whisper looping on silence ("Thank you. Thank you. Thank you.") rather
#: than anything the speaker did, and only an identical sentence counts.
_SENTENCE_REPEAT = re.compile(
    r"(?i)(^|[.!?…]\s+)([^.!?…]{1,80}[.!?…])(?:\s+\2)+")

# --- English grammar ------------------------------------------------------

#: Plural subjects that take "were" / "are" / "have" / "do".
_PLURAL = r"(?P<subj>you|we|they)"
_SINGULAR = r"(?P<subj>he|she|it)"

#: Words that correctly precede "he have" ("does he have", "will it have").
_BEFORE_HAVE = frozenset({
    "do", "does", "did", "will", "would", "could", "should", "can", "may",
    "might", "must", "shall", "to",
})

_AGREEMENT = [
    (re.compile(rf"(?i)\b{_PLURAL}\s+was(?P<neg>n't)?\b"), "were"),
    (re.compile(rf"(?i)\b{_PLURAL}\s+is(?P<neg>n't)?\b"), "are"),
    (re.compile(rf"(?i)\b{_PLURAL}\s+has(?P<neg>n't)?\b"), "have"),
    (re.compile(rf"(?i)\b{_PLURAL}\s+does(?P<neg>n't)?\b"), "do"),
    (re.compile(rf"(?i)\b{_SINGULAR}\s+don(?P<neg>'t)\b"), "doesn"),
    (re.compile(r"(?i)(?<!of )\b(?P<subj>people)\s+was(?P<neg>n't)?\b"), "were"),
    (re.compile(r"(?i)(?<!of )\b(?P<subj>people)\s+is(?P<neg>n't)?\b"), "are"),
    (re.compile(r"(?i)(?<!of )\b(?P<subj>people)\s+has(?P<neg>n't)?\b"), "have"),
    (re.compile(r"(?i)(?<!of )\b(?P<subj>people)\s+doesn(?P<neg>'t)\b"), "don"),
]

_I_IS = re.compile(r"\bI\s+(?:is|are)\b")
_HE_HAVE = re.compile(rf"(?i)(?:(?P<prev>{_WORD})\s+)?\b{_SINGULAR}\s+have\b")

#: Vowel-initial words that start with a consonant sound take "a".
_A_BEFORE_VOWEL_WORD = re.compile(r"(?i)^(?:one\b|once\b|eu|ew|uni|use|usu|ute|ubi)")
#: Consonant-initial words with a silent h take "an".
_SILENT_H = re.compile(r"(?i)^(?:hour|honest|honor|honour|heir|herb)")

_A_AN = re.compile(r"\b(?P<art>[Aa]n?)\s+(?=(?P<next>[A-Za-z]+))")

_COMPARATIVES = frozenset({
    "better", "worse", "easier", "harder", "faster", "slower", "bigger",
    "smaller", "higher", "lower", "cheaper", "stronger", "weaker", "longer",
    "shorter", "older", "younger", "larger", "nicer", "simpler", "quicker",
    "cleaner", "safer", "closer", "earlier", "lighter", "heavier",
})
_MORE_COMPARATIVE = re.compile(rf"(?i)\bmore\s+({_WORD})\b")

#: Uncountable nouns that a Spanish speaker pluralises by analogy with the
#: Spanish word ("informaciones", "consejos").
_UNCOUNTABLE = {
    "informations": "information", "advices": "advice",
    "furnitures": "furniture", "homeworks": "homework",
    "feedbacks": "feedback", "softwares": "software",
    "equipments": "equipment", "luggages": "luggage",
}
_UNCOUNTABLE_RE = re.compile(
    r"(?i)\b(" + "|".join(_UNCOUNTABLE) + r")\b")

_LOWER_I = re.compile(r"(?<![\w'’])i(?=[\s,!?]|'|’|$)")

_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?])")
_COMMA_BEFORE_END = re.compile(r",\s*(?=[.!?…;:])")
_ORPHAN_COMMA = re.compile(r"(^|[.!?…]\s+),\s*")


def _match_case(template: str, word: str) -> str:
    """Give ``word`` the capitalisation of ``template``'s first letter."""
    if template[:1].isupper():
        return word[:1].upper() + word[1:]
    return word


def strip_fillers(text: str) -> str:
    """Remove "um", "uh" and friends, tidying the commas they leave behind."""
    text = _LEADING_FILLER.sub(lambda m: m.group(1) + "\x00", text)

    def replace_inner(m):
        prefix = m.group("before") or ""
        before = prefix.lower()
        lead, trail = m.group("lead"), m.group("trail")
        if (lead or trail) and before in _PAUSE_WORDS:
            return prefix + ","
        if lead and not trail:
            return prefix + ","
        return prefix + " "

    text = _INNER_FILLER.sub(replace_inner, text)
    text = _ORPHAN_COMMA.sub(r"\1", text)
    text = _COMMA_BEFORE_END.sub("", text)
    text = re.sub(r"\x00\s*([^\W\d_])", lambda m: m.group(1).upper(), text)
    text = text.replace("\x00", "")
    return _normalise_spacing(text)


def collapse_repeats(text: str) -> str:
    """Say each stuttered word or phrase once."""

    def keep_first_word(m):
        if m.group(1).lower() in _LEGIT_DOUBLES:
            return m.group(0)
        return m.group(1)

    text = _WORD_REPEAT.sub(keep_first_word, text)
    text = _PHRASE_REPEAT.sub(lambda m: m.group(1), text)
    text = _SENTENCE_REPEAT.sub(lambda m: m.group(1) + m.group(2), text)
    return _normalise_spacing(text)


def fix_english_grammar(text: str) -> str:
    """Correct the agreement and article slips that have one right answer."""
    for pattern, verb in _AGREEMENT:
        def agree(m, verb=verb):
            return f"{m.group('subj')} {verb}{m.group('neg') or ''}"
        text = pattern.sub(agree, text)
    text = _I_IS.sub("I am", text)

    def he_has(m):
        prev = (m.group("prev") or "").lower()
        if prev in _BEFORE_HAVE:
            return m.group(0)
        head = f"{m.group('prev')} " if m.group("prev") else ""
        return f"{head}{m.group('subj')} has"
    text = _HE_HAVE.sub(he_has, text)

    def article(m):
        art, nxt = m.group("art"), m.group("next")
        if nxt[:1].isupper() and nxt != nxt.capitalize():
            return m.group(0)  # an acronym: "an MRI", "a URL"
        starts_vowel = nxt[:1].lower() in "aeio"
        if art.lower() == "a":
            if (starts_vowel and not _A_BEFORE_VOWEL_WORD.match(nxt)) \
                    or _SILENT_H.match(nxt):
                return _match_case(art, "an") + " "
        elif nxt[:1].lower() not in "aeiou" and not _SILENT_H.match(nxt):
            return _match_case(art, "a") + " "
        return m.group(0)
    text = _A_AN.sub(article, text)

    def comparative(m):
        word = m.group(1)
        if word.lower() in _COMPARATIVES:
            return _match_case(m.group(0), word)
        return m.group(0)
    text = _MORE_COMPARATIVE.sub(comparative, text)

    text = _UNCOUNTABLE_RE.sub(
        lambda m: _match_case(m.group(1), _UNCOUNTABLE[m.group(1).lower()]),
        text)
    text = _LOWER_I.sub("I", text)
    return text


def _normalise_spacing(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = re.sub(r",{2,}", ",", text)
    return text.strip()


def tidy(text: str, lang: str = "en") -> str:
    """Make a transcript read the way it was meant.

    Args:
        text: What the transcriber produced.
        lang: The language it is in. Fillers and repeats are handled for any
            language; the grammar pass runs only for ``"en"``.

    Returns:
        str: The tidied text. Text with nothing to fix comes back unchanged.
    """
    if not text or not text.strip():
        return text
    text = strip_fillers(text)
    text = collapse_repeats(text)
    if lang == "en":
        text = fix_english_grammar(text)
    return _normalise_spacing(text)
