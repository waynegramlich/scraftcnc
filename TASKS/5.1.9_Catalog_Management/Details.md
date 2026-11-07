# 5.1.9 Catalog Management

The vast majority of shop tools are purchased via mail order.  Usually tool
vendor has a web site and frequently some sort on-line tool catalog.  Some
vendors go through the trouble of producing a catalog that is .pdf format.
In general, when a tool is added to the shop inventory it is nice to collect
the information about the tool like:
* Tool Name
* Tool Type
* Manufacturer Name
* Manufacturer Part Number
* Vendor Name
* Vendor Part Number
* Purchase Price
* Purchase Date
* Some sort of image of the tool
* etc.

Some (but not all) of this information is kept in the shop TOML file.

The goal is to have a tools directory, where each tool has a separate
sub-directory that contains the relevant documentation.

A previously generated tool called `catxtract` provides a way to extract
tables from a catalog page.  The goal is to make integrate all of this
technology to the current GUI.
