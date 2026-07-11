import fitz


def extract_pdf_text(pdf_path):

    """
    提取PDF逐页文本
    """

    doc = fitz.open(pdf_path)

    pages = []

    for i,page in enumerate(doc):

        text = page.get_text()

        pages.append(
            {
                "page":i+1,
                "text":text
            }
        )


    return pages



if __name__=="__main__":

    pages=extract_pdf_text(
        "input/prospectus.pdf"
    )

    print(pages[0])