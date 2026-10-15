import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../homebox-ui/overlay/lib/workshop-tools.js", import.meta.url), "utf8");

function extractFunction(name) {
  const start = source.indexOf(`function ${name}(`);
  assert.notEqual(start, -1, `production ${name} helper exists`);
  const bodyStart = source.indexOf("{", start);
  let depth = 0;
  for (let index = bodyStart; index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    if (source[index] === "}") depth -= 1;
    if (depth === 0) return source.slice(start, index + 1);
  }
  assert.fail(`production ${name} helper is unterminated`);
}

test("changing Letter sheet layout preserves item previews and invalidates only the composed paper", () => {
  const match = source.match(/\blayout\(margin,gap\)\{([^{}]*)\}/);
  assert.ok(match, "label layout action exists");
  const clearPaperSource = extractFunction("clearPaper");

  const review = { review_id: "review-1", entity_id: "item-1" };
  const workspace = {
    marginMm: 10,
    gapMm: 3,
    reviews: [review],
    printedReviewIds: ["review-1"],
    pages: [{ labels: ["review-1"] }],
    paper: { pages: [{ labels: ["review-1"] }] },
  };
  const paperState = new Function("workspace", `let paperRevision=0,paperCurrent=()=>true; ${clearPaperSource}; return {clearPaper, get paperRevision(){return paperRevision}, isCurrent(){return paperCurrent()}}`)(workspace);
  const clearReviews = () => assert.fail("layout changes must not clear item previews");
  const layout = new Function("workspace", "clearPaper", "clearReviews", `return ({${match[0]}}).layout`)(
    workspace,
    paperState.clearPaper,
    clearReviews,
  );

  layout(12, 5);

  assert.equal(workspace.marginMm, 12);
  assert.equal(workspace.gapMm, 5);
  assert.deepEqual(workspace.reviews, [review]);
  assert.deepEqual(workspace.printedReviewIds, ["review-1"]);
  assert.deepEqual(workspace.pages, []);
  assert.equal(workspace.paper, null);
  assert.equal(paperState.paperRevision, 1);
  assert.equal(paperState.isCurrent(), false);
});
