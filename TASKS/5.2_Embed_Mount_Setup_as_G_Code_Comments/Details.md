# 5.2 Embed Mount Setup as G-Code Comments

The general concept is to embed information into `.nc` (i.e. RS-274) file as
comments that allow `lcnc_hmi.py` (note the new and improved name) to render a
the entire mount setup including:
* Initial material stock.
* All of the mount tooling needed to hold the material.
* All of the machine tools to be mounted into the CNC mill spindle.
* It is important to capture keep out zones here.
* Probably some other stuff yet to be decided.

Possible encoding methods to be explored are:
* Actual Python module, class, and method.  This might need:
  * Directory path.
  * Python (`.py`) file name to import.
  * Class Name
  * Method Name
* TOML description.
* JSON description. 
* Hybrid?
* Others?

To make this work, it is probably prudent to leverage the `.step` file cache.
If the computed solid is in the cache, just use it and add:
* color
* Transparency
* Position
* Orientation

Other random thoughts.
* It might be nice to have the ability to pop up operator instructions.
  * The operator should be able to single step through the mount process.
* It would be nice if the operator could see what the next tool change is
  and approximately when.


