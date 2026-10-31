# LLM Agent Context Log

## 2026-10-30: Created from `T.s2~3`

* Seen once, 2026-10-28, in the user's panel run with the new speeds
  and feeds (`T.msaf~2.1`): the run "was very good", but near the end
  the roughing mill's (T8) path became visible again.  Only the path
  of the tool in the spindle should show (`sim_solidcraft.py`'s
  `PathRack`).  Not looked into, and not reproduced.
* The user: leave it open; eventually reproduce it, or close it for
  lack of a test case.
* SolidCraft is not on Claude's `PATH`: start
  `../solidcraft/solidcraft-linux-x86_64.AppImage --control 8080`.
  `T.s2~3`'s `Context.md` has the commands to bring it all up.
