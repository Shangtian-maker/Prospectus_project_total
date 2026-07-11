import fitz



def split_pdf(
        input_pdf,
        output_pdf,
        start_page,
        end_page
):


    src=fitz.open(input_pdf)


    new_pdf=fitz.open()


    for i in range(
        start_page-1,
        end_page
    ):

        new_pdf.insert_pdf(
            src,
            from_page=i,
            to_page=i
        )


    new_pdf.save(output_pdf)



if __name__=="__main__":


    split_pdf(
        "input/prospectus.pdf",
        "output/history.pdf",
        20,
        50
    )