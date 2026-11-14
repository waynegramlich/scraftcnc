# 5.7 Carousel Planning for a Job

(Draft by Claude, 2026-11-13, from the user's request; the user's to
revise.)

Only CNC machines with an automatic tool changer have a carousel.
Whenever a tool is needed that is not in the carousel, it is loaded
into one of its slots, and the tool it displaces is moved by hand
back to its place in the shop's tool rack.  Someone must decide which
tool takes that trip back to the rack: scraftcam, since it knows the
order of all of the job's `.nc` files.  The goal is the fewest
carousel changes.

* A job is a directory of `.nc` files, run in name order, each file
  driving one tool (`T.npfetc~5.4`).
* With the whole order known, the tool to send back is the one whose
  next use is furthest away (or never comes): Belady's rule, which
  gives the fewest changes for a known order.
* The operator is told, before the job and at each change, which
  tool goes into which slot and which goes back to the rack.
* `scraftcam/carousel.py` already plans one program's slots and swaps;
  this extends it to a whole job.
