"""The pure half of ``dmbot.tools.text_replay``: reading the evening's log and the numbers."""

from dmbot.tools.text_replay import measure, parse_turns, sentences

LOG = """\
19:05:45 INFO    runtime | 📝 Pr0degie | 2.0s·194ms →DM | Ja, dann gehen wir mal los.
19:05:50 INFO    runtime | 📝 Sezgin | 0.7s·154ms | Hä?
19:05:57 INFO    orchestrator | 🪵 LLM roh (stream): Kaad nickt. Draußen regnet es. ⏎  ⏎ <<ORT schrein>>
19:05:57 INFO    voice.delivery | 🎭 Kaad nickt. Draußen regnet es.
19:28:20 INFO    runtime | 📝 Sezgin | 1.8s·315ms →DM | Ich komme mit.
19:28:34 INFO    orchestrator | 🪵 LLM roh (stream): Vosk hebt den Blick. ⏎  ⏎ Drüben knackt es.
19:28:34 INFO    voice.delivery | 🎭 Vosk hebt den Blick.

Drüben knackt es.
19:28:34 INFO    voice.delivery | ⏱ LLM 8328 ms
"""


def test_a_turn_holds_the_lines_spoken_to_the_dm_under_their_character_names():
    first, second = parse_turns(LOG, until="23:59:59")

    assert first["lines"] == [("Fridolin Feuchtgebietheld", "Ja, dann gehen wir mal los.")]  # table talk is not a line
    assert first["spoken"] == "Kaad nickt. Draußen regnet es."
    assert second["lines"] == [("Rektalus Zerfickus", "Ich komme mit.")]


def test_an_answer_logged_over_several_lines_is_read_whole():
    # The text after a paragraph break belongs to the answer — read line by line it was lost.
    assert parse_turns(LOG, until="23:59:59")[1]["spoken"] == "Vosk hebt den Blick. Drüben knackt es."


def test_turns_after_the_last_replayed_one_are_left_out():
    assert [turn["t"] for turn in parse_turns(LOG, until="19:10:00")] == ["19:05:57"]


def test_the_numbers_count_sentences_without_markers_and_closing_quotes_end_one():
    answer = "Bree lächelt nicht. „Kooperativ bin ich mit jedem.“ Dann wartet sie. <<TEST Überreden für Fridolin>>"

    assert sentences(answer) == ["Bree lächelt nicht.", "„Kooperativ bin ich mit jedem.“", "Dann wartet sie."]
    numbers = measure([answer, "x" * 601], cut=1)
    assert (numbers["answers"], numbers["sentences"], numbers["over_600"], numbers["cut"]) == (2, 4, 1, 1)
    assert numbers["chars_max"] == 601
