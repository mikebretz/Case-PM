# Sylvorin world — fantasy Earth (magic, not technology)

## Vision

A **full-scale Earth** (United States, Europe, all continents) where:

- Geography matches the real world (coasts, mountains, rivers, city *locations*)
- **No modern technology** — **magic** replaced tech
- Cities and towns look **like their real counterparts** in layout, but **fantasy architecture** (spires, enchanted districts, arcane harbors)

## Reality check (important)

A 1:1 Earth in Unreal is **enormous** (~40,000 km). We build it in **phases**:

| Phase | Scope | Approach |
|-------|--------|----------|
| **1 — Now** | Playable zone (~5 km) | Landscape + Third Person + ground/sky script |
| **2** | Region (e.g. one US state) | World Partition + heightmaps from GIS |
| **3** | Continents | Streaming + Cesium for Unreal OR tiled landscapes |
| **4** | Full Earth | Multiple world partitions, LOD, dedicated servers |

Recommended scale for development: **1 real meter = 1 Unreal unit (cm)** in local zones, with **streaming** for distance.

## Phase 1 — Do this in editor today

1. **Tools → Run Python Script** → `Unreal/Scripts/sylvorin_setup_level.py`
   - Adds **ground plane**
   - **Sun** rotates very slowly (always moving)
   - Saves map `Content/Sylvorin/Maps/SylvorinWorld`

2. **Project Settings → Maps & Modes** → set **Game Default Map** = `SylvorinWorld`

3. **Add → Feature Pack → Third Person** (if not already)

4. **Landscape** (bigger ground):
   - **Mode → Landscape**
   - Create **8192×8192** (or start 2017×2017)
   - Sculpt hills — this becomes your first zone (Eldergrove / starting area)

## Phase 2+ — Real-world layout, fantasy buildings

### Terrain (real Earth shape)

- **Cesium for Unreal** — real globe terrain and coordinates (free tier for dev)
- Or **GIS heightmaps** (SRTM) → World Machine / Gaea → Unreal Landscape
- Coastlines from **Natural Earth** vector data

### City placement (real positions, fantasy look)

1. Export city centers / roads from **OpenStreetMap**
2. Import as splines or block layout in Unreal
3. Replace building meshes with **fantasy kits** (medieval, arcane, elven districts)
4. Same street grid as real city, different art style

### Magic instead of tech

- No cars/planes — **levitation**, **portal networks**, **skyships**
- Power = **ley lines**, **crystals**, **enchantments** (Gameplay systems later)
- UI and quests from original Sylvorin design doc (`DESIGN-SPEC.md`)

## Folder plan (as we grow)

```
Content/Sylvorin/
  Maps/           SylvorinWorld, regions (US_East, Europe_West, ...)
  Landscape/      heightmaps, materials
  Cities/         fantasy kits per real city (NYC_fantasy, Paris_fantasy, ...)
  Characters/
  Magic/          spells, VFX
```

## Next build tasks (order)

1. ✅ Mouse + keyboard PC controls
2. ✅ Ground + slow sky (Python setup script)
3. Landscape sculpt — first playable biome
4. One fantasy town prototype (layout from a real small town)
5. Cesium or regional heightmap import
6. World Partition streaming for travel

Ask for each phase in Cursor and we’ll implement the next slice.
