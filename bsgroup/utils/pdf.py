import base64
import mimetypes
import os
import re
import frappe
from frappe import _
from frappe.core.doctype.access_log.access_log import make_access_log
from urllib.parse import urlparse, unquote


@frappe.whitelist()
def report_to_pdf(html, orientation="Landscape"):
	make_access_log(file_type="PDF", method="PDF", page=html)
	frappe.local.response.filename = "report.pdf"
	frappe.local.response.filecontent = _get_pdf(html, orientation)
	frappe.local.response.type = "pdf"


def _redirect_assets_to_localhost(html):
	"""Replace any external host in asset/file URLs with 127.0.0.1 so
	wkhtmltopdf (running as a subprocess) can load them via localhost
	instead of the site's external IP which may be unreachable."""
	site_url = frappe.utils.get_url()  # uses request host (e.g. http://192.168.75.199:8003)
	parsed = urlparse(site_url)
	port = parsed.port or (443 if parsed.scheme == "https" else 80)
	localhost_base = f"http://127.0.0.1:{port}"

	# Replace occurrences of the exact site base URL
	html = html.replace(site_url.rstrip("/"), localhost_base)

	# Also catch any other host variant pointing to the same port (e.g. http://bits.local:8003)
	html = re.sub(
		rf'https?://[^/"\']+:{port}(/(?:assets|files)/)',
		lambda m: localhost_base + m.group(1),
		html,
	)
	return html


def _get_pdf(html, orientation):
	import pdfkit
	from pypdf import PdfReader, PdfWriter
	import io
	from frappe.utils.pdf import (
		PDF_CONTENT_ERRORS, prepare_options, cleanup,
		get_file_data_from_writer, get_wkhtmltopdf_version,
	)
	from frappe.utils.data import scrub_urls
	from packaging.version import Version

	html = scrub_urls(html)
	html = _redirect_assets_to_localhost(html)

	html, options = prepare_options(html, {
		"orientation": orientation,
		"load-error-handling": "ignore",
	})

	options.update({"disable-javascript": "", "disable-local-file-access": ""})

	if Version(get_wkhtmltopdf_version()) > Version("0.12.3"):
		options.update({"disable-smart-shrinking": ""})

	filedata = ""
	try:
		filedata = pdfkit.from_string(html, options=options or {}, verbose=True)
		reader = PdfReader(io.BytesIO(filedata))
	except OSError as e:
		all_errors = PDF_CONTENT_ERRORS + ["ConnectionRefusedError", "network error"]
		if any(err in str(e) for err in all_errors):
			if not filedata:
				frappe.throw(_("PDF generation failed: could not load required resources"))
			reader = PdfReader(io.BytesIO(filedata))
		else:
			raise
	finally:
		cleanup(options)

	writer = PdfWriter()
	writer.append_pages_from_reader(reader)
	return get_file_data_from_writer(writer)


@frappe.whitelist(allow_guest=True)
def download_pdf(
	doctype,
	name,
	format=None,
	doc=None,
	no_letterhead=0,
	language=None,
	letterhead=None,
	pdf_generator=None,
):
	"""Override of frappe.utils.print_format.download_pdf that rewrites image
	URLs to 127.0.0.1 before invoking wkhtmltopdf, so the process can fetch
	them even when the site hostname (e.g. bits.local) is not in /etc/hosts."""
	from frappe.utils.print_format import validate_print_permission, print_language
	from frappe.utils.pdf import get_pdf
	from frappe.utils.data import scrub_urls

	if pdf_generator is None:
		pdf_generator = "wkhtmltopdf"

	doc = doc or frappe.get_doc(doctype, name)
	validate_print_permission(doc)

	if pdf_generator != "wkhtmltopdf":
		# Chrome / other generators: fall back to Frappe's default
		from frappe.utils.print_format import download_pdf as _orig
		return _orig(
			doctype, name, format=format, doc=doc, no_letterhead=no_letterhead,
			language=language, letterhead=letterhead, pdf_generator=pdf_generator,
		)

	with print_language(language):
		html = frappe.get_print(
			doctype, name, format, doc=doc, as_pdf=False,
			letterhead=letterhead, no_letterhead=no_letterhead,
		)
		# scrub_urls converts /files/... → http://bits.local:PORT/files/...
		# then redirect the hostname so wkhtmltopdf can reach localhost
		html = scrub_urls(html)
		html = _redirect_assets_to_localhost(html)
		pdf_file = get_pdf(html, options={"load-error-handling": "ignore"})

	frappe.local.response.filename = "{}.pdf".format(name.replace(" ", "-").replace("/", "-"))
	frappe.local.response.filecontent = pdf_file
	frappe.local.response.type = "pdf"


def _smoke_test_proposal_pdf():
	"""Temporary test: verify PDF generation works end-to-end."""
	import pdfkit
	from frappe.utils.data import scrub_urls
	from frappe.utils.pdf import prepare_options
	html = frappe.get_print("Quotation", "SAL-QTN-2026-00048", "Propsal PDF - UAE", as_pdf=False)
	html = scrub_urls(html)
	html = _redirect_assets_to_localhost(html)
	html, options = prepare_options(html, {"load-error-handling": "ignore"})
	with open("/tmp/test_proposal_final.html", "w") as f:
		f.write(html)
	filedata = pdfkit.from_string(html, options=options or {}, verbose=True)
	with open("/tmp/test_proposal.pdf", "wb") as f:
		f.write(filedata)
	return {"size": len(filedata), "is_pdf": filedata[:4] == b"%PDF", "html_size": len(html)}
