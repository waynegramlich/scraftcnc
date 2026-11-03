# 5.1 Reorganize Directories

Currently there are two related directories that are not under control of
this GIt repository:
* `scraftpybind/`:
  This is currently a symbolic link an it needs to be simply moved to this
  `scraftcnc/pybind/`.  It also needs to be turned into a Python package by
  adding a `__init__.py`.
* `scraftlinuxcnc/:
  This is currently a symbolic link an it needs to be simply moved to this
  `scraftcnc/linuxcnc/`.  It also needs to be turned into a Python package by
  adding a `__init__.py`.
* `?/`:
  HMI stands for Human Machine Interface and is commonly used when describing
  the interface an operator uses when controlling industrial machinery.
  Other possibilities OIT (Operator Interface Terminal) or OIC (Operator
  Interface Console) our just plain UI (User Interface.)
* `tests/`:
  All of the tests generated over time need to be consolidate into a single
  directory.  They currently start with `test_`.
* `tooling/`:
  There will be more and more tooling created, so it probably makes sense to
  collect them together.

