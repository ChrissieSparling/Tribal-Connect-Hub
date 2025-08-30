import os

def strip_bom_from_file(filepath):
    with open(filepath, "rb") as f:
        content = f.read()
    # BOM in UTF-8 is b'\xef\xbb\xbf'
    if content.startswith(b'\xef\xbb\xbf'):
        print(f"Cleaning BOM: {filepath}")
        content = content[3:]  # remove BOM
        with open(filepath, "wb") as f:
            f.write(content)

def clean_directory(root):
    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            if filename.endswith(".html"):
                strip_bom_from_file(os.path.join(dirpath, filename))

if __name__ == "__main__":
    clean_directory(".")  # run in current folder
