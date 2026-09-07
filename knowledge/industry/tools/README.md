# Tools — Index

Interactive tools for Australian insulation compliance.

| File | Tool | Description |
|------|------|-------------|
| [compliance_tool.html](compliance_tool.html) | **Compliance Tool** | Interactive web tool (single HTML file) with 4 tabs |

## Compliance Tool features

1. **📍 Climate Zone Finder** — select state + city → get NCC climate zone (covers 60+ Australian locations across all states/territories).
2. **📋 NCC Compliance** — select climate zone + building class → get ceiling/wall/floor/slab R-values, vapour membrane class, and cavity requirements.
3. **🔥 BAL Reference** — select BAL rating → get material suitability (glasswool, rockwool, polyester, EPS/XPS, PIR, foil).
4. **🔊 Sound Requirements** — select building class → get Rw+Ctr, Rw, Ln,w requirements.

## How to use

Open [compliance_tool.html](compliance_tool.html) in any web browser (no dependencies, fully self-contained). Works offline.

## Data sources

- Climate zones: ABCB climate zone map (8 NCC zones)
- NCC requirements: NCC 2022/2025 DTS provisions (Part 13.2, Section J, Part F8, Part F7)
- BAL: AS 3959:2018
- Sound: NCC Part F7 / Part 10.7

## Notes

- R-values shown are DTS minimums. A 7-star NatHERS assessment may require higher values.
- Climate zone boundaries can vary — verify against the official ABCB Climate Map for critical compliance.
- BAL must be determined by an AS 3959 site assessment.

## Related

- `../compliance/` — full NCC/ABCB compliance digests (the data behind this tool)
- `../customer_support/` — troubleshooting playbook
