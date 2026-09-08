# Connected workspace update

Scope: the user's ten-area connected-workspace request, replacing the earlier backlog.

- Scene navigation derives from the route; All Scenes is compact and expandable. Large take lists use selectors, and timeline lists are bounded. Assigned is in the path row. Scene/shot rename menus are on overview rows; stable route IDs remain unchanged.
- Placement owns shot membership, never an old comparison. Dashboard exposes pending placement counts across accessible projects. Queue/Home shot links carry the newest clip ID. Commit invalidates project/dashboard caches.
- Reviewing selection is shared by cockpit, sidebar, issue tabs and performance workspace. Reference excludes Reviewing. Comparison never labels an unjudged new take with an invented zero score.
- Shot Selects render live markers and bounded playback. Split creates editable portions; Trim for Film loads a source portion without modifying the shot select. Reviewed clean ranges have separate green markers, candidate usable spans are neutral, selected spans blue.
- Footage assignment drafts are per clip and preserve explicit zero/unassigned values. Header and table use the same draft; canonical labels come from the plan. Recording preview is contained and responsive.
- Search remains contextual, not a duplicate main-nav item. Per-project navigation remembers the last review context. Film copy and overview copy are reduced.
- Dashboard independent reads run concurrently. Observed production project API first response: 6.28s; repeat: 0.75s; web: 0.53s. Config confirms database idle scaling and zero-minimum API/web instances. Disable database idle scaling and keep one API/web instance warm; worker scaling remains unchanged. This raises baseline hosting cost. No claim that the timing alone isolates each cold-start component, or that 100-take load performance has been benchmarked.

Validation before deployment: 491 API tests passed, 18 skipped; 28 web tests passed; TypeScript, Python lint/format, Terraform formatting passed. New regression covers current takes being included despite an old comparison, and removed takes staying excluded. Local browser verified compact All Scenes and synchronized reviewing/reference metadata and issue-tab switching. No live editorial records were modified for testing.

Production deployment and post-deployment verification pending.
