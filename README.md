# SolidCraftCNC

The purpose of the is project is to support 3-axis mill CNC code generation.
The intent is to do this using the SolidCraft Python bindings.

The following steps are suggested:
1. Create SCCNC class in `solidcraftcnc.py`.
2. Create SCRoundPoly class that supports polygons in the XY plane with
   each corner having a radius of curvature.
3. Look at:
   * [PythonicGCodeMachine](
     https://fabricesalvaire.github.io/pythonic-gcode-machine/gcode-reference/rs-274/index.html) (appears to be abandoned).
   * [RS274](rs274/README.md):
     Another abandoned RS274 project. (I authored this one.)

   In reality, an RS274 command trivially represented a a simple Python
   dictionary.

4. Add one level of nesting of SCRoundPoly's  to provide one or more
   internal pockets.

5. Generalize to support further nesting, to provide alternating islands and
   island pockets.

6. Come up with a way to visualize the generated RS-274 path.
