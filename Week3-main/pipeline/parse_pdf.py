import pdfplumber

def parse_pdf(path):
    pages = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            pages.append({
                "page": i + 1,
                "text": text if text else ""
            })
    return pages


if __name__ == "__main__":
    import json
    import sys
    pages = parse_pdf(sys.argv[1])
    print(json.dumps(pages, ensure_ascii=False, indent=2))