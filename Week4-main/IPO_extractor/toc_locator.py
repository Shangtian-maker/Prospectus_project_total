import fitz



def extract_toc(pdf):

    """
    获取PDF目录
    """

    doc=fitz.open(pdf)


    toc=doc.get_toc()


    result=[]


    for item in toc:

        level,title,page=item


        result.append(
            {
                "title":title,
                "page":page
            }
        )


    return result



def search_target_toc(toc,keywords):


    result={}


    for item in toc:

        for key in keywords:

            if key in item["title"]:

                result[key]=item["page"]


    return result