# Thermotec product-family knowledge base

Bot-facing product knowledge for Thermotec Australia. Each file represents a technical family, not an individual stock SKU. SKU records should link to these files through the `family_id` in each file's front matter.

## Family index

| Family ID | Product family | File | Status |
| --- | --- | --- | --- |
| `THERMOTEC_NUWAVE_BASE_MLV` | NuWave Mass Loaded Vinyl Acoustic Barrier | [nuwave-mass-loaded-vinyl.md](nuwave-mass-loaded-vinyl.md) | Manufacturer supported |
| `THERMOTEC_NUWAVE_UNDERLAY` | Thermotec Carpet Underlay / NuWave underlay | [nuwave-underlay.md](nuwave-underlay.md) | Manufacturer supported; performance figures pending TDS extraction |
| `THERMOTEC_NUWAVE_FENCE_MLV` | NuWave UV-treated Fence MLV | [nuwave-fence-mlv.md](nuwave-fence-mlv.md) | Owned-site source only; manufacturer and availability verification required |
| `THERMOTEC_NUWAVE_FOIL_FACED_MLV` | NuWave 4-Zero Foil-faced MLV | [nuwave-foil-faced-mlv.md](nuwave-foil-faced-mlv.md) | Owned-site source only; manufacturer technical evidence required |
| `THERMOTEC_NUWRAP_5` | NuWrap 5 Acoustic Pipe Lagging | [nuwrap-5.md](nuwrap-5.md) | Manufacturer supported |
| `THERMOTEC_NUWRAP_XTRAFLEX` | NuWrap XtraFlex | [nuwrap-xtraflex.md](nuwrap-xtraflex.md) | Manufacturer supported |
| `THERMOTEC_4_ZERO` | 4-Zero Fire Retardant Pipe Insulation | [4-zero-pipe-insulation.md](4-zero-pipe-insulation.md) | Manufacturer supported |
| `THERMOTEC_E_FLEX_HT` | E-Flex HT Solar Pipe Insulation | [e-flex-ht.md](e-flex-ht.md) | Manufacturer supported |
| `THERMOTEC_E_FLEX_ST` | E-Flex ST Hot Water, HVAC and Refrigeration Pipe Insulation | [e-flex-st.md](e-flex-st.md) | Manufacturer supported |
| `THERMOTEC_ROCKWOOL_PIPE` | Rockwool Pipe Insulation | [rockwool-pipe-insulation.md](rockwool-pipe-insulation.md) | Manufacturer supported |
| `THERMOTEC_E_THERM` | E-Therm Reflective Roof and Wall Insulation | [e-therm-reflective-insulation.md](e-therm-reflective-insulation.md) | Manufacturer supported; system R-values pending TDS extraction |
| `THERMOTEC_MAXTAPE_FR` | MaxTape FR Insulating Foam Tape | [maxtape-fr.md](maxtape-fr.md) | Manufacturer supported; fire classification pending TDS extraction |
| `THERMOTEC_MAXFLEX_PIPE` | Maxflex Coil Pipe Insulation | [maxflex-pipe.md](maxflex-pipe.md) | Identity unverified; blocked from selection and quotation |

The Streamlit demonstration reads [families.json](families.json), which gives each family the same applications, discovery keywords, customer-priority scores, evidence state, questions and human-review gates used by the interface. The ratings are discovery aids—not product performance ratings or compliance certificates.

## Bot retrieval rule

1. Match the SKU to one `family_id`.
2. Load the corresponding family file.
3. Overlay only SKU-specific facts such as dimensions, surface mass, pack quantity and validated performance.
4. Apply the file's limitations and `do_not_claim` rules before answering.
5. Prefer the current manufacturer source when spreadsheet data conflicts with a family file.

Do not copy a technical rating between families merely because both products contain foam, foil, mineral wool or mass loaded vinyl.
