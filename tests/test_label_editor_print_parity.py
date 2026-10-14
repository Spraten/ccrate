import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class LabelEditorPrintParityTests(unittest.TestCase):
    def test_canvas_text_uses_the_shared_print_fitting_result(self):
        renderer = (ROOT / 'label-ui/vendor/print-design-pro/src/components/canvas/ElementRenderer.vue').read_text()
        self.assertIn('fitTextToBox', renderer)
        self.assertIn('measure: text => textMeasureContext.measureText(text).width', renderer)
        self.assertIn('return fittedText.lines.join(', renderer)
        self.assertIn('>{{ fittedTextContent }}</div>', renderer)


if __name__ == '__main__':
    unittest.main()
