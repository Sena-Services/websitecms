import re

import frappe
from frappe.model.document import Document


# Maps item_type → (extension DocType name, autoname prefix)
EXTENSION_MAP = {
	"Agent": ("Registry Agent", "RA-.#####"),
	"Tool": ("Registry Tool", "RTOOL-.#####"),
	"Skill": ("Registry Skill", "RS-.#####"),
	"UI": ("Registry UI", "RUI-.#####"),
	"Logic": ("Registry Logic", "RL-.#####"),
}


class Registry(Document):
	def validate(self):
		self.ensure_slug()
		self.rebuild_search_text()

	def ensure_slug(self):
		if not self.slug:
			self.slug = self.generate_slug(self.title)
		self.slug = self.slug.lower().strip()
		self.slug = re.sub(r"[^a-z0-9-]", "-", self.slug)
		self.slug = re.sub(r"-+", "-", self.slug).strip("-")
		# Ensure uniqueness — append -2, -3, etc. if slug already taken
		base_slug = self.slug
		counter = 1
		while frappe.db.exists("Registry", {"slug": self.slug, "name": ("!=", self.name or "")}):
			counter += 1
			self.slug = f"{base_slug}-{counter}"

	def rebuild_search_text(self):
		from senaerp_platform.registry.embedding import build_search_text
		self._search_text = build_search_text(self)

	def after_insert(self):
		self.create_extension()

	def create_extension(self):
		ext_doctype, _ = EXTENSION_MAP.get(self.item_type, (None, None))
		if not ext_doctype:
			return

		ext = frappe.new_doc(ext_doctype)
		ext.registry = self.name
		ext.insert(ignore_permissions=True, ignore_mandatory=True)

		self.db_set("ref_name", ext.name, update_modified=False)

	def on_trash(self):
		self.delete_extension()

	def delete_extension(self):
		if not self.ref_name:
			return
		ext_doctype, _ = EXTENSION_MAP.get(self.item_type, (None, None))
		if ext_doctype and frappe.db.exists(ext_doctype, self.ref_name):
			frappe.delete_doc(ext_doctype, self.ref_name, ignore_permissions=True)

	@staticmethod
	def generate_slug(title):
		slug = title.lower().strip()
		slug = re.sub(r"[^a-z0-9\s-]", "", slug)
		slug = re.sub(r"[\s]+", "-", slug)
		slug = re.sub(r"-+", "-", slug).strip("-")
		return slug
