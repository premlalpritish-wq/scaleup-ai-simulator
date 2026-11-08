# ScaleUp AI Agent Execution Guidelines

## 1. Zero-Hesitation Bioprocess Simulation (`/scaleup`)

When the user prompts `/scaleup <prompt>` or asks to simulate any bioprocess (e.g. *E. coli*, *Saccharina latissima*, fed-batch kinetics, extraction):
1. **Never perform preparatory read or list calls**: Do not call `dir`, `read_file`, or search files prior to executing the tool.
2. **Execute tool call 1 immediately**:
   ```powershell
   python composition/tools/research_to_godot.py --prompt "<prompt>" --launch-godot
   ```
3. **Execution Characteristics**:
   - Cached runs resolve, verify, and launch Godot in **< 1 second** (`~0.76s`).
   - Uncached runs perform autonomous research, trajectory solving, and launch Godot in **< 15 seconds**.
4. **Respond immediately** with the run ID, evidence tier, and link to the live simulation scene.
