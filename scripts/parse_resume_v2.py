from pathlib import Path

from docx import Document
from pypdf import PdfReader


def extract_text_from_docx(path: Path) -> str:
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def extract_text_from_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    parts = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            parts.append(text)
    return "\n".join(parts)


def extract_text_from_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_resume(path_str: str) -> str:
    path = Path(path_str)

    if not path.exists():
        raise FileNotFoundError(f"Resume file not found: {path}")

    suffix = path.suffix.lower()

    if suffix == ".docx":
        return extract_text_from_docx(path)
    if suffix == ".pdf":
        return extract_text_from_pdf(path)
    if suffix == ".txt":
        return extract_text_from_txt(path)

    raise ValueError("Unsupported resume format. Use .docx, .pdf, or .txt")


if __name__ == "__main__":
    sample_path = "resumes/resume.docx"
    text = parse_resume(sample_path)
    print(text[:3000])
