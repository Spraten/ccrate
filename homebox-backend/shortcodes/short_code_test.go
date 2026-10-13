package shortcodes

import "testing"

func TestPrefixUsesASCIIModelHintAndNonNumericPrefix(t *testing.T) {
	for _, test := range []struct{ model, name, want string }{
		{"m-18", "Other name", "M18"},
		{"", "Ångström drill", "NGS"},
		{"123-45", "Widget", "X23"},
		{"", "", "ITM"},
	} {
		if got := Prefix(test.model, test.name); got != test.want {
			t.Errorf("Prefix(%q, %q) = %q, want %q", test.model, test.name, got, test.want)
		}
	}
}
