"""Единая точка создания BeautifulSoup: lxml, если установлен, иначе stdlib."""
from __future__ import annotations

from bs4 import BeautifulSoup

try:
    import lxml  # noqa: F401
    HTML_PARSER = "lxml"
except ImportError:  # на iPhone (a-Shell) lxml может отсутствовать
    HTML_PARSER = "html.parser"


def make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, HTML_PARSER)
