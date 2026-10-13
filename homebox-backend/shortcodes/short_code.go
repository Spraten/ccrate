package shortcodes

import "strings"

// Prefix derives the stable, readable model hint used by all native allocators.
func Prefix(modelNumber, name string) string {
	for _, source := range []string{modelNumber, name} {
		var normalized strings.Builder
		for i := 0; i < len(source); i++ {
			c := source[i]
			if c >= 'a' && c <= 'z' {
				c -= 'a' - 'A'
			}
			if c >= 'A' && c <= 'Z' || c >= '0' && c <= '9' {
				normalized.WriteByte(c)
			}
		}
		prefix := normalized.String()
		if prefix == "" {
			continue
		}
		if len(prefix) > 3 {
			prefix = prefix[:3]
		}
		prefix += strings.Repeat("X", 3-len(prefix))
		if prefix[0] >= '0' && prefix[0] <= '9' && prefix[1] >= '0' && prefix[1] <= '9' && prefix[2] >= '0' && prefix[2] <= '9' {
			prefix = "X" + prefix[1:]
		}
		return prefix
	}
	return "ITM"
}
