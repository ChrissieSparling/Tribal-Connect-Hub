from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
DIRECTIVE = ""  # don't inject a Jinja comment at the top
EXTENDS_PREFIX = "{% extends"
EXTENDS_PREFIX_TRIMMED = "{%- extends"
LAYOUT_NAMES: set[str] = set()

def clean_file(p: Path) -> bool:
    raw = p.read_bytes()

    # 1) Strip UTF-8 BOM if present
    BOM = b"\xef\xbb\xbf"
    if raw.startswith(BOM):
        raw = raw[len(BOM):]

    # 2) Normalize newlines to \n (strip CR)
    text = raw.decode("utf-8", errors="strict").replace("\r\n", "\n").replace("\r", "\n")

    original = text

    # Skip full-document bases (they should start with <!doctype html>)
    if p.name in LAYOUT_NAMES:
        # still trim leading blank lines just in case
        text = text.lstrip("\n")
        if text != original:
            p.with_suffix(p.suffix + ".bak").write_text(original, encoding="utf-8", newline="\n")
            p.write_text(text, encoding="utf-8", newline="\n")
            return True
        return False

    # 3) For child templates that extend a base: enforce directive + extends at top (no blank lines)
    # Find the first occurrence of an extends tag
    idx = text.find(EXTENDS_PREFIX)
    if idx == -1:
        # No extends — still trim accidental leading blank lines/BOM residue
        stripped = text.lstrip("\n")
        if stripped != original:
            p.with_suffix(p.suffix + ".bak").write_text(original, encoding="utf-8", newline="\n")
            p.write_text(stripped, encoding="utf-8", newline="\n")
            return True
        return False

    # Split into pre extends and rest
    before = text[:idx]
    after = text[idx:]

    # Tighten extends (use trimmed variant to swallow newline in many linters)
    if after.startswith(EXTENDS_PREFIX_TRIMMED):
        extends_line, remainder = after.split("\n", 1) if "\n" in after else (after, "")
    else:
        # convert "{% extends" to "{%- extends" for cleanliness
        first_line, remainder = after.split("\n", 1) if "\n" in after else (after, "")
        extends_line = first_line.replace(EXTENDS_PREFIX, EXTENDS_PREFIX_TRIMMED, 1)

    # Build new header: directive + extends line, with no blank line between
    # Build new header: just the extends line, with no blank line before
    new_top = f"{extends_line}\n"

    # Remove any leading whitespace/comments/blank lines before extends
    # (We’re discarding `before` entirely)
    new_text = new_top + remainder.lstrip("\n")

    if new_text != original:
        p.with_suffix(p.suffix + ".bak").write_text(original, encoding="utf-8", newline="\n")
        p.write_text(new_text, encoding="utf-8", newline="\n")
        return True

    return False

def main():
    changed = 0
    scanned = 0
    for p in sorted(TEMPLATES_DIR.glob("**/*.html")):
        scanned += 1
        try:
            if clean_file(p):
                print(f"fixed: {p.relative_to(TEMPLATES_DIR)}")
                changed += 1
        except Exception as e:
            print(f"ERROR on {p}: {e}")

    print(f"\nScanned {scanned} templates, updated {changed}.")
    if changed:
        print("Backups written as *.bak next to changed files.")

if __name__ == "__main__":
    main()
