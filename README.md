# Insulation Product Enquiry Knowledge Base

This repository contains validated product knowledge for a customer enquiry and callback bot.

The local POC may recommend a manufacturer-supported product family. Exact product selection and all production behaviour remain governed by [`BOT_POLICY.md`](BOT_POLICY.md).

## Structure

- [`knowledge/thermotec/`](knowledge/thermotec/README.md) — Thermotec product-family guides used to understand and qualify enquiries.
- [`knowledge/thermotec/families.json`](knowledge/thermotec/families.json) — the 13-family structured catalogue used by the Streamlit matching and range-explorer views.
- [`knowledge/fletcher/`](knowledge/fletcher/README.md) — Fletcher product-family guides for all 134 Fletcher-labelled rows in `Sheet1`.
- [`knowledge/fletcher/families.json`](knowledge/fletcher/families.json) — the 18-family Fletcher catalogue used in cross-manufacturer comparison.
- [`notebooks/01_thermotec_poc.ipynb`](notebooks/01_thermotec_poc.ipynb) — maps and validates all 280 Thermotec rows currently in `Sheet1`.
- [`scripts/validate_fletcher.py`](scripts/validate_fletcher.py) — maps and validates the 134 Fletcher rows and writes `reports/fletcher_validation_report.csv`.

## Data model

The Google Sheet remains the structured product catalogue and source dataset. The Markdown files provide context the enquiry bot needs to interpret customer questions, including:

- intended applications and product roles;
- enquiry-routing and exclusion rules;
- important limitations and installation constraints;
- approved response language;
- links to official manufacturer sources.

Ratings guide follow-up questions, candidate ordering and the callback brief. In local demo mode, they may support a family-level recommendation when the application also matches; they never authorise SKU, grade, quantity or compliance selection.

Performance values must retain their test metric and system context. For example, `R` and `Rw` represent different properties and must never be treated as interchangeable.

## Validation convention

Each product-family file includes front matter with a stable `family_id`, manufacturer, validation status, and validation date. Product claims should be traceable to the official sources listed in that file.

The proof of concept currently compares Thermotec and Fletcher. A family may be recommended only when its identity is supported; exact SKU selection still requires row-level evidence and human review.

## Team demonstration

The local Streamlit demonstration compares 31 Fletcher and Thermotec families across acoustic, thermal, membrane, HVAC, pipe, roof and accessory applications. The user can compare both manufacturers or restrict the result to one. It recommends the best supported family, exposes evidence limitations, includes a searchable range explorer, produces a callback brief and demonstrates a human-approved mock MYOB quote handoff. It does not access live Aircall, Google Drive or MYOB data.

Run it from Anaconda Prompt:

```powershell
cd "C:\Users\ganes\OneDrive\Documents\GitHub\Insulation_Product_Selection"
streamlit run app.py
```
