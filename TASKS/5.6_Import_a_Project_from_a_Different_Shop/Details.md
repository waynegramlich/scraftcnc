# 5.6 Import a Project from a Different Shop

(Draft by Claude, 2026-11-04, from `T.emsagc~5.2` #63; the user's to
revise.)

The user's long-term goal: someone has a design that works in their
shop, and sends the design and their shop description to another
shop.  A reconciliation then changes the tooling and process so the
design can be made in the second shop.

* Shops are independent: neither knows about the other, and nothing
  is fed across (#62).  Different tools change everything.
* Development works in the "Developers Shop" (today's example shop,
  `examples/shop/`) (#64).
* Today the program picks one shop at its start and fills the name
  dictionaries from it (`use_shop()`).
