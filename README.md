# Wer ist das? – Chemie

Mobile-first Echtzeit-Spiel für zwei Personen. Der Server läuft auf Render; beide Handys verbinden sich per WebSocket mit demselben Raum.

## Spiel
- 24 Hauptgruppen-Elemente in zufälliger Reihenfolge
- Karte zeigt nur Symbol, Name und Ordnungszahl
- Geheimkarte pro Spieler
- mündliche Ja/Nein-Fragen
- eigene Karten werden durch Antippen umgedreht
- „Zug beenden“ wechselt den Zug
- bei einer verbleibenden Karte: direkt antippen und raten
- falscher letzter Tipp: Gegner spielt allein weiter
- 2→1: nach dem Umdrehen darf die letzte Karte direkt geraten werden

## Render
Startbefehl: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
WebSockets werden benötigt. Laufende Räume liegen im Arbeitsspeicher.
