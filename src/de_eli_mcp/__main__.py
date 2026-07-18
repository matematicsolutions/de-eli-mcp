"""Uruchomienie przez `python -m de_eli_mcp`.

Konsolowe entry-pointy (`de-eli-mcp.exe`, `uvx.exe`, `pip.exe`) to launchery
generowane przy instalacji i NIE SA PODPISANE. Smart App Control w Windows 11
blokuje niepodpisane pliki wykonywalne bez pytania i bez wyjatkow per-program.
`python.exe` z python.org jest podpisany przez Python Software Foundation, wiec
ta droga dziala tam, gdzie entry-point zostaje zablokowany.

Zgloszone przez uzytkownika 2026-07-05 (konektory blokowane przez SAC).
"""

from .server import main

if __name__ == "__main__":
    main()
