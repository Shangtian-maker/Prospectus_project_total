from parse_pdf import parse_pdf
from locate_sections import locate_sections
from extract_candidates import extract_candidates
from extract_with_rules import extract_with_rules
from run_cross_check import run_cross_check

def pipeline(pdf_path):
    pages = parse_pdf(pdf_path)
    sections = locate_sections(pages)
    candidates = extract_candidates(sections)
    sub, tran = extract_with_rules(candidates)

    result = run_cross_check(sub, [])
    return result