"""A turn cut at the spoken budget or output cap ends on its last complete sentence (ADR 061,
amendment 2026-11-13, second).

The cut itself is ``_trim_to_last_sentence`` inside ``finalize_answer_trimmed`` — the one seam the
batch turn and ``StreamAssembler.finish`` share — so spoken, stored and posted text are the same.
What these tests pin: both paths drop the dangling sentence and keep everything before it, an
answer that is one unfinished sentence stays as it is, the ✂ line comes from the turn core with
the number of dropped characters (and the client stays quiet for turns), and the two raw answers
of the 2026-11-13 run whose `?“`/`!“` sentences were lost now keep them.
"""

from __future__ import annotations

import asyncio
import logging

from dmbot.llm.cut_report import caller_reports
from dmbot.orchestrator import _ROLE_LABELS, DMBrain, finalize_answer_trimmed, turn_user_msg

_CUT_STATS = {"prompt_eval_count": 10, "eval_count": 220, "num_ctx": 24576,
              "truncated": True, "cut_tokens": 220, "cap": 220}


class _CutClient:
    """Stands in for ``ClaudeClient`` at its spoken budget: yields the text, then reports the cut
    in ``last_stats`` the way ``_finish`` does, noting whether the caller writes the ✂ line."""

    def __init__(self, deltas: list[str]) -> None:
        self._deltas = deltas
        self.last_stats: dict | None = None
        self.caller_wrote_line: bool | None = None

    def _report_cut(self) -> None:
        self.last_stats = dict(_CUT_STATS)
        self.caller_wrote_line = caller_reports()

    async def chat_stream(self, system, messages, *, options=None):
        for delta in self._deltas:
            yield delta
        self._report_cut()

    async def chat(self, system, messages, *, options=None, format=None):
        self._report_cut()
        return "".join(self._deltas)

    async def aclose(self) -> None:
        return None


def _cut_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("✂")]


_SPOKEN = "Die Tür schwingt auf. Bree Marlok hebt den Kopf."
_FRAGMENT = "„Bevor wir über Ware reden, Schätz"
_DELTAS = ["Die Tür schwingt auf. ", "Bree Marlok hebt den Kopf. ", "„Bevor wir über ", "Ware reden, Schätz"]


def test_streamed_turn_cut_mid_sentence_drops_the_fragment_everywhere(caplog):
    client = _CutClient(_DELTAS)
    brain = DMBrain(client)
    brain.add_player_line(1, "Timo", "Ich klopfe an.")
    spoken: list[str] = []

    async def on_sentence(sentence: str) -> None:
        spoken.append(sentence)

    with caplog.at_level(logging.WARNING):
        answer = asyncio.run(brain.respond_streaming(1, on_sentence=on_sentence))

    assert answer == _SPOKEN
    assert " ".join(spoken) == _SPOKEN                              # spoken: the fragment never was
    assert brain._session(1).history[-1]["content"] == _SPOKEN      # stored == spoken
    assert turn_user_msg(answer) is not None                        # TurnAnswer keeps its player line
    assert client.caller_wrote_line is True                         # the client stayed quiet
    assert _cut_lines(caplog) == [
        f"✂ Antwort an der Ausgabegrenze abgeschnitten (220/220 Tokens), {len(_FRAGMENT)} Zeichen am Ende weggefallen"
    ]


def test_batch_turn_cut_mid_sentence_drops_the_fragment(caplog):
    client = _CutClient(_DELTAS)
    brain = DMBrain(client)
    brain.add_player_line(1, "Timo", "Ich klopfe an.")

    with caplog.at_level(logging.WARNING):
        answer = asyncio.run(brain.respond(1))

    assert answer == _SPOKEN
    assert brain._session(1).history[-1]["content"] == _SPOKEN
    assert turn_user_msg(answer) is not None
    assert client.caller_wrote_line is True
    assert _cut_lines(caplog) == [
        f"✂ Antwort an der Ausgabegrenze abgeschnitten (220/220 Tokens), {len(_FRAGMENT)} Zeichen am Ende weggefallen"
    ]


def test_a_single_unfinished_sentence_stays_so_the_turn_is_not_silent(caplog):
    only = "Bree Marlok lehnt sich über das Gitter und mustert dich mit schwarz umrandeten"
    client = _CutClient([only])
    brain = DMBrain(client)
    brain.add_player_line(1, "Timo", "Ich klopfe an.")
    spoken: list[str] = []

    async def on_sentence(sentence: str) -> None:
        spoken.append(sentence)

    with caplog.at_level(logging.WARNING):
        answer = asyncio.run(brain.respond_streaming(1, on_sentence=on_sentence))

    assert answer == only
    assert " ".join(spoken) == only
    assert _cut_lines(caplog) == [
        "✂ Antwort an der Ausgabegrenze abgeschnitten (220/220 Tokens), 0 Zeichen am Ende weggefallen"
    ]


def test_no_cut_line_when_the_backend_reports_no_cut(caplog):
    # Ollama's stats carry no ``truncated``: the answer is still trimmed, but no ✂ line is written.
    client = _CutClient(_DELTAS)
    brain = DMBrain(client)
    brain.add_player_line(1, "Timo", "Ich klopfe an.")
    client._report_cut = lambda: setattr(client, "last_stats", {"eval_count": 220})

    with caplog.at_level(logging.WARNING):
        answer = asyncio.run(brain.respond(1))

    assert answer == _SPOKEN
    assert _cut_lines(caplog) == []


# --- the two raw answers of 2026-11-13 (debug.log, `🪵 LLM roh (stream)`) -------------------------
# Both were cut at the 748-character spoken budget. Before 86ccdc0 the sentence-end rule did not
# accept “ after ?/!, so the complete NSC line before the cut was dropped together with the
# fragment. ⏎ in the log is a newline.

_LABELS = ["Pr0degie", "Fridolin Feuchtgebietheld", "Rektalus", *_ROLE_LABELS]

_RAW_020101 = (
    "Das Auge hinter der Klappe verengt sich, Fridolin, dann rasselt der Riegel, und die Tür schwingt "
    "auf in einen langen Gang aus vergitterten Pfandkäfigen voller Uhren, Gebetsketten und rostiger "
    "Augmetik. Gleich neben dem Eingang hockt ein blinder Greis vor verhängten Vogelkäfigen und summt "
    "eine schiefe, fremde Hymne vor sich hin. Hinter einem Bronzegitter lehnt sich eine hagere Frau mit "
    "schwarz umrandeten Augen über ihre Bücher, die Hehlerin Bree Marlok selbst, und klopft mit dem "
    "Federkiel gegen das Tintenfass. „Handeln will er, um diese Stunde, mit Zollstaub am Kragen“, sagt "
    "sie gedehnt. „Bevor wir über Ware reden, Schätzchen: In wessen Auftrag kommst du?“ \n\n"
    "Fern über den Dächern hebt bereits das Grollen der Mitternachtssirene an, und du, R"
)

_RAW_015246 = (
    "Dein Blick gleitet über den Sockel, Fridolin, und bleibt an frischen, tiefen Kerben in der "
    "Steinkante hängen, wo jemand mit Brechstangen angesetzt hat. Dazwischen glitzert feiner grauer "
    "Bleistaub, und eine Schleifspur zieht sich durch die Asche bis zu einem rußigen Aschenschacht in "
    "der Seitenwand, aus dem kalter, fauliger Kanalgeruch heraufweht. Die Münze daneben ist ein "
    "gewöhnlicher Messingschilling, nur dass jemand den Aquila, den doppelköpfigen Adler des "
    "Imperiums, sauber glattgeschliffen hat. Die Schwester hält die Eisenstange noch immer erhoben, "
    "ihre Lippen murmeln ein hastiges Gebet, und dann bricht es aus ihr heraus: „Ich habe gefragt, wer "
    "dich schickt, Junge, antworte, bevor ich den Thron um Vergebung bitten muss!“ \n\n<<ERLEDIGT ste"
)


def test_live_020101_keeps_the_question_ending_in_a_closing_quote():
    answer, _markers, dropped = finalize_answer_trimmed(_RAW_020101, _LABELS, None)
    assert answer.endswith("„Bevor wir über Ware reden, Schätzchen: In wessen Auftrag kommst du?“")
    assert "Mitternachtssirene" not in answer
    assert dropped == len("Fern über den Dächern hebt bereits das Grollen der Mitternachtssirene an, und du, R")


def test_live_015246_keeps_the_exclamation_ending_in_a_closing_quote():
    answer, _markers, dropped = finalize_answer_trimmed(_RAW_015246, _LABELS, None)
    assert answer.endswith("bevor ich den Thron um Vergebung bitten muss!“")
    assert "<<" not in answer
    assert dropped == len("<<ERLEDIGT ste")
