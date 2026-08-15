"""Einmal-Aufräumer für den Fehlstart vom 2026-08-15 (Timos Rechner).

Der Debug-Abend lief in die LIVE-Dateien des Channels: `history.jsonl` trägt seither
Turns aus der Debug-Kampagne, die inhaltlich nichts mit der echten Kampagne zu tun haben.
Gefährlich wird das erst beim nächsten LIVE-`!leave`: der rotiert die Datei und ingestiert
sie ins Kampagnengedächtnis `session_<channel-id>`. Also vor der nächsten echten Sitzung
einmal laufen lassen.

    uv run python cleanup_15aug.py <pfad-zu-data/sessions/<channel-id>>          # Bericht
    uv run python cleanup_15aug.py <pfad-zu-data/sessions/<channel-id>> --apply  # ausführen

Ohne --apply wird nur gezeigt, was passieren würde. Mit --apply:
  * `history.jsonl` wird nach `history.jsonl.bak` gesichert,
  * alle Records ab dem ersten mit Datum >= 2026-08-15 wandern nach
    `entfernt-2026-08-15.jsonl` NEBEN den Session-Ordner (nicht hinein! Ein
    `history.<stamp>.jsonl` im Ordner würde beim nächsten !join eingelesen),
  * `history.jsonl` behält nur die Records davor.

`state.json` wird nur geprüft, nie geschrieben — der Abend hat keine Marker ausgelöst
(kein Szenenwechsel, keine Uhr, keine Flag), also sollte dort nichts zu reparieren sein.
Der Bericht sagt es dir.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

CUTOFF = "2026-08-15"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # cp1252-Konsole überlebt die Umlaute/Pfeile
    except Exception:
        pass
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    session_dir = Path(sys.argv[1]).resolve()
    apply = "--apply" in sys.argv
    hist = session_dir / "history.jsonl"

    if not hist.is_file():
        print(f"[!] {hist} gibt es nicht — nichts zu tun.")
        return 0

    keep: list[str] = []
    drop: list[str] = []
    for line in hist.read_text(encoding="utf-8").splitlines(keepends=True):
        if not line.strip():
            continue
        try:
            ts = str(json.loads(line).get("ts", ""))
        except json.JSONDecodeError:
            ts = ""  # torn line — behandeln wie "davor", damit nichts still verschwindet
        (drop if (ts[:10] >= CUTOFF and ts) or drop else keep).append(line)

    print(f"[i] {hist.name}: {len(keep) + len(drop)} Records")
    print(f"[i] behalten (echte Kampagne): {len(keep)}")
    print(f"[i] entfernen (ab {CUTOFF}):    {len(drop)}")
    if drop:
        first = json.loads(drop[0])
        print(f"    erster entfernter Record: {first.get('ts')} kind={first.get('kind', 'turn')}")
        print(f"    Auszug: {str(first.get('answer', first))[:120]}")

    state = session_dir / "state.json"
    if state.is_file():
        d = json.loads(state.read_text(encoding="utf-8"))
        print(f"[i] state.json: scene_id={d.get('scene_id')!r}, "
              f"NSCs={len(d.get('npcs', []))}, Recap={len(d.get('recap', ''))} Zeichen")
        print("    → gehört die scene_id zur ECHTEN Kampagne? Wenn ja: nichts zu tun.")

    for stray in ("recap.md", "chekhov.json"):
        p = session_dir / stray
        if p.is_file():
            when = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            print(f"[?] {stray} vorhanden (geändert {when}) — prüfen, ob vom 15.08.")

    # Der ganze Ordner: falls am 15.08. doch ein !leave lief, wurde die Live-history rotiert.
    # Ein Archiv MIT `.debug` im Namen, das echte Kampagnen-Turns enthält, ist der andere
    # Schadensfall — dann ist die Sicherung oben wichtiger als das Trimmen.
    print("\n[i] Inhalt des Session-Ordners:")
    for p in sorted(session_dir.iterdir()):
        when = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        kind = "Ordner" if p.is_dir() else f"{p.stat().st_size:>8} B"
        print(f"    {when}  {kind}  {p.name}")
    archives = sorted(p.name for p in session_dir.glob("history.*.jsonl"))
    if archives:
        print(f"[?] Rotierte Archive gefunden: {', '.join(archives)}")
        print("    Ein Archiv vom 15.08. OHNE `.debug` im Namen wäre ein Problem — melden.")

    if not drop:
        print("[OK] Keine Records ab dem Stichtag — die Datei ist sauber.")
        return 0
    if not apply:
        print("\n[i] Nur Bericht. Mit --apply ausführen.")
        return 0

    shutil.copy2(hist, hist.with_suffix(".jsonl.bak"))
    out = session_dir.parent / f"entfernt-{CUTOFF}.jsonl"
    out.write_text("".join(drop), encoding="utf-8")
    hist.write_text("".join(keep), encoding="utf-8")
    print(f"\n[OK] Sicherung: {hist.name}.bak")
    print(f"[OK] Entfernte Records: {out}  (AUSSERHALB des Session-Ordners)")
    print(f"[OK] {hist.name} enthält jetzt {len(keep)} Records der echten Kampagne.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
