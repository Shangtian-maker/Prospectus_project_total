import re
from config import TARGET_CHAPTERS


def locate_chapters(pages):

    """
    根据关键词寻找章节位置
    """

    results={}


    for chapter in TARGET_CHAPTERS:

        start=None


        for p in pages:

            text=p["text"]


            if chapter in text:

                start=p["page"]

                break


        if start:

            results[chapter]={
                "start_page":start,
                "end_page":None
            }


    return results



def estimate_end_page(results,total_pages):

    """
    根据下一章节推断结束页
    """

    chapters=list(results.keys())


    starts=[
        results[c]["start_page"]
        for c in chapters
    ]


    for i,c in enumerate(chapters):

        if i<len(starts)-1:

            results[c]["end_page"] = (
                starts[i+1]-1
            )

        else:

            results[c]["end_page"]=total_pages



    return results