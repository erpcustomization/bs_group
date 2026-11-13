"""Remove the UAE quotation-only requirement for contractual terms."""
def execute():
    from bsgroup.quotation_optional_terms import install
    install()
