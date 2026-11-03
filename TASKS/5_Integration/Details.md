# 5 Integration

This is the task where the various disparate pieces of code get integrated:
* Shop
  * Machines
  * Tool Models
  * Stock Models
* Mounting
* LinuxCNC Control GUI

Here are some semi unordered steps:
* Inject the mount setup as RS-274 `#` comments.
  * Issue: TOML vs JSON?
* The keep out zones need to injected from the various mounting tools (e.g.
  table, vice, jaws, parallels.)
  * The control panel needs a toggle button that shows the keep out zones.
* When the Simulator is run, it builds up the entire mount from the comments
  up to and including the initial stock in translucent mode.  The final part
  is show in solid mode.
* Decide whether to have one file per tool or a single file that can be moved
  around in.  Probably both.
* Provide a mechanism to tell the operator when manual intervention is need.
* Estimate the time to the next tool change.
* For CNC machines with limited tool changer space, come up with a way of
  prompting the machine operator to set up their tool changer carousel.
* With the simulator, show that they can not manually drive into a keep out
  zone.
* Provide a way to set the origin from GUI.
* Provide a way to switch tools from the GUI.
* Provide a way to pop up operator instructions at various steps along the way.
* Do automatic tool selection from the available tools.
* Make multipart manufacturing work.
* Add probe support
* Generate an operator document for a machine run.
* Add way more tools.
