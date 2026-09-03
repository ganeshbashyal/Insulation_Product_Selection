# Insulation Product Selection Knowledge Base

This repository contains validated, bot-ready product knowledge for insulation and acoustic product selection.

## Structure

- [`knowledge/thermotec/`](knowledge/thermotec/README.md) — Thermotec product-family guides and selection rules.

## Data model

The Google Sheet remains the structured product catalogue and source dataset. The Markdown files in this repository provide the context a selection bot needs to interpret that data, including:

- intended applications and product roles;
- selection and exclusion rules;
- important limitations and installation constraints;
- approved response language;
- links to official manufacturer sources.

Performance values must retain their test metric and system context. For example, `R` and `Rw` represent different properties and must never be treated as interchangeable.

## Validation convention

Each product-family file includes front matter with a stable `family_id`, manufacturer, validation status, and validation date. Product claims should be traceable to the official sources listed in that file.

The knowledge base is being completed manufacturer by manufacturer, beginning with Thermotec.
