# Thermotec POC — first run

This proof of concept validates Thermotec SKU rows against the product-family knowledge files in this repository. In the local Streamlit demo it may recommend a manufacturer-supported family, while exact selection and quotation remain human-controlled. It keeps the Google Sheet as the editable source and does not write back to it.

## Step 1 — export the current Google Sheet

1. Open the product-master Google Sheet.
2. Choose **File → Download → Microsoft Excel (.xlsx)**.
3. Rename the downloaded file to `Product_Master_Bot.xlsx`.
4. Place it in this repository at `data/raw/Product_Master_Bot.xlsx`.

The raw workbook is ignored by Git so inventory quantities and source data are not accidentally committed.

## Step 2 — start Jupyter

### Using Anaconda Navigator

1. Open **Anaconda Navigator**.
2. Launch **JupyterLab**.
3. Browse to this repository.
4. Open `notebooks/01_thermotec_poc.ipynb`.
5. Choose **Run → Run All Cells**.

### Using Anaconda Prompt

```powershell
cd "C:\Users\ganes\OneDrive\Documents\GitHub\Insulation_Product_Selection"
jupyter lab
```

Then open `notebooks/01_thermotec_poc.ipynb` and run all cells.

## Step 3 — review the outputs

The notebook creates:

- `reports/thermotec_validation_report.csv` — every Thermotec SKU with its family mapping and validation outcome;
- `data/processed/thermotec_callback_reference.csv` — validated internal reference rows available when preparing a staff callback brief.

The final notebook cell prints a summary. A family marked `MISSING KNOWLEDGE FILE` must be researched and documented before its information can be used in an enquiry. A row marked `SOURCE NOT READY` has a family file but its spreadsheet evidence/status still needs correction.

Read `BOT_POLICY.md` before changing conversational behaviour. Passing the validation gate can support a family-level demo recommendation; it never authorises SKU, grade, quantity, compliance or installed-performance selection.

## Important interpretation rules

- Thermal `R`, airborne-sound `Rw`, and absorption ratings such as `NRC` or `αw` are separate metrics.
- `RW 120kg` in a stonewool product name describes a rockwool density family; `120 kg/m³` is not an `Rw 120` acoustic rating.
- A product-family rating must not be copied to a different family or presented as the result for a complete installed construction.
- Missing evidence remains missing; the notebook does not invent values.
