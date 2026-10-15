package displayids

import (
	"reflect"
	"testing"
)

func TestBaseUsesCompletePath(t *testing.T) {
	if got := Base("Bin", []string{"D", "GC", "C", "1"}); got != "BIN-D-GC-C-1" { t.Fatalf("Base() = %q", got) }
}

func TestBaseHasFallbackForNamesWithoutASCIIIdentifierCharacters(t *testing.T) {
	if got := Base("物品", []string{"部屋"}); got != "UNKNOWN" { t.Fatalf("Base() = %q", got) }
}

func TestAssignCollisionFamilyAndCrossBaseOverlap(t *testing.T) {
	entries := []Entry{{ID:"b",AssetID:2,Base:"BIN-D-C-1"},{ID:"a",AssetID:1,Base:"BIN-D-C-1"},{ID:"natural",AssetID:3,Base:"BIN-D-C-1-1"}}
	got := Assign(entries)
	if got["a"] != "BIN-D-C-1-1-1" || got["b"] != "BIN-D-C-1-2" || got["natural"] != "BIN-D-C-1-1-2" { t.Fatalf("unexpected stable assignment: %#v", got) }
	seen:=map[string]bool{}; for _, id:=range got { if seen[id] { t.Fatalf("duplicate display ID %q",id) }; seen[id]=true }
}

func TestSearchBasesIncludesNumericSuffixInterpretations(t *testing.T) {
	want:=[]string{"BIN-D-C-1-2","BIN-D-C-1","BIN-D-C"}
	if got:=SearchBases(want[0]); !reflect.DeepEqual(got,want) { t.Fatalf("SearchBases() = %#v",got) }
	want=[]string{"UNKNOWN-1","UNKNOWN"}
	if got:=SearchBases(want[0]); !reflect.DeepEqual(got,want) { t.Fatalf("SearchBases() for sentinel suffix = %#v",got) }
}
