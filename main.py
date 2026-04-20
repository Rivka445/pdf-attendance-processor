import json

from ocr.extractor import extract_text
from classification.classifier import classify_document


def main():
    with open("config/config.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    text = extract_text("pdf files/n_r_10_n.pdf")

    doc_type = classify_document(text, config)

    print(doc_type)
    print(text)


if __name__ == "__main__":
    main()