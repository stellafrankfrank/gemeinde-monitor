# Gemeinde-Monitor – Dateien

Dieses Paket enthält:

- `urls.txt` – die 26 Gemeinde-Websites
- `monitor.py` – findet automatisch interne Unterseiten und vergleicht Änderungen
- `.github/workflows/monitor.yml` – startet die Prüfung automatisch zweimal täglich

## Wichtig beim ersten Lauf

Der erste Lauf speichert nur den Ausgangsstand. Erst ab dem zweiten Lauf können Änderungen erkannt werden.

## E-Mail-Benachrichtigung

Das Skript erstellt bei gefundenen Änderungen ein GitHub-Issue.
Damit GitHub dir dazu E-Mails schickt:

1. Öffne dein Repository.
2. Klicke oben rechts auf **Watch**.
3. Wähle **All Activity**.
4. Prüfe unter GitHub **Settings > Notifications**, dass E-Mail-Benachrichtigungen aktiviert sind.
