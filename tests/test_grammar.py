"""Unit tests for src.grammar.

The model itself is never loaded here. What is tested is everything around
it: that a proposal which rewrites rather than corrects is thrown away, that
the model is fetched once and fed sentence by sentence, and the shape of the
CTranslate2 call.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.grammar import SPEC, LocalGrammar, _Engine, accept


class TestSpec:
    def test_hash_is_a_real_sha256_hex(self):
        assert len(SPEC.sha256) == 64
        int(SPEC.sha256, 16)

    def test_needs_the_weights_and_one_tokeniser(self):
        assert SPEC.files == ("model.bin", "spiece.model")

    def test_has_its_own_folder_and_archive(self):
        assert SPEC.name == "coedit-large"
        assert SPEC.url.endswith("/coedit-large-ct2-int8.zip")


class TestAccept:
    @pytest.mark.parametrize("original, proposed", [
        ("You was a professional player soccer.",
         "You were a professional soccer player."),
        ("I need review it with the team.", "I need to review it with the team."),
        ("Me and him goes to school every days.",
         "Me and him go to school every day."),
        ("Can you send me the report before Friday?",
         "Can you send me the report before Friday?"),
    ])
    def test_a_correction_is_taken(self, original, proposed):
        assert accept(original, proposed) == proposed

    def test_a_name_the_model_replaced_is_a_rejection(self):
        assert accept("Hello, this is Jose Mondragon.",
                      "Hello, this is Marco Polo.") == \
            "Hello, this is Jose Mondragon."

    def test_a_name_the_model_invented_is_a_rejection(self):
        assert accept("Yesterday he said he would come.",
                      "Yesterday Peter said he would come.") == \
            "Yesterday he said he would come."

    def test_a_rephrase_is_a_rejection(self):
        # Correct English, but it is a different sentence: the model is
        # rephrasing, and rephrasing is not its job.
        assert accept("We was working in the project all the night.",
                      "The project kept us busy the whole night.") == \
            "We was working in the project all the night."

    def test_pronoun_fixes_are_corrections(self):
        assert accept("Me and him goes to school every days.",
                      "He and I go to school every day.") == \
            "He and I go to school every day."

    @pytest.mark.parametrize("original, proposed", [
        ("Yesterday I go to the store and I buy three apple.",
         "Yesterday I went to the store, and I bought three apples."),
        ("She don't like when the people is talking loud.",
         "She doesn't like when people are talking loudly."),
        ("I am agree with you, but we need the changes before the deploy.",
         "I agree with you, but we need the changes before the deployment."),
        ("He explain me the problem but I not understand very well.",
         "He explained to me the problem, but I do not understand very well."),
        ("The documents that I send you.", "The documents that I sent you."),
        ("I live in Boston since five years.",
         "I have lived in Boston for five years."),
    ])
    def test_inflections_and_glue_words_are_corrections(self, original,
                                                         proposed):
        assert accept(original, proposed) == proposed

    @pytest.mark.parametrize("original, proposed", [
        ("We need the changes before the deploy.",
         "We need the changes before the release."),
        # Right in English, but "old" was never said: that is the model
        # deciding what was meant, which is the speaker's job.
        ("I have twenty years.", "I am twenty years old."),
        ("Please add the label to the button.",
         "Please add the label to the menu."),
        ("The gizmo have a bug.", "The wifi has a bug."),
    ])
    def test_a_content_word_the_speaker_never_said_is_a_rejection(
            self, original, proposed):
        assert accept(original, proposed) == original

    def test_a_word_the_model_only_capitalised_is_not_a_name(self):
        assert accept("I work on the Gizmo accessibility.",
                      "I work on the Gizmo Accessibility.") == \
            "I work on the Gizmo Accessibility."

    def test_a_number_the_model_changed_is_a_rejection(self):
        assert accept("I live in Boston since five years.",
                      "I live in Boston since 2004.") == \
            "I live in Boston since five years."
        assert accept("Ticket 4521 is open.", "Ticket 4512 is open.") == \
            "Ticket 4521 is open."

    def test_a_number_kept_in_place_is_fine(self):
        assert accept("Ticket 4521 are open.", "Ticket 4521 is open.") == \
            "Ticket 4521 is open."

    def test_a_different_sentence_is_a_rejection(self):
        assert accept("The gizmo have a bug when you press the tab key.",
                      "The wifi has a problem when you press the mouse.") == \
            "The gizmo have a bug when you press the tab key."

    def test_an_empty_proposal_is_a_rejection(self):
        assert accept("Hello.", "") == "Hello."
        assert accept("Hello.", "   ") == "Hello."

    def test_the_first_word_may_change_case(self):
        assert accept("the dog barks.", "The dog barks.") == "The dog barks."

    def test_the_pronoun_i_is_not_a_name(self):
        assert accept("Yesterday I go there.", "Yesterday I went there.") == \
            "Yesterday I went there."


class TestLocalGrammar:
    @pytest.fixture
    def ensure(self, tmp_path):
        return MagicMock(return_value=tmp_path / "grammar-synthesis-small")

    def test_empty_input_never_touches_the_model(self, ensure):
        assert LocalGrammar(ensure=ensure).correct("   ") == ""
        ensure.assert_not_called()

    def test_the_model_is_fetched_once(self, ensure, tmp_path):
        grammar = LocalGrammar(root=tmp_path, ensure=ensure)
        with patch("src.grammar._Engine") as engine:
            engine.return_value.correct.side_effect = lambda s: list(s)
            grammar.correct("One.")
            grammar.correct("Two.")
        ensure.assert_called_once()
        spec, root, _ = ensure.call_args.args
        assert spec is SPEC
        assert root == tmp_path

    def test_sentences_go_through_as_a_batch_and_the_guard_applies(
            self, ensure):
        grammar = LocalGrammar(ensure=ensure)
        with patch("src.grammar._Engine") as engine:
            engine.return_value.correct.return_value = [
                "You were there.", "This is Marco Polo."]
            out = grammar.correct("You was there. This is Jose Mondragon.")
        engine.return_value.correct.assert_called_once_with(
            ["You was there.", "This is Jose Mondragon."])
        assert out == "You were there. This is Jose Mondragon."

    def test_progress_is_forwarded_to_the_download(self, ensure):
        grammar = LocalGrammar(ensure=ensure)
        report = MagicMock()
        with patch("src.grammar._Engine") as engine:
            engine.return_value.correct.side_effect = lambda s: list(s)
            grammar.correct("Hi.", progress=report)
        assert ensure.call_args.args[2] is report


class TestEngine:
    def _fake_libs(self, tmp_path, encoded, decoded):
        ct2 = MagicMock()
        spm = MagicMock()
        tokens = MagicMock()
        spm.SentencePieceProcessor.return_value = tokens
        tokens.encode.side_effect = encoded
        tokens.decode.side_effect = decoded
        hyps = [MagicMock(hypotheses=[[f"out{i}"]]) for i in range(len(decoded))]
        ct2.Translator.return_value.translate_batch.return_value = hyps
        return ct2, spm, tokens

    def test_states_the_task_and_appends_the_end_of_sentence_marker(
            self, tmp_path):
        ct2, spm, tokens = self._fake_libs(
            tmp_path, encoded=[["▁You", "▁was"]], decoded=["You were"])
        with patch.dict("sys.modules", {"ctranslate2": ct2,
                                        "sentencepiece": spm}):
            engine = _Engine(tmp_path)
            assert engine.correct(["You was"]) == ["You were"]
        assert tokens.encode.call_args.args[0] == \
            "Fix grammatical errors in this sentence: You was"
        batch = ct2.Translator.return_value.translate_batch.call_args.args[0]
        assert batch == [["▁You", "▁was", "</s>"]]
        ct2.Translator.assert_called_once_with(str(tmp_path), device="cpu",
                                               compute_type="int8")

    def test_a_sentence_too_long_for_the_model_is_passed_through(
            self, tmp_path):
        long_tokens = ["▁x"] * 300
        ct2, spm, tokens = self._fake_libs(
            tmp_path, encoded=[long_tokens, ["▁Hi"]], decoded=["Hi there"])
        with patch.dict("sys.modules", {"ctranslate2": ct2,
                                        "sentencepiece": spm}):
            engine = _Engine(tmp_path)
            assert engine.correct(["x " * 300, "Hi"]) == ["x " * 300, "Hi there"]
        batch = ct2.Translator.return_value.translate_batch.call_args.args[0]
        assert batch == [["▁Hi", "</s>"]]
