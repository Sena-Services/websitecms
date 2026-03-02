import frappe

from senaerp_platform.registry.embedding import (
	fulltext_search,
	semantic_search,
)


SEARCH_FIELDS = [
	"name",
	"slug",
	"title",
	"item_type",
	"category",
	"description",
	"trust_status",
	"featured",
	"author",
	"install_count",
	"image",
]

_ORDER_FIELDS = {
	"featured": "featured DESC, modified DESC",
	"newest": "creation DESC",
	"updated": "modified DESC",
	"popular": "install_count DESC",
	"alpha": "title ASC",
}

EXTENSION_MAP = {
	"Agent": "Registry Agent",
	"Tool": "Registry Tool",
	"Skill": "Registry Skill",
	"UI": "Registry UI",
	"Logic": "Registry Logic",
}

EXTENSION_CHILDREN = {
	"Registry Agent": ["agent_tools", "agent_skills"],
}

# Direct link fields on extension DocTypes that point to other extensions
_EXT_LINK_FIELDS = {
	"Registry Agent": {
		"ui": "Registry UI",
		"logic": "Registry Logic",
	},
}

# Link fields on child table rows that point to extension DocTypes
_CHILD_LINK_FIELDS = {
	"Registry Agent Tool": {"tool": "Registry Tool"},
	"Registry Agent Skill": {"skill": "Registry Skill"},
}

# Map child table fieldname -> child DocType
_CHILD_TABLE_DOCTYPES = {
	"agent_tools": "Registry Agent Tool",
	"agent_skills": "Registry Agent Skill",
}


@frappe.whitelist(allow_guest=True)
def search(
	q=None,
	item_type=None,
	category=None,
	tags=None,
	trust_status="approved",
	featured_only=False,
	sort_by="featured",
	limit=20,
	offset=0,
):
	limit = min(int(limit), 100)
	offset = int(offset)
	featured_only = frappe.utils.sbool(featured_only)

	filters = {}
	if trust_status:
		filters["trust_status"] = trust_status
	if item_type:
		filters["item_type"] = item_type
	if category:
		filters["category"] = category
	if featured_only:
		filters["featured"] = 1

	order_fields = _ORDER_FIELDS.get(sort_by, _ORDER_FIELDS["featured"])

	if q:
		# Try semantic search first (embedding cosine similarity)
		semantic_results = semantic_search(q, filters=filters, limit=limit)
		if semantic_results is not None:
			items = semantic_results
			total = len(items)
			# Apply tag filter post-search if needed
			if tags:
				items = _filter_by_tags(items, tags)
				total = len(items)
			items = _attach_tags(items)
			return {"items": items, "total": total, "limit": limit, "offset": offset}

		# Fall back to FULLTEXT MATCH AGAINST
		try:
			sql_order = ", ".join(f"r.{p.strip()}" for p in order_fields.split(","))
			items, total = fulltext_search(q, filters=filters, order_by=sql_order, limit=limit, offset=offset)
			if tags:
				items = _filter_by_tags(items, tags)
				total = len(items)
			items = _attach_tags(items)
			return {"items": items, "total": total, "limit": limit, "offset": offset}
		except Exception:
			pass

		# Final fallback: LIKE search
		items, total = _like_search(q, tags, filters, order_fields, limit, offset)
	elif tags:
		items, total = _like_search(None, tags, filters, order_fields, limit, offset)
	else:
		items = frappe.get_list(
			"Registry",
			filters=filters,
			fields=SEARCH_FIELDS,
			order_by=order_fields,
			limit_page_length=limit,
			start=offset,
		)
		total = frappe.db.count("Registry", filters=filters)

	items = _attach_tags(items)
	return {"items": items, "total": total, "limit": limit, "offset": offset}


def _attach_tags(items):
	for item in items:
		if "name" in item:
			item["tags"] = [
				t.tag
				for t in frappe.get_all(
					"Registry Tag", filters={"parent": item["name"]}, fields=["tag"]
				)
			]
			del item["name"]
		elif "tags" not in item:
			item["tags"] = []
	return items


def _filter_by_tags(items, tags_str):
	tag_list = [t.strip().lower() for t in tags_str.split(",") if t.strip()]
	if not tag_list:
		return items
	filtered = []
	for item in items:
		item_name = item.get("name")
		if not item_name:
			continue
		item_tags = {
			t.tag.lower()
			for t in frappe.get_all("Registry Tag", filters={"parent": item_name}, fields=["tag"])
		}
		if all(t in item_tags for t in tag_list):
			filtered.append(item)
	return filtered


def _like_search(q, tags, filters, order_by, limit, offset):
	"""LIKE-based text search (last resort fallback)."""
	conditions = []
	values = {}

	for field, value in filters.items():
		conditions.append(f"r.`{field}` = %({field})s")
		values[field] = value

	if q:
		conditions.append(
			"(r.title LIKE %(q_like)s OR r.description LIKE %(q_like)s OR rt_search.tag LIKE %(q_like)s)"
		)
		values["q_like"] = f"%{q}%"

	if tags:
		tag_list = [t.strip().lower() for t in tags.split(",") if t.strip()]
		for i, tag in enumerate(tag_list):
			key = f"tag_{i}"
			conditions.append(
				f"EXISTS (SELECT 1 FROM `tabRegistry Tag` rt{i} WHERE rt{i}.parent = r.name AND rt{i}.tag = %({key})s)"
			)
			values[key] = tag

	where = " AND ".join(conditions) if conditions else "1=1"
	sql_order = ", ".join(f"r.{p.strip()}" for p in order_by.split(","))

	count_sql = f"""
		SELECT COUNT(DISTINCT r.name)
		FROM `tabRegistry` r
		LEFT JOIN `tabRegistry Tag` rt_search ON rt_search.parent = r.name
		WHERE {where}
	"""
	total = frappe.db.sql(count_sql, values)[0][0]

	sql = f"""
		SELECT DISTINCT r.name, r.slug, r.title, r.item_type, r.category,
			r.description, r.trust_status, r.featured, r.author, r.install_count,
			r.image
		FROM `tabRegistry` r
		LEFT JOIN `tabRegistry Tag` rt_search ON rt_search.parent = r.name
		WHERE {where}
		ORDER BY {sql_order}
		LIMIT %(limit)s OFFSET %(offset)s
	"""
	values["limit"] = limit
	values["offset"] = offset

	items = frappe.db.sql(sql, values, as_dict=True)
	return items, total


@frappe.whitelist(allow_guest=True)
def get_item(slug=None):
	if not slug:
		frappe.throw("slug is required", frappe.MandatoryError)

	reg = frappe.db.get_value(
		"Registry",
		{"slug": slug},
		["name", "slug", "title", "item_type", "category", "description",
		 "trust_status", "featured", "visibility", "ref_name", "install_count",
		 "author", "version", "source_url", "readme", "dotmatrix_avatar"],
		as_dict=True,
	)

	if not reg:
		frappe.throw(f"Registry item with slug '{slug}' not found", frappe.DoesNotExistError)

	reg["tags"] = [
		t.tag
		for t in frappe.get_all(
			"Registry Tag", filters={"parent": reg["name"]}, fields=["tag"]
		)
	]

	extension = None
	if reg.get("ref_name"):
		ext_doctype = EXTENSION_MAP.get(reg["item_type"])
		if ext_doctype:
			extension = _get_extension(ext_doctype, reg["ref_name"])

	parents = _get_parents(reg["item_type"], reg["ref_name"]) if reg.get("ref_name") else []

	del reg["name"]
	del reg["ref_name"]

	result = {"registry": reg, "extension": extension}
	if parents:
		result["parents"] = parents
	return result


def _get_extension(ext_doctype, ext_name):
	ext = frappe.get_doc(ext_doctype, ext_name)
	data = ext.as_dict()

	for key in ["doctype", "name", "owner", "creation", "modified", "modified_by",
				"docstatus", "idx", "registry"]:
		data.pop(key, None)

	# Resolve direct link fields to Registry items
	for field, target_dt in _EXT_LINK_FIELDS.get(ext_doctype, {}).items():
		if data.get(field):
			ref = _resolve_to_registry(target_dt, data[field])
			if ref:
				data[f"{field}_ref"] = ref

	# Clean and resolve child table rows
	child_fields = EXTENSION_CHILDREN.get(ext_doctype, [])
	for field in child_fields:
		if field in data and isinstance(data[field], list):
			child_dt = _CHILD_TABLE_DOCTYPES.get(field)
			data[field] = [_clean_child_row(row, child_dt) for row in data[field]]

	return data


def _clean_child_row(row, child_doctype=None):
	if not isinstance(row, dict):
		row = row.as_dict()
	else:
		row = dict(row)
	for key in ["doctype", "name", "owner", "creation", "modified", "modified_by",
				"docstatus", "parent", "parentfield", "parenttype", "idx"]:
		row.pop(key, None)

	# Resolve link fields to Registry items
	if child_doctype:
		for field, target_dt in _CHILD_LINK_FIELDS.get(child_doctype, {}).items():
			if row.get(field):
				ref = _resolve_to_registry(target_dt, row[field])
				if ref:
					row[f"{field}_ref"] = ref

	return row


def _resolve_to_registry(ext_doctype, ext_name):
	"""Resolve an extension DocType name back to its parent Registry item."""
	registry_name = frappe.db.get_value(ext_doctype, ext_name, "registry")
	if not registry_name:
		return None
	return frappe.db.get_value(
		"Registry", registry_name,
		["slug", "title", "item_type"], as_dict=True,
	)


# ---------------------------------------------------------------------------
# Parent (reverse) lookups
# ---------------------------------------------------------------------------

# Child-table reverse: child_doctype -> (link_field, parent_extension_doctype)
_CHILD_PARENT_MAP = {
	"Registry Tool": [("Registry Agent Tool", "tool", "Registry Agent")],
	"Registry Skill": [("Registry Agent Skill", "skill", "Registry Agent")],
}

# Direct-field reverse: extension_doctype -> [(field, parent_extension_doctype)]
_DIRECT_PARENT_MAP = {
	"Registry UI": [("ui", "Registry Agent")],
	"Registry Logic": [("logic", "Registry Agent")],
}


def _get_parents(item_type, ref_name):
	"""Find direct parents that reference this item."""
	if not ref_name:
		return []

	ext_doctype = EXTENSION_MAP.get(item_type)
	if not ext_doctype:
		return []

	parents = []
	seen = set()

	# Reverse child-table lookups
	for child_dt, link_field, parent_ext_dt in _CHILD_PARENT_MAP.get(ext_doctype, []):
		rows = frappe.get_all(
			child_dt,
			filters={link_field: ref_name},
			fields=["parent"],
		)
		for row in rows:
			reg_name = frappe.db.get_value(parent_ext_dt, row.parent, "registry")
			if reg_name and reg_name not in seen:
				seen.add(reg_name)
				ref = frappe.db.get_value(
					"Registry", reg_name,
					["slug", "title", "item_type"], as_dict=True,
				)
				if ref:
					parents.append(ref)

	# Reverse direct-field lookups
	for field, parent_ext_dt in _DIRECT_PARENT_MAP.get(ext_doctype, []):
		rows = frappe.get_all(
			parent_ext_dt,
			filters={field: ref_name},
			fields=["registry"],
		)
		for row in rows:
			if row.registry and row.registry not in seen:
				seen.add(row.registry)
				ref = frappe.db.get_value(
					"Registry", row.registry,
					["slug", "title", "item_type"], as_dict=True,
				)
				if ref:
					parents.append(ref)

	return parents


# ---------------------------------------------------------------------------
# Install package
# ---------------------------------------------------------------------------

INSTALL_ORDER = {
	"Skill": 1, "Tool": 2, "UI": 3, "Logic": 4, "Agent": 5,
}


@frappe.whitelist(allow_guest=True)
def get_install_package(slug: str | None = None):
	"""Return all dependencies for a registry item as a flat install-ordered list.

	Each item includes full extension data. Link references between items
	use slugs (not internal names like RA-00005).
	"""
	if not slug:
		frappe.throw("slug is required", frappe.MandatoryError)

	reg = frappe.db.get_value(
		"Registry", {"slug": slug},
		["name", "trust_status"],
		as_dict=True,
	)
	if not reg:
		frappe.throw(f"Registry item '{slug}' not found", frappe.DoesNotExistError)
	if reg.trust_status != "approved":
		frappe.throw(f"Registry item '{slug}' is not approved for installation")

	visited: dict[str, bool] = {}
	_collect_deps(reg.name, visited)

	items = []
	for reg_name in visited:
		item = _build_package_item(reg_name)
		if item:
			items.append(item)

	items.sort(key=lambda x: INSTALL_ORDER.get(x["item_type"], 99))
	return {"items": items}


def _collect_deps(registry_name: str, visited: dict[str, bool]) -> None:
	"""Recursively collect all dependencies for a registry item."""
	if registry_name in visited:
		return
	visited[registry_name] = True

	reg = frappe.db.get_value(
		"Registry", registry_name,
		["item_type", "ref_name"], as_dict=True,
	)
	if not reg or not reg.ref_name:
		return

	ext_doctype = EXTENSION_MAP.get(reg.item_type)
	if not ext_doctype:
		return

	ext = frappe.get_doc(ext_doctype, reg.ref_name)

	# Direct link fields → other extensions
	for field, target_dt in _EXT_LINK_FIELDS.get(ext_doctype, {}).items():
		ext_ref = ext.get(field)
		if ext_ref:
			dep_reg = frappe.db.get_value(target_dt, ext_ref, "registry")
			if dep_reg:
				_collect_deps(dep_reg, visited)

	# Child table link fields → other extensions
	for child_field in EXTENSION_CHILDREN.get(ext_doctype, []):
		child_dt = _CHILD_TABLE_DOCTYPES.get(child_field)
		if not child_dt:
			continue
		for row in ext.get(child_field) or []:
			for link_field, target_dt in _CHILD_LINK_FIELDS.get(child_dt, {}).items():
				ext_ref = row.get(link_field)
				if ext_ref:
					dep_reg = frappe.db.get_value(target_dt, ext_ref, "registry")
					if dep_reg:
						_collect_deps(dep_reg, visited)


def _build_package_item(registry_name: str) -> dict | None:
	"""Build a single item dict for the install package."""
	reg = frappe.db.get_value(
		"Registry", registry_name,
		["slug", "title", "item_type", "description", "ref_name"],
		as_dict=True,
	)
	if not reg:
		return None

	item = {
		"item_type": reg.item_type,
		"title": reg.title,
		"slug": reg.slug,
		"description": reg.description,
	}

	ext_doctype = EXTENSION_MAP.get(reg.item_type)
	if not ext_doctype or not reg.ref_name:
		return item

	ext = frappe.get_doc(ext_doctype, reg.ref_name)
	data = ext.as_dict()

	# Strip Frappe meta fields
	for key in ("doctype", "name", "owner", "creation", "modified",
				"modified_by", "docstatus", "idx", "registry"):
		data.pop(key, None)

	# Resolve direct link fields → slugs
	for field, target_dt in _EXT_LINK_FIELDS.get(ext_doctype, {}).items():
		if data.get(field):
			data[field] = _ext_to_slug(target_dt, data[field]) or data[field]

	# Clean child rows and resolve link fields → slugs
	for child_field in EXTENSION_CHILDREN.get(ext_doctype, []):
		if child_field not in data or not isinstance(data[child_field], list):
			continue
		child_dt = _CHILD_TABLE_DOCTYPES.get(child_field)
		cleaned = []
		for row in data[child_field]:
			if not isinstance(row, dict):
				row = row.as_dict()
			else:
				row = dict(row)
			for key in ("doctype", "name", "owner", "creation", "modified",
						"modified_by", "docstatus", "parent", "parentfield",
						"parenttype", "idx"):
				row.pop(key, None)
			if child_dt:
				for link_field, target_dt in _CHILD_LINK_FIELDS.get(child_dt, {}).items():
					if row.get(link_field):
						row[link_field] = _ext_to_slug(target_dt, row[link_field]) or row[link_field]
			cleaned.append(row)
		data[child_field] = cleaned

	item["extension"] = data
	return item


def _ext_to_slug(ext_doctype: str, ext_name: str) -> str | None:
	"""Resolve an extension doc name (e.g. RA-00005) to its Registry slug."""
	reg_name = frappe.db.get_value(ext_doctype, ext_name, "registry")
	if not reg_name:
		return None
	return frappe.db.get_value("Registry", reg_name, "slug")


# ---------------------------------------------------------------------------
# Publish (create/update registry items from tenant)
# ---------------------------------------------------------------------------

@frappe.whitelist(methods=["POST"])
def publish_item(payload=None):
	"""Create or update a Registry doc + extension from a tenant publish request.

	Payload shape:
		{
			"item_type": "Tool"|"Skill"|"UI"|"Logic"|"Agent",
			"title": str,
			"description": str,
			"slug": str (optional — if set, triggers update path),
			"version": str (optional),
			"author": str (optional),
			"extension": { ... type-specific fields ... }
		}
	"""
	if isinstance(payload, str):
		import json
		payload = json.loads(payload)
	if not payload:
		payload = frappe.parse_json(frappe.request.data) if frappe.request else {}

	item_type = payload.get("item_type")
	title = payload.get("title")
	extension = payload.get("extension", {})

	if not item_type or not title:
		frappe.throw("item_type and title are required")

	from senaerp_platform.registry.doctype.registry.registry import EXTENSION_MAP
	if item_type not in EXTENSION_MAP:
		frappe.throw(f"Invalid item_type: {item_type}")

	slug = payload.get("slug")
	action = "created"

	if slug:
		# Update path: find existing registry doc by slug
		reg_name = frappe.db.get_value("Registry", {"slug": slug}, "name")
		if not reg_name:
			frappe.throw(f"Registry item with slug '{slug}' not found")
		reg = frappe.get_doc("Registry", reg_name)
		reg.title = title
		reg.description = payload.get("description", reg.description)
		if payload.get("version"):
			reg.version = payload["version"]
		if payload.get("author"):
			reg.author = payload["author"]
		reg.save(ignore_permissions=True)
		action = "updated"
	else:
		# Check if a matching Registry item already exists (upsert semantics)
		existing_name = _find_existing_registry(item_type, title, extension)
		if existing_name:
			reg = frappe.get_doc("Registry", existing_name)
			reg.title = title
			reg.description = payload.get("description", reg.description)
			if payload.get("version"):
				reg.version = payload["version"]
			if payload.get("author"):
				reg.author = payload["author"]
			reg.save(ignore_permissions=True)
			action = "updated"
		else:
			# Create path
			reg = frappe.new_doc("Registry")
			reg.title = title
			reg.item_type = item_type
			reg.description = payload.get("description", "")
			reg.trust_status = "approved"
			if payload.get("version"):
				reg.version = payload["version"]
			if payload.get("author"):
				reg.author = payload["author"]
			reg.insert(ignore_permissions=True)
			# after_insert creates the extension doc and sets ref_name

	# Populate extension fields
	ext_doctype = EXTENSION_MAP[item_type][0]
	if reg.ref_name:
		ext = frappe.get_doc(ext_doctype, reg.ref_name)
		_populate_extension(ext, extension, item_type)
		ext.save(ignore_permissions=True)

	frappe.db.commit()

	return {
		"slug": reg.slug,
		"ref_name": reg.ref_name,
		"action": action,
	}


# Unique key fields on extension DocTypes used for upsert matching
_EXT_UNIQUE_KEYS = {
	"Tool": ("Registry Tool", "tool_name"),
	"Skill": None,  # no unique key beyond title
	"UI": None,
	"Logic": None,
	"Agent": None,
}


def _find_existing_registry(item_type: str, title: str, extension: dict) -> str | None:
	"""Find an existing Registry doc by title or extension unique key."""
	# First try exact title + item_type match
	name = frappe.db.get_value("Registry", {"title": title, "item_type": item_type}, "name")
	if name:
		return name

	# Try matching via extension unique key (e.g. tool_name for Tool)
	key_info = _EXT_UNIQUE_KEYS.get(item_type)
	if key_info and extension:
		ext_doctype, key_field = key_info
		key_value = extension.get(key_field)
		if key_value:
			ref_name = frappe.db.get_value(ext_doctype, {key_field: key_value}, "registry")
			if ref_name:
				return ref_name

	return None


def _populate_extension(ext, data: dict, item_type: str) -> None:
	"""Set extension fields from publish payload data."""

	if item_type == "Tool":
		for field in ("tool_name", "tool_class", "description", "instructions",
					  "handler_path", "handler_source", "parameters_schema", "requires_config"):
			if data.get(field) is not None:
				ext.set(field, data[field])

	elif item_type == "Skill":
		for field in ("skill_type", "skill_content"):
			if data.get(field) is not None:
				ext.set(field, data[field])

	elif item_type == "UI":
		for field in ("ui_mode", "framework", "route", "source_path",
					  "source_url", "source_ref"):
			if data.get(field) is not None:
				ext.set(field, data[field])

	elif item_type == "Logic":
		for field in ("module_name", "tier", "logic_doctypes", "source_path",
					  "source_url", "source_ref"):
			if data.get(field) is not None:
				ext.set(field, data[field])

	elif item_type == "Agent":
		for field in ("is_system", "model", "selectable_models", "failover_chain",
					  "temperature", "max_turns", "thinking_mode", "thinking_budget"):
			if data.get(field) is not None:
				ext.set(field, data[field])

		# Resolve UI slug → Registry UI extension name
		ui_slug = data.get("ui_slug")
		if ui_slug:
			ref_name = frappe.db.get_value(
				"Registry", {"slug": ui_slug, "item_type": "UI"}, "ref_name"
			)
			if ref_name:
				ext.set("ui", ref_name)

		# Resolve Logic slug → Registry Logic extension name
		logic_slug = data.get("logic_slug")
		if logic_slug:
			ref_name = frappe.db.get_value(
				"Registry", {"slug": logic_slug, "item_type": "Logic"}, "ref_name"
			)
			if ref_name:
				ext.set("logic", ref_name)

		# Resolve agent_tools child table
		if data.get("agent_tools"):
			ext.set("agent_tools", [])
			for row in data["agent_tools"]:
				tool_slug = row.get("tool_slug")
				if tool_slug:
					ref_name = frappe.db.get_value(
						"Registry", {"slug": tool_slug, "item_type": "Tool"}, "ref_name"
					)
					if ref_name:
						ext.append("agent_tools", {
							"tool": ref_name,
							"enabled": row.get("enabled", 1),
						})

		# Resolve agent_skills child table
		if data.get("agent_skills"):
			ext.set("agent_skills", [])
			for row in data["agent_skills"]:
				skill_slug = row.get("skill_slug")
				if skill_slug:
					ref_name = frappe.db.get_value(
						"Registry", {"slug": skill_slug, "item_type": "Skill"}, "ref_name"
					)
					if ref_name:
						ext.append("agent_skills", {
							"skill": ref_name,
							"activation": row.get("activation", "core"),
							"enabled": row.get("enabled", 1),
						})
