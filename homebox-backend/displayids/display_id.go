package displayids

import (
	"regexp"
	"sort"
	"strconv"
	"strings"
)

var separators = regexp.MustCompile(`[^A-Z0-9]+`)

func Segment(value string) string {
	value = strings.ToUpper(strings.TrimSpace(value))
	return strings.Trim(separators.ReplaceAllString(value, "-"), "-")
}

func Base(typeName string, locationPath []string) string {
	segments := make([]string, 0, len(locationPath)+2)
	if name := Segment(typeName); name != "" {
		segments = append(segments, name)
	}
	for _, part := range locationPath {
		if name := Segment(part); name != "" {
			segments = append(segments, name)
		}
	}
	if len(locationPath) == 0 {
		segments = append(segments, "UNLOCATED")
	}
	// UNKNOWN keeps IDs searchable when every type/path name is non-ASCII.
	if len(segments) == 0 {
		segments = append(segments, "UNKNOWN")
	}
	return strings.Join(segments, "-")
}

type Entry struct {
	ID      string
	AssetID int64
	Base    string
}

// Assign returns stable, unique IDs for the supplied connected base families.
func Assign(entries []Entry) map[string]string {
	byBase := make(map[string][]Entry)
	for _, entry := range entries {
		byBase[entry.Base] = append(byBase[entry.Base], entry)
	}
	preferred := make(map[string]string, len(entries))
	preferredCounts := make(map[string]int, len(entries))
	for base, family := range byBase {
		sort.Slice(family, func(i, j int) bool {
			if family[i].AssetID != family[j].AssetID {
				return family[i].AssetID < family[j].AssetID
			}
			return family[i].ID < family[j].ID
		})
		for i, entry := range family {
			id := base
			if len(family) > 1 {
				id += "-" + strconv.Itoa(i+1)
			}
			preferred[entry.ID] = id
			preferredCounts[id]++
		}
	}
	sort.Slice(entries, func(i, j int) bool {
		if entries[i].Base != entries[j].Base {
			return entries[i].Base < entries[j].Base
		}
		if entries[i].AssetID != entries[j].AssetID {
			return entries[i].AssetID < entries[j].AssetID
		}
		return entries[i].ID < entries[j].ID
	})
	result := make(map[string]string, len(entries))
	used := make(map[string]bool, len(entries))
	for _, entry := range entries {
		id := preferred[entry.ID]
		if preferredCounts[id] > 1 || used[id] {
			for counter := 1; ; counter++ {
				candidate := id + "-" + strconv.Itoa(counter)
				if !used[candidate] && preferredCounts[candidate] == 0 {
					id = candidate
					break
				}
			}
		}
		used[id] = true
		result[entry.ID] = id
	}
	return result
}

// SearchBases returns the literal ID and bases that could produce it with a
// trailing numeric collision counter, including nested counter conflicts.
func SearchBases(id string) []string {
	segments := strings.Split(strings.ToUpper(strings.TrimSpace(id)), "-")
	bases := []string{strings.Join(segments, "-")}
	for len(segments) > 1 {
		last := segments[len(segments)-1]
		if last == "" {
			break
		}
		for _, r := range last {
			if r < '0' || r > '9' {
				return bases
			}
		}
		segments = segments[:len(segments)-1]
		bases = append(bases, strings.Join(segments, "-"))
	}
	return bases
}
