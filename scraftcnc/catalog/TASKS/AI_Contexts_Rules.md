# AI Contexts Rules

`ai_contexts` writes this file into every collection each time it runs,
so it always matches the program.  Never edit it; a change to it is
made in `ai_contexts.py`.

The `ai_contexts` program (often installed as `aic`) creates and manages
items in collections such as `TASKS/` and `ISSUES/`.  `ai_contexts` with
no arguments lists the collections, and `ai_contexts -h` lists all of
the commands.  Every command starts with the collection, which (like the
command) may be any unique prefix in any case.  The `create` command
(e.g. `ai_contexts TASKS create 1.2.3 New Task`, or `ai_contexts t cr
1.2.3 New Task`) creates an item directory (e.g. `TASKS/1.2.3_New_Task/`)
containing:

* `Details.md`:
  Edited by the human to describe the item.  Claude only edits it when
  asked to.
* `Context.md`:
  Edited by Claude to retain useful item context across sessions.
  Claude edits it directly; there is no `ai_contexts` command for it.
* `Summary.md`:
  Written by Claude before the item is closed (see below).
* `.item.json`:
  Managed by `ai_contexts`.  Claude changes the state with the
  `pending`, `open`, `reference`, `suspend`, `close` and `reject`
  commands (e.g. `ai_contexts t close T.fbm`), never by editing this
  file.

Each item has a tag (e.g. `I.dbzib` for "Division by Zero is Bad" in
`ISSUES/`), shown by `ai_contexts t ls`; `ai_contexts I.dbzib show`
shows everything about it.  To refer to an item in Markdown text and
commit messages, use its tag followed by `~` and its current number, in
back quotes (e.g. `I.dbzib~3`), so that its directory
(`ISSUES/3_Division_by_Zero_is_Bad/`) is easy to find.  Never use the
number alone.  Numbers change when items are created, deleted, moved or
transferred, and a `~NUMBER` is never updated: it records the number
when it was written, and the tag is what names the item.  Commands
accept a tag (in any case, but never shortened, and with or without a
`~NUMBER`, which is ignored) wherever they take a number, and a tag can
stand in for its collection (`ai_contexts T.fbm close`).  Renaming an
item can change its tag; `ai_contexts` then lists the `.md` files that
use the old tag and offers to update them, and Claude answers yes (after
checking the list) so that every reference changes in the same pass.

Every `ai_contexts` command checks its collections and prints what it
fixed and what needs fixing.  When it reports a problem, Claude fixes it
(usually with the `rename` command it suggests) or tells the user about
it.

Item numbers never have gaps.  `create` and `move` take a place: the
next free number of a level (e.g. `1.3`), or `before NUMBER` / `after
NUMBER` (e.g. `ai_contexts t move T.fbm after 2.1`, or `ai_contexts t
create before 1.1 Fix Big Mistake`).  `rename NUMBER to TITLE...`
changes a title.  There is no undo: when `ai_contexts` recommends a
version control snapshot before a move, rename or transfer and asks
whether to continue, Claude answers no, takes a snapshot (following the
project's version control rules), and then runs the command again.
`delete` is permanent: it refuses an item with children unless given
`-r` (which asks first), and renumbers the later items.  Never run
`delete` (or other changing commands) on the real items just to see what
happens; try it in a scratch directory.

An item that belongs in another collection of the same type (e.g. a
Task that turns out to be an Issue) is moved there, with its children,
by `ai_contexts t transfer T.fbm issues [PLACE]`.  Its tag gets the new
prefix (`T.fbm` becomes `I.fbm`), and `ai_contexts` offers to update the
`.md` files that use the old tags; as for a rename, Claude answers yes
after checking the list.  The update drops an old tag's `~NUMBER`
(`T.fbm~12` becomes `I.fbm`), since that number was in the other
collection.  Old tags are not looked up afterwards, so text must use the
new ones.

When priority is enabled for a collection (e.g. `ai_contexts i enable
priority`), items may have a priority set with `ai_contexts i priority
NUMBER LEVEL`, and `ls` lists them by priority first:

* **0**: A catastrophic bug that must be avoided at all costs, such as a
  security hole or a defect that escapes to where nobody can fix it.
* **1**: A high priority that needs to be fixed quickly.
* **2**: A medium priority that needs to be fixed next.
* **3**: A low priority that gets put near the end of the list.

`-` removes the priority.

New items start out Pending.  The states (of an "items" collection, like
`TASKS/` and `ISSUES/`) are Pending, Open, Reference, Suspended, Closed
and Rejected.  A Reference item is not being worked on, but its
`Context.md` is still loaded, so its context stays available.  A
Rejected item was decided against (`ai_contexts i reject NUMBER`); it is
treated like a Closed one, and its `Summary.md` says why.

Before closing an item, Claude writes its `Summary.md` (below the
heading line that `ai_contexts` maintains): what was decided and done,
with the tags (and `~NUMBER`s) of related items.  Once the item is
closed, only that summary is loaded at startup (and after the 50 most
recently closed, only its tag and title, in the generated
`TASKS/Closed.md`), so it should be enough to know that the item exists
and what it settled.
`ai_contexts T.fbm show` and the item's files give the rest when needed.

Every time `ai_contexts` is successfully run, it rewrites these files,
which Claude never edits:

* `TASKS/Startup.md`: `@` imports of the `Details.md` of every item that
  is not closed, the `Context.md` of every Open or Reference item and
  the `Summary.md` of the most recently closed items, in every
  collection.
* `TASKS/Closed.md`: the tags and titles of the older closed items.
* `RULES/Active_Rules.md`: `@` imports of the Active rules.
* `AI_Contexts_Rules.md` (this file), in every collection.

`CLAUDE.md` imports only files that are known to exist, such as these:

```
@TASKS/AI_Contexts_Rules.md
@TASKS/Startup.md
@RULES/Active_Rules.md
```

Every run reports an `@` import in `CLAUDE.md` whose file does not
exist; Claude tells the user about it.

`RULES/` is a rules collection (`ai_contexts r type` prints a
collection's type).  Each rule's `Details.md` is a read-only copy of a
source file elsewhere (e.g. `../shared_rules/Version_Control_Rules.md`),
made and refreshed by `ai_contexts`; its states are Active and InActive
(`ai_contexts r activate R.vcr`, `ai_contexts r deactivate R.vcr`).
Claude never edits a rule's copy: a change to a rule is made in its
source (and only when asked), and the next `ai_contexts` run copies it.
New rules come from files with `ai_contexts r create PLACE FILE...`,
or from another project's rules (or a directory of rule files) with
`ai_contexts r copy DIRECTORY [CHOICES...]`, which lists them by number
and title and copies the chosen ones (e.g. `1,3-5`); Claude gives the
CHOICES on the command line, as the user asked.  `ai_contexts r source
R.vcr FILE` changes a rule's source.  All three insist on a file ending
in `.md`, refuse a `CLAUDE.md` file, and ask before using a file that
does not look like a rule (one named in capital letters, like
`README.md`, or one with an `@` import); Claude answers no unless the
user asked for that file.  When `ai_contexts`
reports a copy edited in place, a missing source, an `@` import in a
rule or a rule that `CLAUDE.md` also imports, Claude tells the user
rather than fixing it with `refresh`.
