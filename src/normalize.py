import re
import unicodedata


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"[\r\n\t]+", "\n", text)
    text = re.sub(r"[ \f\v]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def compact_for_match(text: str) -> str:
    text = normalize_text(text).lower().replace("\n", " ")
    # Collapse spaced decorative letters: D I S T I L L E R Y -> DISTILLERY
    def collapse_spaced_letters(match):
        return match.group(0).replace(" ", "")
    text = re.sub(r"\b(?:[a-z]\s+){2,}[a-z]\b", collapse_spaced_letters, text)
    text = re.sub(r"[^a-z0-9%./ ]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def text_lines(text: str) -> list[str]:
    return [compact_for_match(line) for line in normalize_text(text).splitlines() if compact_for_match(line)]


def adjacent_line_windows(text: str, max_window: int = 3) -> list[str]:
    lines = text_lines(text)
    windows = list(lines)
    for size in range(2, max_window + 1):
        for i in range(0, max(0, len(lines) - size + 1)):
            windows.append(" ".join(lines[i:i+size]))
    # preserve order, drop duplicates
    seen = set()
    out = []
    for item in windows:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def canonical_volume(text: str) -> str:
    text = compact_for_match(text)
    text = re.sub(r"\bmilliliters?\b", "ml", text)
    text = re.sub(r"\bliters?\b", "l", text)
    text = re.sub(r"(\d)\s*(ml|l)\b", r"\1 \2", text)
    return text


def canonical_abv(text: str) -> str:
    text = compact_for_match(text)
    text = text.replace("alc / vol", "alc/vol")
    text = text.replace("alc. / vol", "alc/vol")
    text = text.replace("alcohol by volume", "abv")
    text = text.replace("alc vol", "alc/vol")
    return text
