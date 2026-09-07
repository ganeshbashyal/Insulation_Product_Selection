# Acoustic Principles — Deep Dive

*Engineering-level reference for sound, sound transmission, and acoustic insulation as applied to Australian buildings.*

---

## 1. Sound Fundamentals

### 1.1 What sound is
Sound is a **longitudinal pressure wave** propagating through a medium (air, water, structure). It has:
- **Frequency (f):** cycles per second (Hz). Pitch.
- **Wavelength (λ):** λ = c / f, where c = speed of sound (~343 m/s in air at 20°C).
- **Amplitude:** pressure magnitude. Loudness.

**Human hearing:** 20 Hz – 20,000 Hz.
- Bass/low frequency: 20–250 Hz (hardest to insulate)
- Speech: 250–4,000 Hz
- High frequency: 4,000–20,000 Hz

### 1.2 Speed of sound
- Air (20°C): 343 m/s
- Water: ~1,480 m/s
- Steel: ~5,100 m/s
- Concrete: ~3,000–3,700 m/s

### 1.3 Wavelength examples (air)
| Frequency | Wavelength |
|-----------|-----------|
| 63 Hz (bass) | 5.4 m |
| 250 Hz | 1.4 m |
| 1,000 Hz | 0.34 m |
| 4,000 Hz | 0.086 m |

**Why it matters:** low-frequency sound has long wavelengths that diffract (bend) around obstacles and require mass to block; high-frequency sound is easily blocked by thin barriers but leaks through tiny gaps.

---

## 2. Decibels & Sound Levels

### 2.1 Sound pressure level (SPL)
```
Lp = 20 · log₁₀(p / p_ref)   dB
```
- `p` = sound pressure (Pa)
- `p_ref` = 20 µPa (threshold of hearing)

### 2.2 Sound power vs sound pressure
- **Sound power (Lw):** total acoustic energy emitted by a source (independent of distance).
- **Sound pressure (Lp):** what you measure at a point (depends on distance, room).
- Insulation ratings deal with **level difference** — how much the building element reduces transmission.

### 2.3 Decibel arithmetic
- Decibels are logarithmic. **10 dB increase ≈ perceived "twice as loud."**
- **3 dB change = just noticeable difference (JND).**
- Adding two equal sources: +3 dB.
- Doubling distance from a point source: −6 dB.

### 2.4 Frequency weighting
- **A-weighting (dBA):** approximates human hearing sensitivity (attenuates low frequencies).
- **C-weighting (dBC):** flatter, captures low-frequency/bass content.
- Insulation ratings use unweighted third-octave data, then apply spectrum adaptation terms.

---

## 3. Sound Transmission & Insulation

### 3.1 Transmission loss (TL) & sound reduction index (R)
```
R = 10 · log₁₀(1/τ)   dB
```
- `τ` = transmission coefficient (fraction of sound energy transmitted).
- **R (or TL)** = how much airborne sound a building element blocks.
- Higher R = better insulation.

### 3.2 The Mass Law
For a single homogeneous panel, sound insulation increases with mass and frequency:
```
R ≈ 20 · log₁₀(m · f) − 47   dB   (theoretical)
```
- `m` = surface mass (kg/m²)
- `f` = frequency (Hz)

**Practical mass law:** ~5–6 dB increase per **doubling of mass** (or per octave of frequency).

**Implication:** to significantly improve a single-leaf wall, you must add a LOT of mass (double it for ~5 dB). This is why lightweight construction uses **double-leaf** (mass-spring-mass) instead.

### 3.3 Coincidence effect (critical frequency)
At a certain frequency (the **coincidence/critical frequency**), the panel's bending wavelength matches the airborne wavelength, causing a **dip in insulation** (resonant transmission).
- Thin, stiff panels (glass, thin steel) have high coincidence dips in the speech range.
- Thicker, more flexible panels push coincidence lower (less problematic).

### 3.4 Resonance
Panels have natural resonance frequencies. Below the lowest resonance, stiffness controls; above, mass controls. The mass law applies in the mass-controlled region.

---

## 4. Single-Leaf vs Double-Leaf (Mass-Spring-Mass)

### 4.1 Single leaf
- One layer of material (e.g., single brick wall).
- Performance governed by mass law (limited by mass).
- To get Rw 50 with a single leaf requires very heavy construction (e.g., 230mm brick).

### 4.2 Double leaf (mass-spring-mass)
Two leaves separated by a cavity (air + insulation). The cavity acts as a **spring**, the two leaves as **masses** — a resonant system.

**Mass-air-mass resonance frequency:**
```
f₀ = 60 · √( (m₁ + m₂) / (m₁ · m₂ · d) )   Hz
```
- `m₁, m₂` = surface mass of each leaf (kg/m²)
- `d` = cavity depth (m)

**Below f₀:** the two leaves move together (like a single leaf) — poor insulation.
**Above f₀:** insulation improves steeply (~12 dB/octave) — much better than single leaf.

**Design goal:** push f₀ below the frequency range of interest (below ~100 Hz) by:
- Increasing leaf mass
- Increasing cavity depth
- Adding absorption (insulation) in the cavity

### 4.3 Cavity absorption
Filling the cavity with porous insulation (glasswool/rockwool/polyester) **damps the cavity resonance** and improves mid/high-frequency insulation by **5–10 dB**.
- It also prevents the cavity from acting as a resonant chamber.
- This is why acoustic insulation in party walls is essential.

---

## 5. Sound Absorption vs Sound Insulation

These are **different** and often confused:

| Property | Meaning | Metric |
|----------|---------|--------|
| **Sound absorption** | How much sound energy a material absorbs (doesn't reflect) within a room | α (absorption coefficient), NRC |
| **Sound insulation** | How much sound a building element blocks from passing through | R, Rw, DnT,w |

- **Absorption** controls reverberation and echo *within* a room.
- **Insulation** controls transmission *between* rooms.
- A material can be a great absorber (soft, porous) but a poor insulator (light, porous), and vice versa.

### 5.1 Absorption coefficient (α)
- α = fraction of incident sound absorbed (0 = all reflected, 1 = all absorbed).
- **NRC** (Noise Reduction Coefficient) = average α at 250, 500, 1000, 2000 Hz.
- Porous absorbers (insulation batts, acoustic panels) have high α at mid/high frequencies.

### 5.2 Reverberation time (Sabine)
```
RT60 = 0.161 · V / A   seconds
```
- `V` = room volume (m³)
- `A` = total absorption (m² sabins) = Σ(αᵢ · Sᵢ)
- Lower RT60 = "deader" room (less echo).

---

## 6. Rating Systems (Rw, C, Ctr, DnT,w, Ln,w)

### 6.1 Weighted sound reduction index (Rw)
- Single-number rating derived from the full frequency spectrum (100–3150 Hz).
- Determined per **AS/NZS ISO 717.1** by comparing the measured curve to a reference curve.
- Rw is a **laboratory** value (ideal conditions, no flanking).

### 6.2 Spectrum adaptation terms (C, Ctr)
- **C:** adjusts for pink noise (mid/high frequency emphasis).
- **Ctr:** adjusts for low-frequency (traffic/bass) spectrum. Always negative.
- **Rw + Ctr** is always lower than Rw (typically 3–10 dB lower) — reflects poor low-frequency performance.

**Why Ctr matters:** modern home theatre/music systems produce strong bass. The NCC uses **Rw + Ctr** for walls/floors separating dwellings because bass is the hardest to control and the most intrusive.

### 6.3 Field vs laboratory
| Metric | Context | Notes |
|--------|---------|-------|
| Rw, Rw+Ctr | Laboratory | Ideal, no flanking |
| DnT,w, DnT,w+Ctr | Field (on-site) | Includes flanking — always lower than lab |
| Ln,w | Laboratory impact | — |
| LnT,w | Field impact | — |

**Field values are typically 5–10 dB lower** than lab values due to flanking transmission in real buildings. The NCC recognises this: field verification allows DnT,w + Ctr ≥ 45 (vs lab Rw + Ctr ≥ 50).

### 6.4 STC (Sound Transmission Class)
- US single-number rating, similar to Rw but different reference curve.
- Not used in the NCC, but appears on imported products (esp. ROCKWOOL US data).
- Roughly comparable: STC ≈ Rw (within a few dB), but not interchangeable.

---

## 7. Impact Sound

### 7.1 What it is
Sound generated by **physical impact** on a surface (footsteps, dropped objects, furniture moving) — transmitted through the structure.

### 7.2 Measurement
- **Ln,w / LnT,w** = weighted normalised/standardised impact sound pressure level.
- Measured with a **standard tapping machine** (5 hammers striking the floor).
- **Lower Ln,w = better** impact insulation (opposite direction to Rw).

### 7.3 Control methods
- **Resilient layers** (underlay, floating floors) — decouple the impact from the structure.
- **Floating floors** — mass on a resilient layer.
- **Discontinuous ceilings** — ceiling isolated from floor above.
- **Carpet + underlay** — classic impact absorber (but can be substituted with hard flooring, failing compliance).

---

## 8. Flanking Transmission

**Flanking** = sound travelling around a separating element via adjacent structure (walls, floors, ceilings, ducts).

### 8.1 Flanking paths
- Continuous structure (slab extending past the wall)
- Junctions (wall-ceiling, wall-floor)
- Services (ducts, pipes, conduits)
- Gaps and penetrations

### 8.2 Why it matters
- Flanking often **limits real-world performance** more than the separating element itself.
- A lab-tested Rw 50 wall can achieve only DnT,w 40–45 in the field due to flanking.
- This is why the NCC field verification threshold is lower than the lab requirement.

### 8.3 Mitigation
- Break continuous elements (discontinuous construction, expansion joints).
- Seal all penetrations.
- Offset electrical outlets (not back-to-back).
- Acoustic treatment around ducts penetrating rated walls.

---

## 9. Improving Sound Insulation — Practical Hierarchy

| Rank | Technique | Typical gain |
|------|-----------|--------------|
| 1 | **Seal all gaps** | +5–10 dB (most cost-effective) |
| 2 | **Add mass** (extra plasterboard layer) | +5–6 dB per doubling |
| 3 | **Cavity absorption** (insulation batts) | +5–10 dB |
| 4 | **Decouple** (resilient channels, staggered/double studs) | +5–15 dB |
| 5 | **Increase cavity depth** | Improves low-frequency |
| 6 | **Eliminate flanking** | +5–10 dB (field) |

### 9.1 The gap problem
- A **1% gap area** can reduce Rw by **5–10 dB** — sound finds the path of least resistance.
- Sealing is almost always the highest-value acoustic intervention.

### 9.2 Density vs thickness (for cavity absorption)
- **Density** (30–80 kg/m³) matters more than thickness for mid-frequency absorption.
- Standard thermal glasswool (10–14 kg/m³) provides some benefit; acoustic batts (30–40 kg/m³) provide more.
- For low-frequency absorption, need thickness AND density (or specialised absorbers).

---

## 10. Australian NCC Acoustic Requirements (summary)

### 10.1 Class 1 (separating walls between dwellings)
- **Type A** (bathroom/kitchen/laundry vs habitable room): Rw + Ctr ≥ 50 + impact (discontinuous construction)
- **Type B** (all other): Rw ≥ 45

### 10.2 Class 2 & 3 (apartments/hotels)
- Wall between SOUs: **Rw + Ctr ≥ 50**
- Wall SOU vs plant/corridor/lift: **Rw ≥ 50**
- Floor between SOUs: **Rw + Ctr ≥ 50** (airborne) + **Ln,w ≤ 62** (impact)
- Door in wall SOU vs corridor: **Rw ≥ 30**

### 10.3 Class 9c (aged care)
- Floor between SOUs: Rw ≥ 45
- Wall separating SOUs: Rw ≥ 45

### 10.4 Discontinuous construction
- ≥ 20mm cavity between two separate leaves
- Masonry: resilient (acoustic) wall ties
- Non-masonry: no mechanical linkage except periphery
- Staggered studs with common plates = NOT discontinuous

---

## 11. Typical Wall Assembly Performance (illustrative)

| Assembly | Approx Rw |
|----------|-----------|
| Single 10mm plasterboard each side, 90mm stud, no insulation | ~30–33 |
| + glasswool cavity batts | ~35–38 |
| + double plasterboard one side | ~40–43 |
| Staggered studs + insulation | ~45–48 |
| Double studs (discontinuous) + insulation | ~50–55 |
| Double studs + double plasterboard + insulation | ~55–60 |

*(Actual values depend on exact construction; always use tested systems per NCC Specification 28.)*

---

## 12. Summary — Acoustic Design Principles

1. **Mass blocks airborne sound** (mass law) — but doubling mass only gives ~5 dB.
2. **Double-leaf (mass-spring-mass) beats single leaf** — decouple and add cavity depth.
3. **Cavity absorption is essential** — damp resonance, +5–10 dB.
4. **Seal everything** — gaps destroy performance.
5. **Decouple** — break vibration paths (discontinuous construction, resilient mounts).
6. **Control flanking** — it limits real-world performance.
7. **Impact sound needs resilient layers**, not just mass.
8. **Low frequency (bass) is the hardest** — hence Rw+Ctr (not Rw) in the NCC.
9. **Absorption ≠ insulation** — different jobs, different metrics.
10. **Use tested systems** — lab ratings don't transfer without correct installation.
