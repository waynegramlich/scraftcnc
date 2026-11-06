# 5.1.5 HMI Sub-package

The HMI (Human Machine Interface) package needs to be reorganized:
* There is a separate process that sits between HMI user interface and
  the calls to the Python interface of LinuxCNC.  This process probably
  no longer needs to exist.
* The HMI needs to support managing the tool offset table needed by LinuxCNC.
* The HMI needs to be able manually move the current tool around without
  running the tool tip into a keep out zone.
* The HMI needs to be able to set the origin.
* The HMI needs to be able to toggle:
  * Flute/drill lines on tools.
  * Translucent "fake" tool holders.
  * Stock outline.
  * origin visibility.
  * Deep out zone visibility.
* The HMI needs to be able to show mount setup instructions.
* The HMI needs to be able to deal with tool changer setup, since most
  shops have more tools then they have openings in the tool changer carousel.
* The HMI needs to show the next tool to be installed:
* The HMI needs to show the estimated time left until the next tool change.
* Some setup tools need to be created:
  * Edge finder  (page 415 of SHARS catalog)
  * Center finder
  * Z-Axis Tool Setter (Page 414 of SHARS catalog.)
