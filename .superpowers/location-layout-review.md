# Location layout final scoped review

Reviewed the current `location_child_contents_frontend()` builder function, the scoped `ChildContents.vue` changes, the implementation report, upstream location page and native selectable/bulk refresh flow. Existing unrelated changes were excluded. Review was by source inspection only; no tests, builds, browser checks, dependency changes, services, or operational data mutations were performed.

## Strengths and requirement coverage

- The shared `/location/[id]` page mounts the existing grouped thumbnail component for the current location with `direct-only`, covering root bins, nested bins, and leaves. Existing group membership, photos, chevrons, record links, identities, quantities, pagination loops, hydration, retry, and filtering remain in the shared implementation.
- Direct-only mode skips child detail retrieval and recursive rendering. The separately mounted child component preserves child previews without rendering them twice.
- Native selection and bulk actions remain in the collapsed **Manage items** disclosure. The native successful bulk Change location callback emits refresh through `resetSelection()`; the page increments `contentsRevision` and refreshes the native item list.
- The final builder keys both direct and child contents by location and revision, so moves into a child invalidate its cached preview too. The reactive location async-data key handles route changes, and component keys recreate local caches for the new location.
- The direct list has the correct heading and filter wording. Vue `useId()` gives the two independent filters distinct label targets; the installed Nuxt generated imports explicitly include `useId`. The installed async-data signature accepts the getter key used here.
- All builder replacement anchors match the inspected upstream page, and each replacement checks for exactly one match. No obvious syntax or new type integration blocker was found by inspection.

## Findings

No unresolved critical or important source findings.

One important issue was found during review and fixed in the final builder: the child preview originally used only `location.id` as its key, so moving a direct item into a visible child would leave the child's cached item list stale. `deploy/build-homebox-ui.py:432` now uses `children-${location.id}-${contentsRevision}`, sharing the revision invalidation of direct contents.

The final inspection also confirmed `work/homebox-ui-dev/pages/location/[id]/index/index.vue:351` contains the corrected child revision key, and its generated `ChildContents.vue` contains the final heading and filter changes.

## Declined to judge

- Unrelated pre-existing dirty files and other builder patch functions: outside this scoped change.
- The native management list's existing default-page retrieval and table behavior: retained from upstream; the new grouped default view uses the existing all-pages loader.
- Runtime compilation, browser behavior, and production deployment: not executed under the explicit review constraints. Source inspection is not a passing runtime verification result.

## Verdict

**Spec: satisfied in the final source. Quality: approved by scoped static review.** The change reuses the existing component and native management controls with a small set of page and mode changes. No additional source fixes are required from this review. Runtime behavior remains unverified.
