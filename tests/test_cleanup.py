"""Unit tests for src.cleanup.

Two kinds of case matter equally here: the dictation slip the rule exists
for, and the correct sentence that looks like one and must come back
untouched. Every rule has at least one of each.
"""

import pytest

from src.cleanup import (collapse_repeats, fix_english_grammar, strip_fillers,
                         tidy)


class TestFillers:
    @pytest.mark.parametrize("spoken, tidied", [
        ("Um, I think we should go.", "I think we should go."),
        ("Uh, the meeting is at two.", "The meeting is at two."),
        ("Ummm, hello.", "Hello."),
        ("I think. Um. Yes.", "I think. Yes."),
        ("Hmm.", ""),
    ])
    def test_a_filler_that_opens_a_sentence_goes_and_the_next_word_starts_it(
            self, spoken, tidied):
        assert strip_fillers(spoken) == tidied

    def test_a_filler_between_words_leaves_one_space(self):
        assert strip_fillers("I um think so.") == "I think so."

    def test_a_filler_inside_a_clause_takes_both_commas_with_it(self):
        assert strip_fillers("I want to, um, schedule a meeting.") == \
            "I want to schedule a meeting."

    def test_a_filler_after_a_real_pause_keeps_the_comma(self):
        assert strip_fillers("Well, um, I think so.") == "Well, I think so."
        assert strip_fillers("Yes, uh, I agree.") == "Yes, I agree."

    def test_a_filler_that_ends_a_sentence_goes_with_its_comma(self):
        assert strip_fillers("I don't know, um.") == "I don't know."

    @pytest.mark.parametrize("sentence", [
        "The umbrella is in the hummer.",
        "Uh-huh, that is right.",
        "To err is human.",
        "Ah, I see. Oh no.",
    ])
    def test_words_that_contain_or_resemble_a_filler_are_untouched(
            self, sentence):
        assert strip_fillers(sentence) == sentence


class TestRepeats:
    @pytest.mark.parametrize("spoken, tidied", [
        ("I I think so.", "I think so."),
        ("I I I think so.", "I think so."),
        ("I, I think we, we should go.", "I think we should go."),
        ("It is like, like the other one.", "It is like the other one."),
        ("The the day.", "The day."),
        ("I'm I'm fine.", "I'm fine."),
        ("Thank you very, very much.", "Thank you very much."),
    ])
    def test_a_stuttered_word_is_said_once(self, spoken, tidied):
        assert collapse_repeats(spoken) == tidied

    def test_the_first_spelling_is_the_one_kept(self):
        assert collapse_repeats("The the day.") == "The day."
        assert collapse_repeats("Hello THE the day.") == "Hello THE day."

    @pytest.mark.parametrize("spoken, tidied", [
        ("I will I will help you today.", "I will help you today."),
        ("I will I will I will help you.", "I will help you."),
        ("I know, I know, I know.", "I know."),
        ("This is this is Jose.", "This is Jose."),
    ])
    def test_a_stuttered_phrase_is_said_once(self, spoken, tidied):
        assert collapse_repeats(spoken) == tidied

    def test_a_sentence_whisper_looped_on_is_said_once(self):
        assert collapse_repeats("Thank you. Thank you. Thank you.") == \
            "Thank you."

    @pytest.mark.parametrize("sentence", [
        "He said that that was fine.",
        "I had had enough.",
        "Bye bye.",
        "The theme of the day.",
        "Does he have a car? He has a car.",
        "I said no. No way.",
        "It is what it is.",
    ])
    def test_doubles_that_are_real_english_stay(self, sentence):
        assert collapse_repeats(sentence) == sentence


class TestEnglishGrammar:
    @pytest.mark.parametrize("spoken, tidied", [
        ("You was a professional soccer player.",
         "You were a professional soccer player."),
        ("They wasn't there.", "They weren't there."),
        ("We is ready.", "We are ready."),
        ("You isn't ready.", "You aren't ready."),
        ("They has a car.", "They have a car."),
        ("You doesn't know.", "You don't know."),
        ("He don't know.", "He doesn't know."),
        ("It don't matter.", "It doesn't matter."),
        ("She have a car.", "She has a car."),
        ("I is here.", "I am here."),
        ("The people is here.", "The people are here."),
        ("People doesn't care.", "People don't care."),
    ])
    def test_subject_and_verb_agree(self, spoken, tidied):
        assert fix_english_grammar(spoken) == tidied

    @pytest.mark.parametrize("sentence", [
        "Does he have a car?",
        "Will it have one?",
        "I want to have it.",
        "What does it do?",
        "If he were here.",
        "The number of people is growing.",
        "He was there. She is here. It has worked.",
    ])
    def test_correct_agreement_is_untouched(self, sentence):
        assert fix_english_grammar(sentence) == sentence

    @pytest.mark.parametrize("spoken, tidied", [
        ("A apple a day.", "An apple a day."),
        ("I saw a elephant.", "I saw an elephant."),
        ("It took a hour.", "It took an hour."),
        ("He is a honest man.", "He is an honest man."),
        ("I read an book.", "I read a book."),
    ])
    def test_a_and_an_follow_the_next_word(self, spoken, tidied):
        assert fix_english_grammar(spoken) == tidied

    @pytest.mark.parametrize("sentence", [
        "A European, a one-time thing, a user, a uniform.",
        "An umbrella, an MRI, an hour.",
        "A URL and an FBI agent.",
    ])
    def test_articles_that_are_already_right_stay(self, sentence):
        assert fix_english_grammar(sentence) == sentence

    def test_double_comparatives_lose_the_more(self):
        assert fix_english_grammar("It is more better and more easier.") == \
            "It is better and easier."
        assert fix_english_grammar("More better.") == "Better."

    def test_more_before_an_ordinary_word_stays(self):
        assert fix_english_grammar("I need more paper.") == "I need more paper."

    def test_uncountables_lose_their_plural(self):
        assert fix_english_grammar("I have many informations and advices.") == \
            "I have many information and advice."

    def test_a_lowercase_i_is_the_pronoun(self):
        assert fix_english_grammar("i think i'm fine, i am.") == \
            "I think I'm fine, I am."


class TestTidy:
    def test_the_passes_combine(self):
        spoken = "Um, like uh like you you was a a professional soccer player."
        assert tidy(spoken) == "Like you were a professional soccer player."

    def test_a_filler_between_a_stutter_still_collapses(self):
        assert tidy("I um I think so.") == "I think so."

    def test_a_correct_sentence_comes_back_unchanged(self):
        sentence = "Hello there. How are you? I had had enough of that."
        assert tidy(sentence) == sentence

    def test_word_order_is_never_changed(self):
        # Reordering needs a reader, not a rule; that is what the editable
        # panes are for.
        assert tidy("You was a professional player soccer.") == \
            "You were a professional player soccer."

    def test_spanish_gets_repeats_and_fillers_but_no_english_grammar(self):
        assert tidy("Hola, eh, yo yo creo que que sí.", "es") == \
            "Hola, yo creo que sí."
        # "is" is not English here and must not be touched.
        assert tidy("You is", "es") == "You is"

    def test_an_ellipsis_mid_sentence_stays_lowercase_after(self):
        assert tidy("I was... thinking about it.") == \
            "I was... thinking about it."

    @pytest.mark.parametrize("text", ["", "   "])
    def test_empty_input_is_returned_as_is(self, text):
        assert tidy(text) == text
