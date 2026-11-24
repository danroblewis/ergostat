# merge-pipeline-gaps-briefs-read-records: The briefs, the planner and the knowledge block read the entries from dev/records/

depends-on: [merge-pipeline-gaps-md-regenerated-on-land]

Problem: dev/bin/brief.py:42-54, plan.py:133 and :422 and knowledge.py:231 read docs/GAPS.md on main for a gap's entry and its section, and tests/test_item_search_gaps.py pins live GAPS.md text. Change: all three read gapsdoc.entries over main's dev/records/ (added here if neither sibling reader gap has landed); the role prompts under dev/prompts/ and dev/README.md say the entry is in the record; test_item_search_gaps.py moves to a fixture. Done: an implementor's, a reviewer's and a planner's brief carry the same entry text from the records as from the rendered GAPS.md on the pinned fixture; an unreadable record is said in the brief by name, never read as no entry; a test asserts no file under tests/ opens docs/GAPS.md. Files: dev/bin/{brief,plan,knowledge}.py, dev/bin/gapsdoc.py, dev/prompts/, dev/README.md, tests/test_item_search_gaps.py, tests/test_factory.py. Budget: 60 net lines in dev/bin.

Area: merge-pipeline. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.
