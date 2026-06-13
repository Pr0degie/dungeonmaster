# Checkliste — was du von Tobi brauchst, um den DM laufen zu lassen

Kurzcheckliste für eine fremde Maschine (z. B. die 5080-Box). Die allgemeine Installation
steht im [README → „Running on another machine"](../README.md) und in [`SETUP.md`](SETUP.md)
— hier steht nur, **was git nicht mitbringt** und was du dafür von Tobi bekommen musst.

## 1. Von Tobi kopieren (nicht im Repo — gekaufte Bücher / Ableitungen davon)

| Pfad | Inhalt | Wofür |
|---|---|---|
| `data/pdfs/` | gekaufte PDFs **+ der `md/`-Unterordner** (Konvertierungen) | RAG-Quelltexte, Charakterbogen-Filler |
| `data/adventures/chemical_burn/` | `adventure.json` + `npcs.json` — Szenenkarten + Statblocks | das Abenteuer im DM (ADR 019) |
| `data/vectordb/rag.db` | fertige Vektor-DB (rulebook 1505 / player_guide 502 / gm_guide 226 / setting 201 / lore_imperium 18 / lore_chaos 17 Chunks, bge-m3) | Retrieval — kopieren spart den Neuaufbau |

Alles davon liegt absichtlich nicht im (öffentlichen) Repo — Ableitungen gekaufter Bücher.
Privat weitergeben ist ok, nicht hochladen. (Das Lore-Kompendium `data/lore/` ist dagegen
**im Repo** — eigene Formulierung frei zugänglichen 40k-Wissens, kommt mit dem Clone.)

**Nicht kopieren:** Tobis `.env` (Tokens!). Eigene `.env` aus `.env.example` bauen — eigene
Discord-Tokens (ein Token = eine Live-Verbindung), `OLLAMA_HOST`, GPU-Profil. Wichtig:
`DM_ADVENTURE=chemical_burn` setzen, sonst lädt der DM kein Abenteuer.

## 2. Selbst installieren

1. Beide Repos klonen: dieses (`main`) + `Pr0degie/musicbot` Branch `dungeon_master` (Bot A).
   In beiden `uv sync`.
2. Ollama installieren, dann **`ollama pull mistral-nemo`** und **`ollama pull bge-m3`**
   (bge-m3 ist der Embedder der Vektor-DB — ohne ihn bleibt das Retrieval stumm, der Rest
   läuft weiter).
3. Rest (Tokens, GPU-Profil, Startreihenfolge, Tailscale-Split): README + `SETUP.md`.

## 3. `rag.db` neu bauen (nur falls nicht kopiert)

Ollama mit `bge-m3` muss laufen; die PDFs müssen da sein (`data/lore/` kommt mit dem Clone).
Aus dem Repo-Root:

```
uv run python tools/pdf_to_md.py "data/pdfs/Starter Set/IM_SS_Setting_Guide_Book_240722.pdf" --pages 1-57
uv run python tools/pdf_to_md.py "data/pdfs/Imperium Maledictum Inquisition GM-Guide.pdf" --pages 4-61,74-83,172-174 -o "data/pdfs/md/Imperium Maledictum Inquisition GM-Guide.md"
uv run python -m dmbot.rag.ingest "data/pdfs/md/Imperium Maledictum Core Rulebook.md" --source rulebook
uv run python -m dmbot.rag.ingest "data/pdfs/md/IM_SS_Setting_Guide_Book_240722.md" --source setting
uv run python -m dmbot.rag.ingest "data/pdfs/md/Imperium_Maledictum_Inqusition_Player's_Guide.md" --source player_guide
uv run python -m dmbot.rag.ingest "data/pdfs/md/Imperium Maledictum Inquisition GM-Guide.md" --source gm_guide
uv run python -m dmbot.rag.ingest "data/lore/imperium.md" --source lore_imperium
uv run python -m dmbot.rag.ingest "data/lore/chaos.md" --source lore_chaos
```

Bewusste Spoiler-Schnitte (wie „Villains on Voll"): der **Setting Guide** nur Seite 1–57; der
**Inquisition GM-Guide** nur Seite 4–61, 74–83, 172–174 (= Ordos/Philosophien, Lex Imperialis,
Signs of Chaos/Xenos, Rosetten, Radical Methods, Bestiarium). **Draußen:** die *Heresies-Macharia*-
Kampagne (S. 84–121), die Sector-Threat-Villains, die Open Case Files, die Inquisitor-Steckbriefe
(inkl. Patron Halikarn, S. 62–73) und der Index (S. 175, nennt alle Geheimnis-Einträge). Der
**Player's Guide** kommt komplett rein (spielerseitig). Reihenfolge/Labels der Quellen stehen in
`dmbot/rag/retrieve.py` (`_SOURCES`).

## 4. Spielrunde

- Pro Voice-Channel braucht der DM eine Party: `data/sessions/<channel-id>/characters.json`.
  **Die aktuelle circlejerk-Party (Channel `1343673766487654464`: Fridolin / Gellicus /
  Rektalus) liegt bereits im Repo** und kommt mit dem Clone — spielt ihr denselben Channel,
  ist hier nichts zu tun. **Anderer Channel-ID?** Die Datei in den Ordner mit *eurer* ID
  kopieren (`data/sessions/<eure-id>/characters.json`), sonst greift der Beispiel-Fallback.
  Nur diese `characters.json` ist getrackt; Laufzeit-State (`state.json`/History/Recap) und die
  Bogen-PDFs unter `sheets/` bleiben lokal.
- Neue Charaktere erstellen: `docs/how-to-create-a-character.html` (Formular → JSON) **oder** der
  Ein-Prompt-Weg `docs/character-creation-prompt.md` (Spieler interviewt sich selbst → fertiges
  JSON). Regeln-Primer für Spieler: `docs/how-to-play.html`, Setting-Hintergrund: `docs/lore.html`
  (oder in Discord `!lore` / `!lore chaos`).
- Beide Bots in denselben Voice-Channel (`!join`), dann läuft die Runde. Schnelltest, ob die
  Lore da ist: eine Chaos-Frage stellen — im Log muss eine `📚 lore_chaos:`-Zeile auftauchen.
