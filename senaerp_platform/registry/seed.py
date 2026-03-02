"""Registry seed data.

Seeds pre-defined Composio toolkits on every bench migrate.
"""

from __future__ import annotations

import frappe


def seed_registry() -> None:
	"""Seed the registry with pre-defined external tools. Idempotent."""
	_seed_composio_toolkits()
	frappe.db.commit()


_COMPOSIO_LOGO = "https://logos.composio.dev/api"

COMPOSIO_TOOLKITS = [
	{
		"slug": "gmail",
		"title": "Gmail",
		"description": "Send, read, and manage Gmail emails. Actions: send email, read inbox, search messages, manage labels, drafts, and threads.",
	},
	{
		"slug": "slack",
		"title": "Slack",
		"description": "Send messages, manage channels, and interact with Slack workspaces. Actions: post message, list channels, upload files, manage users.",
	},
	{
		"slug": "github",
		"title": "GitHub",
		"description": "Manage repositories, issues, pull requests, and GitHub workflows. Actions: create issue, list PRs, manage repos, review code.",
	},
	{
		"slug": "googlecalendar",
		"title": "Google Calendar",
		"description": "Create, read, and manage Google Calendar events. Actions: create event, list events, update event, delete event.",
	},
	{
		"slug": "notion",
		"title": "Notion",
		"description": "Create and manage Notion pages, databases, and blocks. Actions: create page, query database, update block, search.",
	},
	{
		"slug": "googlesheets",
		"title": "Google Sheets",
		"description": "Read and write Google Sheets data. Actions: read range, write range, create spreadsheet, manage sheets.",
	},
	{
		"slug": "outlook",
		"title": "Outlook",
		"description": "Send, read, and manage Outlook/Microsoft 365 emails. Actions: send email, read inbox, manage folders, search messages.",
	},
	{
		"slug": "googledrive",
		"title": "Google Drive",
		"description": "Manage files and folders in Google Drive. Actions: upload file, list files, share file, create folder.",
	},
	{
		"slug": "googledocs",
		"title": "Google Docs",
		"description": "Create and edit Google Docs. Actions: create document, read content, insert text, update formatting.",
	},
	{
		"slug": "hubspot",
		"title": "HubSpot",
		"description": "Manage CRM contacts, deals, and companies in HubSpot. Actions: create contact, update deal, list companies, manage pipelines.",
	},
	{
		"slug": "linear",
		"title": "Linear",
		"description": "Manage issues, projects, and teams in Linear. Actions: create issue, update status, list projects, manage cycles.",
	},
	{
		"slug": "airtable",
		"title": "Airtable",
		"description": "Read and write Airtable records. Actions: list records, create record, update record, delete record.",
	},
	{
		"slug": "jira",
		"title": "Jira",
		"description": "Manage Jira issues, projects, and sprints. Actions: create issue, update issue, search, manage transitions.",
	},
	{
		"slug": "twitter",
		"title": "Twitter / X",
		"description": "Post tweets, read timelines, and manage Twitter/X interactions. Actions: post tweet, search tweets, like, retweet.",
	},
	{
		"slug": "discord",
		"title": "Discord",
		"description": "Send messages and manage Discord servers. Actions: send message, list channels, manage roles, create webhooks.",
	},
	{
		"slug": "figma",
		"title": "Figma",
		"description": "Read and interact with Figma design files. Actions: get file, list components, export assets, read comments.",
	},
	{
		"slug": "supabase",
		"title": "Supabase",
		"description": "Query and manage Supabase databases. Actions: select, insert, update, delete rows, manage tables.",
	},
	{
		"slug": "youtube",
		"title": "YouTube",
		"description": "Manage YouTube videos and channels. Actions: search videos, get video details, list playlists, manage comments.",
	},
	{
		"slug": "reddit",
		"title": "Reddit",
		"description": "Browse and interact with Reddit. Actions: get posts, submit post, list subreddits, manage comments.",
	},
	{
		"slug": "googletasks",
		"title": "Google Tasks",
		"description": "Create and manage Google Tasks. Actions: create task, list tasks, update task, complete task.",
	},
]


def _seed_composio_toolkits() -> None:
	"""Seed Composio toolkits as Registry Tool items."""
	for tk in COMPOSIO_TOOLKITS:
		slug = tk["slug"]
		title = tk["title"]
		logo = f"{_COMPOSIO_LOGO}/{slug}"

		ref_name = frappe.db.get_value(
			"Registry",
			{"title": title, "item_type": "Tool", "author": "Composio"},
			"ref_name",
		)

		if ref_name:
			reg = frappe.get_doc("Registry", {"title": title, "item_type": "Tool", "author": "Composio"})
			reg.image = logo
			reg.save(ignore_permissions=True)

			ext = frappe.get_doc("Registry Tool", ref_name)
			ext.tool_name = slug
			ext.tool_class = "external"
			ext.description = tk["description"]
			ext.save(ignore_permissions=True)
			continue

		reg = frappe.new_doc("Registry")
		reg.title = title
		reg.item_type = "Tool"
		reg.description = tk["description"]
		reg.trust_status = "approved"
		reg.author = "Composio"
		reg.image = logo
		reg.insert(ignore_permissions=True)

		ext = frappe.get_doc("Registry Tool", reg.ref_name)
		ext.tool_name = slug
		ext.tool_class = "external"
		ext.description = tk["description"]
		ext.save(ignore_permissions=True)
