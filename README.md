# Super Duper Batch Exporter
### Forked and uploaded to Extension Platform: https://extensions.blender.org/add-ons/superduperbatchexporter/

## Description
One click export to multiple files. Options are set once and stored with blend file for consistent export to game engines or other 3D software. With options to limit export, e.g. **Render Enabled**, you'll never have repeat the same selection each time you export.

### Export Options
Use existing export presets, set options like **Output Directory**, **Prefix**, **Suffix**, filter by **Type** or set object **Location**, **Rotation** or **Scale** on export. 

**Mode** exports a file for each:
- **Object**
- **Parent Object**
- **Collection**
- **Object with Collections as Sub-directories**    (NEW)
- **Parent Object with Collections as Sub-directories**   (NEW)
- **Scene**  (NEW)

**Limit to** specifies which objects to export:
- **Selected**
- **Visible**
- **Render Enabled and Visible**  (NEW)

### Other Features
- Supports: **DAE, ABC, USD, SVG, PDF, OBJ, PLY, STL, FBX, glTF**.
- **FBX only feature**: Automatic LOD creation on export using decimate modifier. Game engines like Unreal and Unity will automatically setup LOD on import.
- Choose between these UI Locations: **Top Bar**, **N-panel**, **3D Viewport Header**


The Add-on is a fork of MrTriPie's Super Batch Export which can be found on github.

<img src="https://user-images.githubusercontent.com/65431647/147272597-7ed290c6-51b4-4afa-a8ee-ee4661330825.png" height="400"/> <img src="https://user-images.githubusercontent.com/65431647/147272883-0c8c10d7-062f-4737-8522-55a3c51c5c50.png" height="400"/>
