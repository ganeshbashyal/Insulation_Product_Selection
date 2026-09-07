# Thermal Principles — Deep Dive

*Engineering-level reference for heat transfer and thermal performance as applied to Australian building insulation.*

---

## 1. The Three Heat Transfer Mechanisms

Heat always flows from hot to cold. It does so by three mechanisms, and insulation must address all three.

### 1.1 Conduction
Heat transfer through a solid (or stationary fluid) by molecular vibration/collision.

**Fourier's Law:**
```
q = -λ · (dT/dx)
```
- `q` = heat flux (W/m²)
- `λ` (lambda) = thermal conductivity (W/m·K)
- `dT/dx` = temperature gradient (K/m)

**Thermal conductivity (λ)** is a material property — how readily a material conducts heat. Lower λ = better insulator.
- Still air: 0.025 W/m·K (the benchmark — insulation traps still air)
- Glasswool: 0.032–0.044 W/m·K
- Rockwool: 0.033–0.040 W/m·K
- PIR foam: 0.022–0.026 W/m·K
- Phenolic: 0.021 W/m·K (lowest common)
- Timber: 0.13–0.17 W/m·K
- Steel: 50 W/m·K (≈2000× worse than insulation — why thermal bridging matters)
- Concrete: 1.0–1.6 W/m·K
- Water: 0.6 W/m·K (≈25× worse than air — why wet insulation fails)

### 1.2 Convection
Heat transfer by bulk fluid movement (air or liquid).

**Newton's Law of Cooling:**
```
q = h · (T_surface − T_fluid)
```
- `h` = convective heat transfer coefficient (W/m²·K)
- Natural convection (still air film): h ≈ 2–10 W/m²·K
- Forced convection (wind): h ≈ 10–100 W/m²·K

**Why it matters:** Bulk insulation traps air in tiny pockets too small for convection cells to form, so heat transfer through it is dominated by conduction through the still air. If air can move (gaps, draughts, convective loops in cavities), insulation effectiveness collapses.

### 1.3 Radiation
Heat transfer by electromagnetic waves (infrared). All bodies above absolute zero emit radiation.

**Stefan-Boltzmann Law:**
```
q = ε · σ · T⁴
```
- `ε` = emissivity (0–1; polished foil ≈ 0.03–0.05, black body = 1.0)
- `σ` = 5.67 × 10⁻⁸ W/m²·K⁴
- `T` = absolute temperature (K)

**Radiant heat transfer between two surfaces:**
```
q = σ · (T₁⁴ − T₂⁴) / (1/ε₁ + 1/ε₂ − 1)
```

**Why it matters:** Reflective insulation (foil) works by having **low emissivity** — it reflects radiant heat rather than absorbing/re-emitting it. This is fundamentally different from bulk insulation (which resists conduction). Reflective insulation only works across an **airspace** — foil pressed against a solid surface conducts heat through it and loses its reflective benefit.

---

## 2. Thermal Resistance (R-Value) & Transmittance (U-Value)

### 2.1 Definitions
- **R-Value** = thermal resistance = `R = d / λ` (m²·K/W), where `d` = thickness (m).
- **Thermal resistivity** `r = 1/λ` (m·K/W).
- **U-Value** = thermal transmittance = `U = 1/R_total` (W/m²·K).

**Higher R = better insulation. Lower U = better insulation.**

### 2.2 Series vs parallel heat flow

**Series (layers stacked, heat flows through each in turn):**
```
R_total = R₁ + R₂ + R₃ + ... + R_n
```
This is how a wall's layers add up: external air film + cladding + airspace + insulation + plasterboard + internal air film.

**Parallel (heat flows through multiple paths side by side, e.g., insulation + studs):**
```
1/R_total = f₁/R₁ + f₂/R₂ + ...   (weighted by area fractions f)
```
This is the thermal bridging problem — the studs and the insulation are in parallel, so the stud (low R) "short-circuits" the insulation.

### 2.3 Surface air film resistances (Rsi, Rse)

Still air at a surface provides a thin insulating film:
- **Internal surface (Rsi):** ~0.12 m²·K/W (still air)
- **External surface (Rse):** ~0.04 m²·K/W (wind-exposed)
- These are included in Total R-Value calculations.

### 2.4 Airspace resistances

An enclosed airspace resists heat flow. Its R-value depends on:
- Thickness (up to ~25mm, then plateaus)
- Emissivity of surfaces (foil lining dramatically increases airspace R)
- Heat flow direction (up/down/horizontal)
- Typical: unventilated 20mm airspace ≈ R0.16–0.18; foil-lined ≈ R0.30–0.60+

**Key point:** reflective insulation's R-value comes from the airspace, not the foil itself. The foil just lowers the airspace's effective emissivity.

---

## 3. Total R-Value Calculation (AS/NZS 4859.2)

The NCC requires Total R-Value (not just product R-Value) for compliance. AS/NZS 4859.2 prescribes the method.

### 3.1 The problem
A wall with R2.5 batts between timber studs does NOT achieve R2.5. The studs conduct heat, reducing the effective resistance.

### 3.2 Upper limit (Ru) — parallel path
Assume heat flows in parallel through each path independently:
```
1/Ru = f_insulation/R_insulation + f_stud/R_stud
```
where `f` = area fraction of each path.

### 3.3 Lower limit (Rl) — series path
Assume heat flows in series through the layers (a more pessimistic view of bridging).

### 3.4 Design value
```
R_design = (Ru + Rl) / 2   (arithmetic mean)
```
(Some references use the geometric mean √(Ru·Rl); the exact formula varies by standard edition — always check the current AS/NZS 4859.2.)

### 3.5 Worked example (illustrative)
90mm timber stud wall, 600mm centres, R2.5 batts:
- Stud area fraction ≈ 10% (45mm stud / 600mm spacing)
- Insulation path: R2.5 + air films + linings
- Stud path: timber R (90mm × 0.13 W/mK ≈ R0.7) + linings
- Result: effective R ≈ R1.8–R2.0 (vs R2.5 product) — a 20–28% loss

**Steel framing is far worse** (steel λ = 50 W/m·K): a 90mm steel stud wall with R2.5 batts may achieve only R1.5–R1.8 Total R-Value.

---

## 4. Thermal Bridging

A **thermal bridge** is a path of lower thermal resistance through the envelope — typically framing, fixings, penetrations, or junctions.

### 4.1 Types
| Type | Description | Example |
|------|-------------|---------|
| **Repeating** | Regular, accounted for in R-value calc | Timber/steel studs |
| **Point** | Localised | Fixings, brackets, screws |
| **Linear** | Along a line | Wall-floor junction, window reveals, slab edge |

### 4.2 Impact
- Steel studs can reduce wall R-value by **40–60%**.
- Timber studs reduce by **15–30%**.
- Slab edges, window frames, and corners are concentrated bridges.

### 4.3 Mitigation
- **Thermal breaks** — low-conductivity material interrupting the bridge (e.g., insulated sheathing over studs, thermal break strips in steel framing).
- **Continuous insulation** — rigid board over the outside of the frame (Kingspan K12, XPS) eliminates stud bridging.
- **NCC 2022+** explicitly requires thermal breaks for steel-framed construction.

---

## 5. Thermal Mass & Heat Capacity

**Thermal mass ≠ insulation.** They do different jobs.

### 5.1 Definitions
- **Specific heat capacity (c):** energy to raise 1 kg by 1 K (J/kg·K). Water 4186, concrete ~880, timber ~1200–1600.
- **Volumetric heat capacity (ρ·c):** energy per unit volume (J/m³·K).
- **Thermal diffusivity (α):** how fast heat spreads = `λ / (ρ·c)` (m²/s).

### 5.2 High vs low thermal mass
| Material | Volumetric heat capacity | Diffusivity |
|----------|-------------------------|-------------|
| Concrete/brick | High (~2000 kJ/m³·K) | Moderate |
| Water | Very high (4186) | Low |
| Timber | Low (~600) | Low |
| Insulation | Very low | Very low |

### 5.3 How thermal mass works
- High-mass materials **absorb, store, and release** heat slowly.
- They **dampen temperature swings** (time lag + decrement factor).
- Best in climates with **high diurnal range** (zones 3, 4, 7, 8) — store daytime heat, release at night.
- Less useful in hot-humid climates (zone 1) where nights don't cool.

### 5.4 Time lag & decrement factor
- **Time lag:** delay between peak external temperature and peak internal response.
- **Decrement factor:** ratio of internal to external temperature swing amplitude.
- High mass + insulation = long time lag + low decrement = stable interior.

---

## 6. Dynamic (Transient) Thermal Behaviour

Steady-state R-value is a simplification. Real buildings experience **transient** conditions.

### 6.1 Steady state vs transient
- **Steady state:** constant temperatures, heat flow = U·A·ΔT. Used for simple sizing.
- **Transient:** temperatures vary over time (diurnal, seasonal). Governed by thermal diffusivity and heat capacity.

### 6.2 Why it matters for insulation
- **Lightweight construction** (timber frame + insulation) responds quickly — heats up/cools down fast.
- **High-mass construction** responds slowly — thermal lag smooths extremes.
- In hot climates, insulation on the **outside** of mass keeps heat out before it reaches the mass; insulation on the **inside** lets the mass absorb heat (good for winter, bad for summer cooling).

---

## 7. Solar Radiation & the Building Envelope

### 7.1 Key surface properties
- **Solar absorptance (SA or α):** fraction of solar radiation absorbed. Light roof ≈ 0.23, dark roof ≈ 0.85–0.96.
- **Emissivity (ε):** ability to emit thermal radiation. Foil ≈ 0.03–0.05, most materials ≈ 0.85–0.95.
- **Reflectivity (ρ):** 1 − α (for opaque surfaces).

### 7.2 Roof colour & insulation (NCC)
- NCC zones 1–5 limit roof SA to ≤ 0.64 (to limit solar heat gain).
- Light roofs (SA ≤ 0.23) allow lower ceiling R-values.
- Dark roofs (SA > 0.64) require higher ceiling R-values.
- A dark roof can be 20–30°C hotter than a light roof in summer sun.

### 7.3 Reflective insulation physics
- Radiant heat gain through a roof is dominated by radiation (hot roof radiates down to ceiling).
- Foil under the roof (low ε) reflects this radiant heat back — effective only across an airspace.
- In hot climates (zones 1–3), reflective insulation can be more effective than bulk insulation for radiant heat rejection.

---

## 8. Moisture & Thermal Interaction

### 8.1 Wet insulation fails
- Water λ = 0.6 W/m·K vs air 0.025 — wet insulation can lose 50–90% of its R-value.
- Moisture also promotes mould, corrosion, and material degradation.

### 8.2 Condensation & dew point
- Warm air holds more moisture. When air cools to its **dew point**, water vapour condenses.
- Insulation must keep surface temperatures **above dew point** to prevent surface condensation.
- **Interstitial condensation** occurs within the fabric when vapour diffuses to a cold layer.

### 8.3 Hygrothermal behaviour
- Combined heat + moisture analysis (WUFI, AIRAH DA07).
- Vapour permeance determines whether moisture can dry out.
- Open-cell insulation (glasswool, rockwool, polyester) = high permeance (dries).
- Closed-cell (PIR, XPS, foil-faced) = low permeance (can trap moisture).

---

## 9. Temperature Dependence & Ageing

### 9.1 Temperature dependence
- R-value is tested at a mean temperature (typically 23°C per AS/NZS 4859.1).
- Some materials' λ increases with temperature (foams), others less so.
- Reflective insulation R-value is highly temperature-dependent (radiation ∝ T⁴).

### 9.2 Thermal drift (foam ageing)
- PIR/phenolic foam R-values **decline over time** as the blowing agent (low-λ gas) diffuses out and air diffuses in.
- Foil facings slow this diffusion.
- Declared R-values account for aged performance (not just initial).

---

## 10. Practical Heat Loss/Gain Calculations

### 10.1 Steady-state heat flow
```
Q = U · A · ΔT   (Watts)
```
- `Q` = heat flow (W)
- `U` = 1/R_total (W/m²·K)
- `A` = area (m²)
- `ΔT` = temperature difference (K)

### 10.2 Example — ceiling heat loss
- Ceiling R4.0 (U = 0.25 W/m²·K), 200 m², ΔT = 15 K (winter, 20°C inside / 5°C outside)
- Q = 0.25 × 200 × 15 = **750 W** continuous heat loss through the ceiling alone.

### 10.3 Insulation payback logic
- Halving U (doubling R) halves heat loss through that element.
- Diminishing returns: going R2.0 → R4.0 saves ~50% more; R4.0 → R8.0 saves only ~25% more (on that element).

---

## 11. Summary — Thermal Design Principles

1. **Insulate the largest, hottest/coldest surfaces first** (ceiling, then walls, then floor).
2. **Address all three heat transfer modes** — bulk (conduction) + air sealing (convection) + reflective (radiation).
3. **Account for thermal bridging** — use Total R-Value, not product R-Value.
4. **Match insulation to climate** — reflective in hot zones, bulk in cool zones.
5. **Keep insulation dry** — wet insulation doesn't insulate.
6. **Use thermal mass intelligently** — with insulation, and matched to diurnal range.
7. **Consider dynamic behaviour** — not just steady-state R.
8. **Watch roof colour** — solar absorptance interacts with insulation requirements.
