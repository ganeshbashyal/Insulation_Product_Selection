# Principles — Deep Dive Index

Engineering-level references for the physics behind insulation performance.

| File | Focus |
|------|-------|
| [01_thermal_principles.md](01_thermal_principles.md) | Heat transfer (conduction/convection/radiation), R-value & U-value, Total R-value (AS/NZS 4859.2), thermal bridging, thermal mass, solar radiation, moisture interaction |
| [02_acoustic_principles.md](02_acoustic_principles.md) | Sound fundamentals, decibels, mass law, mass-spring-mass, absorption vs insulation, Rw/C/Ctr ratings, impact sound, flanking, NCC acoustic requirements |

## Key formulas at a glance

**Thermal:**
- Fourier: `q = -λ·(dT/dx)`
- R-value: `R = d/λ`
- U-value: `U = 1/R_total`
- Heat flow: `Q = U·A·ΔT`
- Radiation: `q = ε·σ·T⁴`

**Acoustic:**
- SPL: `Lp = 20·log₁₀(p/p_ref)`
- Mass law: `R ≈ 20·log₁₀(m·f) − 47`
- Mass-air-mass resonance: `f₀ = 60·√((m₁+m₂)/(m₁·m₂·d))`
- Reverberation: `RT60 = 0.161·V/A`

## Related

- `../compliance/` — NCC/ABCB compliance digests (where these principles are applied)
- `../product_intelligence/` — products and materials (how these principles map to products)
- `../AU_Insulation_Expert_Knowledge_Base.md` — broad industry knowledge base
