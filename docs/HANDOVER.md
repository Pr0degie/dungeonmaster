# Handover — was du von Tobi brauchst, um den DM laufen zu lassen

Kurzcheckliste für eine fremde Maschine (z. B. die 5080-Box). Die allgemeine Installation
steht im [README → „Running on another machine"](../README.md) und in [`SETUP.md`](SETUP.md)
— hier steht nur, **was git nicht mitbringt** und was du dafür von Tobi bekommen musst.

## 1. Von Tobi kopieren (nicht im Repo — gekaufte Bücher / Ableitungen davon)

| Pfad | Inhalt | Wofür |
|---|---|---|
| `data/pdfs/` | gekaufte PDFs **+ der `md/`-Unterordner** (Konvertierungen) | RAG-Quelltexte, Charakterbogen-Filler |
| `data/lore/` | `imperium.md` + `chaos.md` — kuratierte deutsche Lore (ADR 021) | Weltwissen Imperium + Chaos |
| `data/adventures/chemical_burn/` | `adventure.json` + `npcs.json` — Szenenkarten + Statblocks | das Abenteuer im DM (ADR 019) |
| `data/vectordb/rag.db` | fertige Vektor-DB (rulebook 1505 / setting 201 / lore_imperium 18 / lore_chaos 17 Chunks, bge-m3) | Retrieval — kopieren spart den Neuaufbau |

Alles davon liegt absichtlich nicht im (öffentlichen) Repo — Ableitungen gekaufter Bücher.
Privat weitergeben ist ok, nicht hochladen.

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

Ollama mit `bge-m3` muss laufen; PDFs + `data/lore/` müssen da sein. Aus dem Repo-Root:

```
uv run python tools/pdf_to_md.py "data/pdfs/Starter Set/IM_SS_Setting_Guide_Book_240722.pdf" --pages 1-57
uv run python -m dmbot.rag.ingest "data/pdfs/md/Imperium Maledictum Core Rulebook.md" --source rulebook
uv run python -m dmbot.rag.ingest "data/pdfs/md/IM_SS_Setting_Guide_Book_240722.md" --source setting
uv run python -m dmbot.rag.ingest "data/lore/imperium.md" --source lore_imperium
uv run python -m dmbot.rag.ingest "data/lore/chaos.md" --source lore_chaos
```

(Setting Guide bewusst nur Seite 1–57 — das „Villains on Voll"-Kapitel ist Spoiler und
bleibt bis zum Kampagnenfinale draußen.)

## 4. Spielrunde

- Pro Voice-Channel braucht der DM eine Party: `data/sessions/<channel-id>/characters.json`.
  Erstellung: `docs/how-to-create-a-character.html` (Formular → JSON), Regeln-Primer für
  Spieler: `docs/how-to-play.html`.
- Beide Bots in denselben Voice-Channel (`!join`), dann läuft die Runde. Schnelltest, ob die
  Lore da ist: eine Chaos-Frage stellen — im Log muss eine `📚 lore_chaos:`-Zeile auftauchen.
