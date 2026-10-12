import pathlib
import unittest
import os

from tests import test_workshop_browser as browser_fixture


ROOT = pathlib.Path(__file__).resolve().parents[1]


class WorkshopLayoutTests(unittest.TestCase):
    """Exercise the maintained renderer with the real browser fixture and CSS."""

    @classmethod
    def setUpClass(cls):
        browser_fixture.WorkshopBrowserTests.setUpClass()
        cls.source = browser_fixture.WorkshopBrowserTests.source
        cls.css = browser_fixture.WorkshopBrowserTests.css

    def setUp(self):
        browser_fixture.WorkshopBrowserTests.setUp(self)

    def _catalog_asset(self, url):
        return browser_fixture.WorkshopBrowserTests._catalog_asset(self, url)

    def install_plan(self):
        room = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        drawing = {
            'id': '33333333-3333-4333-8333-333333333333',
            'name': 'A very long name for checking inspector wrapping without forcing a wide panel',
            'kind': 'Rack', 'x': 1, 'y': 1, 'width': 3, 'height': 2,
            'rotation': 0, 'location_id': None,
        }
        document = {'version': 2, 'rooms': [{
            'id': room, 'location_id': None, 'name': 'Main room', 'width': 14,
            'height': 20, 'unit': 'ft', 'approximate': False, 'objects': [drawing],
        }]}
        browser_fixture.WorkshopBrowserTests.install_rooms4_plan(self, document, selected_drawing=drawing['id'])

    @staticmethod
    def set_native_theme(page, dark=False):
        values = {
            '--background': '222 26% 13%' if dark else '0 0% 100%',
            '--foreground': '210 20% 96%' if dark else '222.2 84% 4.9%',
            '--card': '222 23% 17%' if dark else '0 0% 100%',
            '--card-foreground': '210 20% 96%' if dark else '222.2 84% 4.9%',
            '--primary': '204 85% 60%' if dark else '222.2 47.4% 11.2%',
            '--primary-foreground': '220 40% 10%' if dark else '210 40% 98%',
            '--muted-foreground': '210 12% 72%' if dark else '215.4 16.3% 46.9%',
            '--border': '215 20% 30%' if dark else '214.3 31.8% 91.4%',
            '--input': '215 20% 30%' if dark else '214.3 31.8% 91.4%',
            '--accent': '214 35% 26%' if dark else '210 40% 96.1%',
            '--accent-foreground': '210 20% 96%' if dark else '222.2 47.4% 11.2%',
            '--ring': '204 85% 65%' if dark else '222.2 84% 4.9%',
        }
        page.locator('html').evaluate(
            '(el,values)=>Object.entries(values).forEach(([key,value])=>el.style.setProperty(key,value))',
            values,
        )

    def assert_no_horizontal_overflow(self):
        state = self.page.evaluate('''() => ({
          viewport: document.documentElement.clientWidth,
          page: document.documentElement.scrollWidth,
          workspace: (() => { const e=document.querySelector('.planner-workspace'); return [e.clientWidth,e.scrollWidth] })(),
          panels: [...document.querySelectorAll('.planner-palette,.planner-inspector')].map(e=>[e.clientWidth,e.scrollWidth])
        })''')
        self.assertLessEqual(state['page'], state['viewport'] + 1, state)
        for width, scroll_width in [state['workspace'], *state['panels']]:
            self.assertLessEqual(scroll_width, width + 1, state)

    @staticmethod
    def contrast_ratio(page, selector):
        colors = page.locator(selector).first.evaluate('''el => {
          const rgb = value => value.match(/[\\d.]+/g).slice(0,3).map(Number);
          return [rgb(getComputedStyle(el).color),rgb(getComputedStyle(el).backgroundColor)];
        }''')
        def luminance(rgb):
            channels = [v / 255 for v in rgb]
            linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in channels]
            return .2126 * linear[0] + .7152 * linear[1] + .0722 * linear[2]
        foreground, background = map(luminance, colors)
        high, low = max(foreground, background), min(foreground, background)
        return (high + .05) / (low + .05)

    def test_desktop_geometry_zoom_theme_and_keyboard_access(self):
        self.install_plan()
        self.set_native_theme(self.page)
        self.page.get_by_role('button', name='Edit', exact=True).click()
        proof_dir = pathlib.Path(os.environ.get('WORKSHOP_LAYOUT_PROOF_DIR', ROOT / 'work/workshop-layout'))
        proof_dir.mkdir(parents=True, exist_ok=True)

        for width, height in ((1280, 800), (1440, 900)):
            self.page.set_viewport_size({'width': width, 'height': height})
            palette = self.page.locator('.planner-palette')
            canvas = self.page.locator('.planner-canvas-frame')
            inspector = self.page.locator('.planner-inspector')
            palette.wait_for(state='visible')
            self.assertTrue(canvas.is_visible())
            self.assertTrue(inspector.is_visible())
            geometry = self.page.evaluate('''() => {
              const box = selector => { const r=document.querySelector(selector).getBoundingClientRect(); return {x:r.x,y:r.y,width:r.width,height:r.height}; };
              const root=document.querySelector('.room-planner'), workspace=document.querySelector('.planner-workspace');
              return {viewport:[innerWidth,innerHeight],pageHeight:document.documentElement.scrollHeight,root:[root.clientWidth,root.scrollWidth],workspace:[workspace.clientWidth,workspace.scrollWidth],
                canvas:box('.planner-canvas-frame'),palette:box('.planner-palette'),inspector:box('.planner-inspector'),
                paletteOverflow:getComputedStyle(document.querySelector('.planner-palette')).overflowY,
                inspectorOverflow:getComputedStyle(document.querySelector('.planner-inspector')).overflowY};
            }''')
            self.assertLessEqual(geometry['pageHeight'], height + 1, geometry)
            self.assertLessEqual(geometry['root'][1], geometry['root'][0] + 1, geometry)
            self.assertLessEqual(geometry['workspace'][1], geometry['workspace'][0] + 1, geometry)
            self.assertGreater(geometry['canvas']['width'], geometry['palette']['width'], geometry)
            self.assertGreater(geometry['canvas']['width'], geometry['inspector']['width'], geometry)
            self.assertGreater(geometry['canvas']['width'] * geometry['canvas']['height'],
                               geometry['palette']['width'] * geometry['palette']['height'], geometry)
            self.assertEqual((geometry['paletteOverflow'], geometry['inspectorOverflow']), ('auto', 'auto'))
            first_pair = palette.locator('.planner-preset-group').first.locator('.planner-preset-card').evaluate_all('''cards=>cards.slice(0,2).map(el=>{
              const r=el.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width};})''')
            self.assertEqual(len(first_pair), 2, first_pair)
            self.assertAlmostEqual(first_pair[0]['y'], first_pair[1]['y'], delta=1, msg=str(first_pair))
            self.assertGreater(first_pair[1]['x'], first_pair[0]['x'], first_pair)
            self.assertGreater(first_pair[0]['width'], 0, first_pair)
            self.assertEqual(self.page.get_by_label('Search objects').evaluate('el=>getComputedStyle(el).position'), 'sticky')
            self.assertGreater(palette.evaluate('el=>el.scrollHeight'), palette.evaluate('el=>el.clientHeight'))
            sticky = palette.evaluate('''el=>{el.scrollTop=el.scrollHeight;const input=el.querySelector('input[type=search]');
              const panel=el.getBoundingClientRect(),search=input.getBoundingClientRect();
              return {top:search.top,panelTop:panel.top,bottom:search.bottom,panelBottom:panel.bottom};}''')
            self.assertGreaterEqual(sticky['top'], sticky['panelTop'], sticky)
            self.assertLessEqual(sticky['bottom'], sticky['panelBottom'], sticky)
            palette.evaluate('el=>el.scrollTop=0')
            self.assert_no_horizontal_overflow()
            self.page.screenshot(path=str(proof_dir / f'after-{width}x{height}.png'), full_page=True)

        search = self.page.get_by_label('Search objects')
        search.fill('wall cabinet')
        wall_cabinet = self.page.locator('.planner-preset-card[data-preset-id="wall-cabinet"]')
        base_cabinet = self.page.locator('.planner-preset-card[data-preset-id="base-cabinet"]')
        bins = self.page.locator('.planner-preset-group[data-preset-category="Bins"]')
        self.assertTrue(wall_cabinet.is_visible())
        self.assertFalse(base_cabinet.is_visible(), 'Unmatched presets in a matching category stay hidden.')
        self.assertFalse(bins.is_visible(), 'Categories with no matching presets stay hidden.')
        search.fill('')
        self.assertTrue(base_cabinet.is_visible(), 'Clearing search restores same-category presets.')
        self.assertTrue(bins.is_visible(), 'Clearing search restores unmatched categories.')

        contrast_target = self.page.locator('.planner-preset-card').first
        contrast_target.evaluate("el=>el.style.transition='none'")
        self.set_native_theme(self.page)
        self.assertGreaterEqual(self.contrast_ratio(self.page, '.planner-preset-card'), 4.5)
        self.set_native_theme(self.page, dark=True)
        self.assertGreaterEqual(self.contrast_ratio(self.page, '.planner-preset-card'), 4.5)

        search.focus()
        for _ in range(50):
            self.page.keyboard.press('Tab')
            focused = self.page.locator(':focus')
            if focused.evaluate("el=>el.matches('.planner-preset-card')"):
                break
        self.assertTrue(focused.evaluate("el=>el.matches('.planner-preset-card')"),
                        'Keyboard Tab reaches an illustrated catalog card.')
        focus_style = focused.evaluate('''el=>({width:getComputedStyle(el).outlineWidth,style:getComputedStyle(el).outlineStyle,
                                             color:getComputedStyle(el).outlineColor})''')
        self.assertEqual(focus_style['width'], '2px', focus_style)
        self.assertNotEqual(focus_style['style'], 'none', focus_style)
        self.assertTrue(focus_style['color'], focus_style)

        self.page.set_viewport_size({'width': 640, 'height': 450})
        self.assertTrue(self.page.get_by_role('button', name='Objects', exact=True).is_visible())
        self.assertTrue(self.page.get_by_role('button', name='Details', exact=True).is_visible())
        self.page.get_by_role('button', name='Objects', exact=True).click()
        self.page.get_by_role('button', name='Details', exact=True).click()
        self.assertTrue(self.page.get_by_label('Search objects').is_visible())
        self.assertTrue(self.page.get_by_label('Workshop inspector').is_visible())
        self.assert_no_horizontal_overflow()
        self.page.screenshot(path=str(proof_dir / 'after-200pct-640x450.png'), full_page=True)
        self.assertEqual(self.errors, [])


if __name__ == '__main__':
    unittest.main()
