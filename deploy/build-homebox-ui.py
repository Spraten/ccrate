#!/usr/bin/env python3
"""Build a native Homebox frontend overlay without modifying the upstream checkout.

Install the pinned frontend dependencies in work/homebox-ui-build first. A
fresh --build-root installs from its copied lockfile. Output stays staged until
a verified release is selected by work/homebox-ui-current.
"""
import argparse
import os
import json
import pathlib
import shutil
import subprocess
import sys
import re
import threading
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(pathlib.Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from homebox_patchset import source_commit
BUILD = ROOT / 'work/homebox-ui-build'
TOOLCHAIN_ROOT = ROOT / 'work/toolchains'
UPSTREAM_ROOT = ROOT


def replace(path, old, new):
    target = BUILD / path
    source = target.read_text()
    if source.count(old) != 1:
        raise RuntimeError(f'Upstream changed: expected one patch anchor in {path}')
    target.write_text(source.replace(old, new))


def configure_ui_component_discovery():
    # Keep shadcn's TypeScript barrels importable while Nuxt auto-discovers only
    # the Vue components they intentionally export. Register after shadcn-nuxt
    # so its components:dirs hook has already appended its directory.
    replace(
        'nuxt.config.ts',
        '''  modules: [
    "@nuxtjs/tailwindcss",
    "@pinia/nuxt",
    "@vueuse/nuxt",
    "@vite-pwa/nuxt",
    "unplugin-icons/nuxt",
    "shadcn-nuxt",
    "@nuxt/eslint",
  ],''',
        '''  modules: [
    "@nuxtjs/tailwindcss",
    "@pinia/nuxt",
    "@vueuse/nuxt",
    "@vite-pwa/nuxt",
    "unplugin-icons/nuxt",
    "shadcn-nuxt",
    "@nuxt/eslint",
    (_options, nuxt) => {
      nuxt.hook("components:dirs", dirs => {
        for (let index = 0; index < dirs.length; index++) {
          const source = dirs[index];
          if (!source) continue;
          const dir = typeof source === "string" ? { path: source, extensions: [] } : source;
          if (dir.path.replaceAll("\\\\", "/").includes("components/ui")) {
            dir.extensions = ["vue"];
            dirs[index] = dir;
          }
        }
      });
    },
  ],''',
    )


def filter_known_wasi_warning(output):
    """Drop only the exact Node WASI notice known to accompany the Pi fallback."""
    return re.sub(
        r'(?m)^ERROR \(node:\d+\) ExperimentalWarning: WASI is an experimental feature and might change at any time(?:\r?\n|$)',
        '',
        output,
    )


def has_frontend_tool_failure(output):
    """Recognize invocation failures that must never be waived as upstream TS errors."""
    return re.search(
        r'(?im)^(?:ERR_PNPM_[A-Z0-9_]+\b|\s*ERROR\s+spawn\b|Error:|Error \[ERR_[A-Z_]+\]:|'
        r'Error: (?:Cannot find module|Cannot find package|spawn .* ENOENT)|'
        r'.* is not recognized as an internal or external command\.?)',
        output,
    ) is not None


def is_only_known_upstream_typecheck_failure(output, baseline, pin):
    if has_frontend_tool_failure(output):
        return False
    nuxt_exit_codes = re.findall(
        r'(?m)^\s*ERROR\s+Process exited with non-zero status \((\d+)\)\s*$',
        output,
    )
    if nuxt_exit_codes != ['2']:
        return False
    diagnostics = [
        list(match.groups())
        for match in re.finditer(
            r'^(.+?)\(\d+,\d+\): error (TS\d+): (.*)$', output, re.M
        )
    ]
    additional = Counter(map(tuple, diagnostics)) - Counter(map(tuple, baseline['diagnostics']))
    return baseline['pin'] == pin and bool(diagnostics) and not additional


def resolve_pnpm_launcher(toolchain_root, platform=None):
    pnpm = toolchain_root/'pnpm/node_modules/.bin/pnpm'
    if (platform or os.name) == 'nt':
        pnpm_cmd = pnpm.with_suffix('.cmd')
        if pnpm_cmd.exists():
            return pnpm_cmd
    return pnpm


def brand_frontend():
    # Brand values and assets change; API identifiers, theme keys and URLs stay native.
    for folder in ('pages', 'components', 'layouts'):
        for path in (BUILD/folder).rglob('*.vue'):
            text = re.sub(r'\bHome(?:Box|box)\b', 'C-Crate', path.read_text())
            path.write_text(text)
    for path in (BUILD/'nuxt.config.ts', BUILD/'lib/data/themes.ts'):
        text = path.read_text().replace('"Homebox"', '"C-Crate"').replace('"Home Inventory App"', '"Workshop inventory and equipment checkout"')
        path.write_text(text)
    def values(value):
        if isinstance(value, str): return value.replace('HomeBox', 'C-Crate').replace('Homebox', 'C-Crate')
        if isinstance(value, dict): return {key: values(item) for key, item in value.items()}
        if isinstance(value, list): return [values(item) for item in value]
        return value
    for path in (BUILD/'locales').glob('*.json'):
        path.write_text(json.dumps(values(json.loads(path.read_text(encoding='utf-8'))), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    logo = (ROOT/'kiosk/branding/caci-create.svg').read_text()
    (BUILD/'components/App/Logo.vue').write_text('<template>\n'+logo+'</template>\n')
    shutil.copytree(ROOT/'kiosk/branding', BUILD/'public', dirs_exist_ok=True)
    replace('pages/index.vue', '            HomeB\n            <AppLogo class="-mb-4 w-12" />\n            x', '<AppLogo aria-hidden="true" class="mr-3 size-14 shrink-0" /><span>C-Crate</span>')
    replace('layouts/default.vue', '          </NuxtLink>\n\n          <CollectionSelector />', '            <span class="block text-center text-base font-bold group-data-[collapsible=icon]:hidden">C-Crate</span>\n          </NuxtLink>\n\n          <CollectionSelector />')


def item_log_frontend():
    # One fail-closed template anchor keeps the disclosure beside native Details.
    path = 'pages/item/[id]/index.vue'
    replace(path, '  import LabelMaker from', '  import WorkshopItemLog from "@/components/Workshop/ItemLog.vue";\n  import ItemLoans from "@/components/Workshop/ItemLoans.vue";\n  import LabelMaker from')
    details_anchor = '          </DetailsSection>\n        </BaseCard>\n\n        <!-- anything in this is not rendered if on another page -->'
    replace(path, details_anchor, '          </DetailsSection>\n          <div v-if="item.displayId" class="flex items-center gap-2 px-6 pb-2"><span class="text-sm text-muted-foreground" title="Generated from item type and full storage path; regenerated when the item moves.">Display ID</span><code class="font-mono font-semibold">{{ item.displayId }}</code><CopyText :text="item.displayId" :icon-size="16" /></div>\n          <div v-if="item.shortCode" class="flex items-center gap-2 px-6 pb-4"><span class="text-sm text-muted-foreground">Short code</span><code class="font-mono font-semibold">{{ item.shortCode }}</code><CopyText :text="item.shortCode" :icon-size="16" /></div>\n        </BaseCard>\n\n        <WorkshopItemLog v-if="!hasNested" :item-id="itemId" />\n\n        <!-- anything in this is not rendered if on another page -->')


def move_create_actions_after_photo_preview(source):
    """Keep both existing create actions after uploaded-photo previews."""
    action_open = '      <div class="mt-4 flex flex-row-reverse">'
    action_start = source.find(action_open)
    preview_start = source.find('      <PhotoUploaderPreview\n')
    if action_start < 0 or preview_start < 0:
        raise RuntimeError('Upstream changed: expected the create actions and photo preview in CreateModal.vue')
    if source.count(action_open) != 1 or source.count('      <PhotoUploaderPreview\n') != 1:
        raise RuntimeError('Upstream changed: expected one create action block and photo preview in CreateModal.vue')

    action_close = source.find('\n      </div>', action_start)
    button_group_start = source.find('        <ButtonGroup>', action_start, action_close)
    if action_close < 0 or button_group_start < 0:
        raise RuntimeError('Upstream changed: expected the create buttons inside their actions block')
    button_group_end = source.find('        </ButtonGroup>', button_group_start)
    if button_group_end < 0 or button_group_end > action_close:
        raise RuntimeError('Upstream changed: expected the create buttons inside their actions block')
    if source[action_start + len(action_open):button_group_start].strip() or source[button_group_end + len('        </ButtonGroup>'):action_close].strip():
        raise RuntimeError('Upstream changed: expected only the create button group inside its actions block')
    action_end = action_close + len('\n      </div>')
    actions = source[action_start:action_end]
    if actions.count('type="submit"') != 1 or actions.count('@click="create(false)"') != 1:
        raise RuntimeError('Upstream changed: expected both existing create actions in CreateModal.vue')
    if preview_start < action_start:
        return source

    if source[action_end:preview_start] != '\n\n':
        raise RuntimeError('Upstream changed: expected create actions directly before the photo preview')
    preview_tag_end = source.find('>', preview_start)
    if preview_tag_end < 0 or source[preview_tag_end - 1] != '/':
        raise RuntimeError('Upstream changed: expected a self-closing photo preview in CreateModal.vue')
    preview_end = preview_tag_end + 1
    return source[:action_start] + '\n\n' + source[preview_start:preview_end] + '\n\n' + actions + source[preview_end:]


def nest_frontend():
    replace('lib/api/classes/items.ts', '  orderBy?: string;', '  orderBy?: string;\n  isLocation?: boolean;')
    replace(
        'components/ui/dialog-provider/utils.ts',
        '  [DialogID.CreateEntity]:\n    | { baseType: "item"; product?: BarcodeProduct; barcode?: string; subItem?: true; resume?: true }\n    | { baseType: "location" };',
        '  [DialogID.CreateEntity]: (\n    | { baseType: "item"; product?: BarcodeProduct; barcode?: string; subItem?: true; resume?: true }\n    | { baseType: "location" }\n  ) & { parentId?: string };',
    )
    path = 'components/Entity/CreateModal.vue'
    replace(path, ':entity-types="subItemCreate ? entityTypes.filter(t => !t.isLocation) : entityTypes"', ':entity-types="entityTypes"')
    target = BUILD/path
    source = target.read_text()
    # Older frontend pins did not yet include model-number handling. Add it
    # only when absent; barcode-aware pins already supply the complete flow.
    if 'v-model="form.modelNumber"' not in source:
        replace(path, '      <FormTextField\n        v-if="!selectedEntityType?.isLocation"\n        v-model.number="form.quantity"', '      <FormTextField v-if="!selectedEntityType?.isLocation" v-model="form.modelNumber" label="Model number" :max-length="255" />\n      <FormTextField\n        v-if="!selectedEntityType?.isLocation"\n        v-model.number="form.quantity"')
    elif source.count('v-model="form.modelNumber"') != 1:
        raise RuntimeError(f'Upstream changed: expected one model-number control in {path}')
    if 'modelNumber: "",' not in source:
        replace(path, '    name: "",\n    quantity: 1,', '    name: "",\n    modelNumber: "",\n    quantity: 1,')
    elif source.count('modelNumber: "",') != 1:
        raise RuntimeError(f'Upstream changed: expected one model-number form field in {path}')
    if 'form.modelNumber = "";' not in source:
        replace(path, '    form.name = "";\n    form.quantity = 1;', '    form.name = "";\n    form.modelNumber = "";\n    form.quantity = 1;')
    target = BUILD/path
    text = target.read_text()
    selector = '      <ItemSelector\n'
    if text.count(selector) != 1:
        raise RuntimeError(f'Upstream changed: expected one sub-item selector in {path}')
    start = text.index(selector)
    end = text.index('\n      />', start) + len('\n      />')
    text = text[:start]+text[end:]
    import_block = text[text.index('  import type {'):text.index('  } from "~~/lib/api/types/data-contracts";')]
    if 'EntitySummary,' not in import_block:
        if text.count('    EntityCreate,') != 1:
            raise RuntimeError(f'Upstream changed: expected one EntityCreate import in {path}')
        text = text.replace('    EntityCreate,', '    EntityCreate,\n    EntitySummary,')
    elif import_block.count('EntitySummary,') != 1:
        raise RuntimeError(f'Upstream changed: expected one EntitySummary import in {path}')
    text = text.replace('const found = locations.value.find(l => l.id === data.defaultLocation!.id);', 'const { data: found } = await api.items.get(data.defaultLocation.id);')
    text = text.replace('location: locations.value && locations.value.length > 0 ? locations.value[0] : ({} as EntityOut)', 'location: null as EntitySummary | null')
    text = text.replace('      form.parentId = null;', '      form.parentId = null;\n      form.location = null;')
    text = text.replace('            parent.value = data;', '            parentItemLocationId = data.id;')
    start = text.index('          if (data.parent) {'); end = text.index('\n        }', start)
    text = text[:start]+text[end:]
    location_context_anchor = '''      const locId = locationId.value ? locationId.value : parentItemLocationId;
      applyInitialBarcodeParamAfterContext(initialBarcode, form, lookupBarcode, () => {
        if (locId) {
          const found = locations.value.find(l => l.id === locId);
          if (found) {
            form.location = found;
          }
        }

        if (tagId.value) {'''
    if text.count(location_context_anchor) != 1:
        raise RuntimeError(f'Upstream changed: expected one barcode-aware location context anchor in {path}')
    text = text.replace(
        location_context_anchor,
        '''      const locId = params.parentId || locationId.value || parentItemLocationId;
      if (locId) {
        const { data } = await api.items.get(String(locId));
        if (data) form.location = data;
      }

      applyInitialBarcodeParamAfterContext(initialBarcode, form, lookupBarcode, () => {
        if (tagId.value) {''',
    )
    start = text.index('    // Items must live somewhere'); end = text.index('    if (loading.value)', start)
    text = text[:start]+text[end:]
    text = text.replace('parentId: form.location.id as string', 'parentId: form.location?.id || null').replace('parentId: form.parentId || (form.location.id as string)', 'parentId: form.location?.id || null')
    # Barcode-aware upstream already owns the model-number field, state and
    # create payloads. Keep the overlay from reinserting duplicate keys/imports.
    existing_model_number_payloads = text.count('modelNumber: form.modelNumber,')
    if existing_model_number_payloads not in (0, 3):
        raise RuntimeError(f'Upstream changed: expected zero or three model-number payloads in {path}')
    if existing_model_number_payloads == 0:
        if text.count('const templateRequest = {') != 1:
            raise RuntimeError(f'Upstream changed: expecteuÓMµ¶‰žËkºwµçt(€€€™¥¹…±±äì¥˜€¡É•Ù¥Í¥½¸€ôôô¥Ñ•µI•Ù¥Í¥½¸¤¥Ñ•µ1½…‘¥¹œ¹Ù…±Õ”€ô™…±Í”ìô(€ô(€™Õ¹Ñ¥½¸É•™É•Í¡Y¥Í¥‰±•%Ñ•µÌ ¤ì¥˜€¡‘½Õµ•¹Ð¹Ù¥Í¥‰¥±¥ÑåMÑ…Ñ”€ôôô€‰Ù¥Í¥‰±”ˆ€˜˜€…¥Ñ•µ1½…‘¥¹œ¹Ù…±Õ”¤Ù½¥±½…‘5•µ‰•É1½…¹Ì ¤ìô(€™Õ¹Ñ¥½¸É•™É•Í¡5•µ‰•ÉÌ ¤ìÙ½¥±½…‘5•µ‰•ÉÌ ¤ìÙ½¥±½…‘	…‘•Ì ¤ìÙ½¥±½…‘5•µ‰•É1½…¹Ì ¤ìô(€±•ÐÝ½É­Í¡½ÁI•Ù¥Í¥½¸€ô€Àì(€…Íå¹Œ™Õ¹Ñ¥½¸±½…‘	…‘•Ì ¤ì(€€€½¹ÍÐÉ•Ù¥Í¥½¸€ô€¬­Ý½É­Í¡½ÁI•Ù¥Í¥½¸ì(€€€‰…‘•I½ÝÌ¹Ù…±Õ”€ômtìÁ•½Á±•I½ÝÌ¹Ù…±Õ”€ômtìÝ½É­Í¡½ÁÉÉ½È¹Ù…±Õ”€ô€ˆˆì(€€€ÑÉäì(€€€€€…Ý…¥ÐÝ½É­Í¡½À¹É•™É•Í  ¤ì(€€€€€¥˜€ …Ý½É­Í¡½À¹µ…¹…•È¹Ù…±Õ”¤É•ÑÕÉ¸ì(€€€€€½¹ÍÐm‰…‘•Ì°Á•½Á±•t€ô…Ý…¥ÐAÉ½µ¥Í”¹…±°¡mÝ½É­Í¡½À¹É•ÅÕ•ÍÐñ…¹åmtø ‰‰…‘•Ìˆ¤°Ý½É­Í¡½À¹É•ÅÕ•ÍÐñ…¹åmtø ‰Á•½Á±”ˆ¥t¤ì(€€€€€¥˜€¡É•Ù¥Í¥½¸€ôôôÝ½É­Í¡½ÁI•Ù¥Í¥½¸¤ì‰…‘•I½ÝÌ¹Ù…±Õ”€ô‰…‘•ÌìÁ•½Á±•I½ÝÌ¹Ù…±Õ”€ôÁ•½Á±”ìô(€€€ô…Ñ €¡…ÕÍ”¤ì¥˜€¡É•Ù¥Í¥½¸€ôôôÝ½É­Í¡½ÁI•Ù¥Í¥½¸¤Ý½É­Í¡½ÁÉÉ½È¹Ù…±Õ”€ô€¡…ÕÍ”…ÌÉÉ½È¤¹µ•ÍÍ…”ìô(€ô(€Ý…Ñ ¡Í•±•Ñ•‘%°€ ¤€ôøìµ•µ‰•É1½…¹Ì¹Ù…±Õ”€ô¹Õ±°ìÉ•™É•Í¡5•µ‰•ÉÌ ¤ìô°ì™±ÕÍ è€‰Íå¹Œˆô¤ì(€½¹5½Õ¹Ñ•  ¤€ôøì(€€€Ù½¥±½…‘5•µ‰•É1½…¹Ì ¤ì(€€€Ý¥¹‘½Ü¹…‘‘Ù•¹Ñ1¥ÍÑ•¹•È ‰™½ÕÌˆ°É•™É•Í¡Y¥Í¥‰±•%Ñ•µÌ¤ì(€€€‘½Õµ•¹Ð¹…‘‘Ù•¹Ñ1¥ÍÑ•¹•È ‰Ù¥Í¥‰¥±¥Ñå¡…¹”ˆ°É•™É•Í¡Y¥Í¥‰±•%Ñ•µÌ¤ì(€€€µ•µ‰•ÉQ¥µ•È€ôÍ•Ñ%¹Ñ•ÉÙ…°¡É•™É•Í¡Y¥Í¥‰±•%Ñ•µÌ°€ÌÀÀÀÀ¤ì(€ô¤ì(€½¹	•™½É•U¹µ½Õ¹Ð  ¤€ôøì(€€€Ý½É­Í¡½ÁI•Ù¥Í¥½¸¬¬ì¥Ñ•µI•Ù¥Í¥½¸¬¬ìµ•µ‰•É1½…¹Ì¹Ù…±Õ”€ô¹Õ±°ì(€€€¥˜€¡µ•µ‰•ÉQ¥µ•È¤±•…É%¹Ñ•ÉÙ…°¡µ•µ‰•ÉQ¥µ•È¤ì(€€€Ý¥¹‘½Ü¹É•µ½Ù•Ù•¹Ñ1¥ÍÑ•¹•È ‰™½ÕÌˆ°É•™É•Í¡Y¥Í¥‰±•%Ñ•µÌ¤ì(€€€‘½Õµ•¹Ð¹É•µ½Ù•Ù•¹Ñ1¥ÍÑ•¹•È ‰Ù¥Í¥‰¥±¥Ñå¡…¹”ˆ°É•™É•Í¡Y¥Í¥‰±•%Ñ•µÌ¤ì(€ô¤ì((€½¹ÍÐ±½…‘¥¹œ€ôÉ•˜¡ÑÉÕ”¤ìœœœ¤(€€€É•Á±…”¡Á…Ñ °€œñQ…‰±••±°ùíìÕÍ•È¹¹…µ”õôð½Q…‰±••±°øœ°€œñQ…‰±••±°øñ‘¥Ø±…ÍÌô‰™±•à¥Ñ•µÌµ•¹Ñ•È…À´Ìˆøñ5•µ‰•ÉÙ…Ñ…È€éµ•µ‰•Èµ¥ô‰ÕÍ•È¹¥ˆ€é¹…µ”ô‰ÕÍ•È¹¹…µ”ˆ€¼øñÍÁ…¸±…ÍÌô‰™½¹Ðµµ•‘¥Õ´ˆùíìÕÍ•È¹¹…µ”õôð½ÍÁ…¸øð½‘¥Øøð½Q…‰±••±°øœ¤(€€€É•Á±…”¡Á…Ñ °€œ€¥µÁ½ÉÐì	ÕÑÑ½¸ôœ°€œ€¥µÁ½ÉÐ5•µ‰•ÉÙ…Ñ…È™É½´€‰ ½½µÁ½¹•¹ÑÌ½]½É­Í¡½À½5•µ‰•ÉÙ…Ñ…È¹ÙÕ”ˆíq¸€¥µÁ½ÉÐ5•µ‰•É%Ñ•µÌ™É½´€‰ ½½µÁ½¹•¹ÑÌ½]½É­Í¡½À½5•µ‰•É%Ñ•µÌ¹ÙÕ”ˆíq¸€¥µÁ½ÉÐÑåÁ”ì]½É­Í¡½Á1½…¸ô™É½´€‰ ½±¥ˆ½Ý½É­Í¡½Àµ±½…¹Ìˆíq¸€¥µÁ½ÉÐ	…‘•Ñ¥½¹Ì™É½´€‰ ½½µÁ½¹•¹ÑÌ½]½É­Í¡½À½	…‘•Ñ¥½¹Ì¹ÙÕ”ˆíq¸€¥µÁ½ÉÐì	ÕÑÑ½¸ôœ¤(€€€É•Á±…”¡Á…Ñ °€œ€€€±½…‘5•µ‰•ÉÌ ¤íq¸€ô¤ìœ°€œ€€€±½…‘5•µ‰•ÉÌ ¤íq¸€€€±½…‘	…‘•Ì ¤íq¸€ô¤ìœ¤(€€€É•Á±…”¡Á…Ñ °€œ€€ñ‘¥Ø±…ÍÌô‰ÍÁ…”µä´Ðˆøœ°€œœœ€€ñ‘¥Ø±…ÍÌô‰ÍÁ…”µä´Ðˆø(€€€€ñ‘¥Ø±…ÍÌô‰™±•à™±•àµÝÉ…À¥Ñ•µÌµ•¹Ñ•È©ÕÍÑ¥™äµ‰•ÑÝ••¸…À´Ìˆø(€€€€€€ñÀ±…ÍÌô‰Ñ•áÐµÍ´Ñ•áÐµµÕÑ•µ™½É•É½Õ¹ˆù5•µ‰•ÉÌ°­¥½Í¬‰…‘•Ì…¹Ñ¡”¥Ñ•µÌ•… Á•ÉÍ½¸¡…Ì¡•­•½ÕÐ¸ð½Àø(€€€€€€ñ	ÕÑÑ½¸Ù…É¥…¹Ðô‰½ÕÑ±¥¹”ˆÍ¥é”ô‰Í´ˆ€é‘¥Í…‰±•ô‰±½…‘¥¹œñð¥Ñ•µ1½…‘¥¹œˆ±¥¬ô‰É•™É•Í¡5•µ‰•ÉÌˆùI•™É•Í µ•µ‰•ÉÌ€™…µÀì¥Ñ•µÌð½	ÕÑÑ½¸ø(€€€€ð½‘¥Øø(€€€€ñÀØµ¥˜ô‰¥Ñ•µÉÉ½ÈˆÉ½±”ô‰…±•ÉÐˆ±…ÍÌô‰Ñ•áÐµÍ´Ñ•áÐµ‘•ÍÑÉÕÑ¥Ù”ˆù½Õ±¹½Ð±½…¡•­•µ½ÕÐ¥Ñ•µÌ¸íì¥Ñ•µÉÉ½Èõôð½Àø(€€€€ñÀØµ¥˜ô‰Ý½É­Í¡½ÁÉÉ½ÈˆÉ½±”ô‰…±•ÉÐˆ±…ÍÌô‰Ñ•áÐµÍ´Ñ•áÐµ‘•ÍÑÉÕÑ¥Ù”ˆù	…‘”µ…¹…•µ•¹ÐèíìÝ½É­Í¡½ÁÉÉ½Èõô€ñ	ÕÑÑ½¸Ù…É¥…¹Ðô‰±¥¹¬ˆ±¥¬ô‰±½…‘	…‘•ÌˆùI•±½…‰…‘”µ…¹…•µ•¹Ðð½	ÕÑÑ½¸øð½Àøœœœ¤(€€€É•Á±…”¡Á…Ñ °€œñQ…‰±•!•…ùíì€‘Ð ‰½±±•Ñ¥½¸¹µ•µ‰•ÉÌ¹¹…µ”ˆ¤õôð½Q…‰±•!•…øœ°€œñQ…‰±•!•…ùUÍ•Èð½Q…‰±•!•…øœ¤(€€€É•Á±…”¡Á…Ñ °€œ€€€€€€€€€€€€€€ñQ…‰±•!•…±…ÍÌô‰Ü´ÌÈœ°€œ€€€€€€€€€€€€€€ñQ…‰±•!•…Øµ¥˜ô‰Ý½É­Í¡½À¹µ…¹…•È¹Ù…±Õ”ˆù-¥½Í¬	…‘”ð½Q…‰±•!•…ùq¸€€€€€€€€€€€€€€ñQ…‰±•!•…ù%Ñ•µÌð½Q…‰±•!•…ùq¸€€€€€€€€€€€€€€ñQ…‰±•!•…±…ÍÌô‰Ü´ÌÈœ¤(€€€É•Á±…”¡Á…Ñ °€œ€€€€€€€€€€€€€€ñQ…‰±••±°ùq¸€€€€€€€€€€€€€€€€ñ‘¥Ø±…ÍÌô‰µ°µ…ÕÑ¼ˆøœ°€œœœ€€€€€€€€€€€€€€ñQ…‰±••±°Øµ¥˜ô‰Ý½É­Í¡½À¹µ…¹…•È¹Ù…±Õ”ˆø(€€€€€€€€€€€€€€€€ñ	…‘•Ñ¥½¹Ì€éµ•µ‰•Èô‰ÕÍ•Èˆ€é‰…‘•Ìô‰‰…‘•I½ÝÌ¹™¥±Ñ•È¡É½Ü€ôøÉ½Ü¹ÕÍ•É}¥€ôôôÕÍ•È¹¥¤ˆ€é…¸µµ…¹…”ôˆ„…Á•½Á±•I½ÝÌ¹™¥¹¡É½Ü€ôøÉ½Ü¹¥€ôôôÕÍ•È¹¥¤ü¹Ý½É­Í¡½Á}µ…¹…•Èˆ€éÁÉ½Ñ•Ñ•µ½Ý¹•Èôˆ„…Á•½Á±•I½ÝÌ¹™¥¹¡É½Ü€ôøÉ½Ü¹¥€ôôôÕÍ•È¹¥¤ü¹ÁÉ½Ñ•Ñ•‘}½Ý¹•Èˆ¡…¹•ô‰±½…‘	…‘•Ìˆ€¼ø(€€€€€€€€€€€€€€ð½Q…‰±••±°ø(€€€€€€€€€€€€€€ñQ…‰±••±°øñ5•µ‰•É%Ñ•µÌ€éµ•µ‰•Èµ¥ô‰ÕÍ•È¹¥ˆ€é±½…¹Ìô‰µ•µ‰•É1½…¹Ìˆ€é±½…‘¥¹œô‰¥Ñ•µ1½…‘¥¹œˆ€é•ÉÉ½Èô‰¥Ñ•µÉÉ½Èˆ€¼øð½Q…‰±••±°ø(€€€€€€€€€€€€€€ñQ…‰±••±°ø(€€€€€€€€€€€€€€€€ñ‘¥Ø±…ÍÌô‰µ°µ…ÕÑ¼ˆøœœœ¤(€€€€Œ%Ñ•´±½…¹ÌÍ¥Ð…±½¹Í¥‘”¹…Ñ¥Ù”•Ñ…¥±Ì½5…¥¹Ñ•¹…¹”½‘¥Ðì‘•Ñ…¥±ÌÍ¡½ÜÍÑ…ÑÕÌ¸(€€€Á…Ñ €ô€Á…•Ì½¥Ñ•´½m¥‘t½¥¹‘•à¹ÙÕ”œ(€€€¥Ñ•µ}±½}™É½¹Ñ•¹ ¤(€€€É•Á±…”¡Á…Ñ °€œ€€€€€€€¥è€‰•‘¥Ðˆ°œ°€œ€€€€€€€¥è€‰±½…¹Ìˆ°¹…µ”è€‰1½…¹Ì€˜É•ÑÕÉ¸¹½Ñ•Ìˆ°Ñ¼è€½¥Ñ•´¼‘í¥Ñ•µ%¹Ù…±Õ•ô½±½…¹Í€±q¸€€€€€ô±q¸€€€€€íq¸€€€€€€€¥è€‰•‘¥Ðˆ°œ¤(€€€É•Á±…”¡Á…Ñ °€íì€‘Ð¡Ñ…ˆ¹¹…µ”¤õôœ°€íìÑ…ˆ¹¥€ôôô€‰±½…¹Ìˆ€üÑ…ˆ¹¹…µ”€è€‘Ð¡Ñ…ˆ¹¹…µ”¤õôœ¤(€€€É•Á±…”¡Á…Ñ °€œé¥ô‰¥Ñ•´¹…ÍÍ•Ñ%‰q¸€€€€€€€€€€€€€€€ÑåÁ”ô‰…ÍÍ•Ðˆœ°€œé¥ô‰¥Ñ•´¹…ÍÍ•Ñ%‰q¸€€€€€€€€€€€€€€€€é•¹Ñ¥Ñäµ¥ô‰¥Ñ•´¹¥‰q¸€€€€€€€€€€€€€€€ÑåÁ”ô‰…ÍÍ•Ðˆœ¤(€€€É•Á±…”¡Á…Ñ °€œñ9ÕáÑA…”€é¥Ñ•´ô‰¥Ñ•´ˆ€éÁ…”µ­•äô‰¥Ñ•µ%ˆ€¼øœ°€œñ9ÕáÑA…”€é¥Ñ•´ô‰¥Ñ•´ˆ€éÁ…”µ­•äô‰¥Ñ•µ%ˆ€¼ùq¸€€€€€€€€ñ%Ñ•µ1½…¹ÌØµ¥˜ôˆ…¡…Í9•ÍÑ•ˆ€é¥Ñ•´µ¥ô‰¥Ñ•µ%ˆ½µÁ…Ð€¼øœ¤(€€€€ŒáÑ•¹Ñ¡”•á¥ÍÑ¥¹œ±…‰•°‘¥…±½œì‰É½ÝÍ•ÈÁÉ¥¹Ñ¥¹œÉ•µ…¥¹Ì¹…Ñ¥Ù”¸(€€€Á…Ñ €ô€½µÁ½¹•¹ÑÌ½±½‰…°½1…‰•±5…­•È¹ÙÕ”œ(€€€É•Á±…”¡Á…Ñ °€œ€¥µÁ½ÉÐA…•EI½‘”œ°€œ€¥µÁ½ÉÐA¥AÉ¥¹Ð™É½´€‰ ½½µÁ½¹•¹ÑÌ½]½É­Í¡½À½A¥AÉ¥¹Ð¹ÙÕ”ˆíq¸€¥µÁ½ÉÐA…•EI½‘”œ¤(€€€É•Á±…”¡Á…Ñ °€œ€€€¥èÍÑÉ¥¹œìœ°€œ€€€¥èÍÑÉ¥¹œíq¸€€€•¹Ñ¥Ñå%üèÍÑÉ¥¹œìœ¤(€€€É•Á±…”¡Á…Ñ °€œ€€€€€€€€ñ¥µœ€éÍÉŒô‰•Ñ1…‰•±UÉ°¡™…±Í”¤ˆ€¼øœ°€œñ¥µœ€éÍÉŒô‰•Ñ1…‰•±UÉ°¡™…±Í”¤ˆ…±Ðô‰!½µ•‰½à±…‰•°ÁÉ•Ù¥•Üˆ€¼ùq¸€€€€€€€€ñA¥AÉ¥¹Ð€é¥ô‰¥ˆ€é•¹Ñ¥Ñäµ¥ô‰•¹Ñ¥Ñå%ˆ€¼øœ¤(€€€É•Á±…”¡Á…Ñ °€œñ	ÕÑÑ½¸Í¥é”ô‰¥½¸ˆ±¥¬ô‰½Á•¹¥…±½œ¡¥…±½%¹AÉ¥¹Ñ1…‰•°¤ˆøœ°€œñ	ÕÑÑ½¸Í¥é”ô‰¥½¸ˆ€é…É¥„µ±…‰•°ôˆ‘Ð¡p½µÁ½¹•¹ÑÌ¹±½‰…°¹±…‰•±}µ…­•È¹‰É½ÝÍ•É}ÁÉ¥¹Ñpœ¤ˆ±¥¬ô‰½Á•¹¥…±½œ¡¥…±½%¹AÉ¥¹Ñ1…‰•°¤ˆøœ¤(€€€€Œ5…¹…”¹…Ñ¥Ù”Á•½Á±”‰•Í¥‘”‰…‘•Ì…¹ÕÍÑ½‘ä°Ý¥Ñ ½±±•Ñ¥½¸µ½Ý¹•È…•ÍÌ¸(€€€½¹ÑÉ…Ðõ	U%1¼±¥ˆ½…Á¤½ÑåÁ•Ì½‘…Ñ„µ½¹ÑÉ…ÑÌ¹ÑÌœí‰½‘äõ½¹ÑÉ…Ð¹É•…‘}Ñ•áÐ ¤(€€€ÍÑ…ÉÐõ‰½‘ä¹¥¹‘•à •áÁ½ÉÐ¥¹Ñ•É™…”UÍ•ÉMÕµµ…Éäìœ¤í•¹õ‰½‘ä¹¥¹‘•à q¹ôœ±ÍÑ…ÉÐ¤(€€€‰½‘äõ‰½‘ålé•¹‘t¬q¸€…Ù…Ñ…ÈüèÍÑÉ¥¹œìœ­‰½‘åm•¹étí½¹ÑÉ…Ð¹ÝÉ¥Ñ•}Ñ•áÐ¡‰½‘ä¤(€€€Á…Ñ ôÁ…•Ì½½±±•Ñ¥½¸½¥¹‘•à½µ•µ‰•ÉÌ¹ÙÕ”œíÑ…É•Ðõ	U%1½Á…Ñ í‰½‘äõÑ…É•Ð¹É•…‘}Ñ•áÐ ¤(€€€‰½‘äõ‰½‘ä¹É•Á±…” œ€¥µÁ½ÉÐ5•µ‰•ÉÙ…Ñ…È™É½´œ°€œ€¥µÁ½ÉÐUÍ•É5…¹…•È™É½´€‰ ½½µÁ½¹•¹ÑÌ½]½É­Í¡½À½UÍ•É5…¹…•È¹ÙÕ”ˆíq¸€¥µÁ½ÉÐ5•µ‰•ÉÙ…Ñ…È™É½´œ¤(€€€‰½‘äõ‰½‘ä¹É•Á±…” œ€½¹ÍÐÝ½É­Í¡½À€ôÕÍ•]½É­Í¡½À ¤ìœ°€œ€½¹ÍÐÝ½É­Í¡½À€ôÕÍ•]½É­Í¡½À ¤íq¸€½¹ÍÐÕÍ•É‘µ¥¸€ôÉ•˜¡™…±Í”¤°ÕÍ•É5…¹…•È€ôÉ•˜ñ%¹ÍÑ…¹•QåÁ”ñÑåÁ•½˜UÍ•É5…¹…•Èøð¹Õ±°ø¡¹Õ±°¤ìœ¤(€€€‰½‘äõ‰½‘ä¹É•Á±…” ½¹ÍÐm‰…‘•Ì°Á•½Á±•t€ô…Ý…¥ÐAÉ½µ¥Í”¹…±°¡mÝ½É­Í¡½À¹É•ÅÕ•ÍÐñ…¹åmtø ‰‰…‘•Ìˆ¤°Ý½É­Í¡½À¹É•ÅÕ•ÍÐñ…¹åmtø ‰Á•½Á±”ˆ¥t¤ìœ°½¹ÍÐm‰…‘•Ì°Á•½Á±”°…‘µ¥¹¥ÍÑÉ…Ñ¥½¹t€ô…Ý…¥ÐAÉ½µ¥Í”¹…±°¡mÝ½É­Í¡½À¹É•ÅÕ•ÍÐñ…¹åmtø ‰‰…‘•Ìˆ¤°Ý½É­Í¡½À¹É•ÅÕ•ÍÐñ…¹åmtø ‰Á•½Á±”ˆ¤°Ý½É­Í¡½À¹É•ÅÕ•ÍÐñì…¹5…¹…”è‰½½±•…¸ôø ‰ÕÍ•ÉÌ½…‘µ¥¹¥ÍÑÉ…Ñ¥½¸ˆ¥t¤ìœ¤(€€€‰½‘äõ‰½‘ä¹É•Á±…” ‰…‘•I½ÝÌ¹Ù…±Õ”€ô‰…‘•ÌìÁ•½Á±•I½ÝÌ¹Ù…±Õ”€ôÁ•½Á±”ìœ°€‰…‘•I½ÝÌ¹Ù…±Õ”€ô‰…‘•ÌìÁ•½Á±•I½ÝÌ¹Ù…±Õ”€ôÁ•½Á±”ìÕÍ•É‘µ¥¸¹Ù…±Õ”€ô…‘µ¥¹¥ÍÑÉ…Ñ¥½¸¹…¹5…¹…”ìœ¤(€€€‰½‘äõ‰½‘ä¹É•Á±…” ¥˜€ …Ý½É­Í¡½À¹µ…¹…•È¹Ù…±Õ”¤É•ÑÕÉ¸ìœ°€¥˜€ …Ý½É­Í¡½À¹µ…¹…•È¹Ù…±Õ”¤ìÕÍ•É‘µ¥¸¹Ù…±Õ”€ô™…±Í”ìÉ•ÑÕÉ¸ìôœ¤(€€€‰½‘äõ‰½‘ä¹É•Á±…” Ý…Ñ ¡Í•±•Ñ•‘%°€ ¤€ôøìµ•µ‰•É1½…¹Ì¹Ù…±Õ”€ô¹Õ±°ìœ°€Ý…Ñ ¡Í•±•Ñ•‘%°€ ¤€ôøìÕÍ•É‘µ¥¸¹Ù…±Õ”€ô™…±Í”ìµ•µ‰•É1½…¹Ì¹Ù…±Õ”€ô¹Õ±°ìœ¤(€€€‰½‘äõ‰½‘ä¹É•Á±…” œ€€€€€€ñ	ÕÑÑ½¸Ù…É¥…¹Ðô‰½ÕÑ±¥¹”ˆÍ¥é”ô‰Í´ˆ€é‘¥Í…‰±•ô‰±½…‘¥¹œñð¥Ñ•µ1½…‘¥¹œˆœ°€œ€€€€€€ñ	ÕÑÑ½¸Øµ¥˜ô‰ÕÍ•É‘µ¥¸ˆÙ…É¥…¹Ðô‰½ÕÑ±¥¹”ˆÍ¥é”ô‰Í´ˆ±¥¬ô‰ÕÍ•É5…¹…•Èü¹Í¡½Ü ¤ˆù5…¹…”ÕÍ•ÉÌð½	ÕÑÑ½¸ùq¸€€€€€€ñ	ÕÑÑ½¸Ù…É¥…¹Ðô‰½ÕÑ±¥¹”ˆÍ¥é”ô‰Í´ˆ€é‘¥Í…‰±•ô‰±½…‘¥¹œñð¥Ñ•µ1½…‘¥¹œˆœ¤(€€€‰½‘äõ‰½‘ä¹É•Á±…” œ€€€€ñÀØµ¥˜ô‰¥Ñ•µÉÉ½Èˆœ°€œ€€€€ñUÍ•É5…¹…•ÈØµ¥˜ô‰ÕÍ•É‘µ¥¸ˆÉ•˜ô‰ÕÍ•É5…¹…•Èˆ€éµ•µ‰•ÉÌô‰µ•µ‰•ÉÌˆ¡…¹•ô‰É•™É•Í¡5•µ‰•ÉÌˆ€¼ùq¸€€€€ñÀØµ¥˜ô‰¥Ñ•µÉÉ½Èˆœ¤(€€€‰½‘äõ‰½‘ä¹É•Á±…” œñ5•µ‰•ÉÙ…Ñ…È€éµ•µ‰•Èµ¥ô‰ÕÍ•È¹¥ˆ€é¹…µ”ô‰ÕÍ•È¹¹…µ”ˆ€¼øñÍÁ…¸±…ÍÌô‰™½¹Ðµµ•‘¥Õ´ˆùíìÕÍ•È¹¹…µ”õôð½ÍÁ…¸øœ°€œñ5•µ‰•ÉÙ…Ñ…È€éµ•µ‰•Èµ¥ô‰ÕÍ•È¹¥ˆ€é¹…µ”ô‰ÕÍ•È¹¹…µ”ˆ€éÁ¥ÑÕÉ”ô‰ÕÍ•È¹…Ù…Ñ…Èˆ€¼øñÍÁ…¸øñÍÁ…¸±…ÍÌô‰‰±½¬™½¹Ðµµ•‘¥Õ´ˆùíìÕÍ•È¹¹…µ”õôð½ÍÁ…¸øñÍÁ…¸±…ÍÌô‰‰±½¬Ñ•áÐµáÌÑ•áÐµµÕÑ•µ™½É•É½Õ¹ˆù%íìÕÍ•È¹¥¹Í±¥” À°à¤õôð½ÍÁ…¸øð½ÍÁ…¸øœ¤(€€€‰½‘äõ‰½‘ä¹É•Á±…” œñQ…‰±••±°ùíìÕÍ•È¹•µ…¥°õôð½Q…‰±••±°øœ°€œñQ…‰±••±°ùíìÕÍ•È¹•µ…¥°ñð€‹ŠPˆõôð½Q…‰±••±°øœ¤(€€€‰½‘äõ‰½‘ä¹É•Á±…” œ€€€€€€€€€€€€€€€€ñ‘¥Ø±…ÍÌô‰µ°µ…ÕÑ¼ˆøœ°œ€€€€€€€€€€€€€€€€ñ‘¥Ø±…ÍÌô‰µ°µ…ÕÑ¼™±•à¥Ñ•µÌµ•¹Ñ•È©ÕÍÑ¥™äµ•¹…À´Èˆùq¸€€€€€€€€€€€€€€€€€€ñ	ÕÑÑ½¸Øµ¥˜ô‰ÕÍ•É‘µ¥¸ˆÙ…É¥…¹Ðô‰½ÕÑ±¥¹”ˆÍ¥é”ô‰Í´ˆ€é…É¥„µ±…‰•°ô‰p5…¹…”ÁÉ½™¥±”èpœ€¬ÕÍ•È¹¹…µ”ˆ±¥¬ô‰ÕÍ•É5…¹…•Èü¹Í¡½Ü¡ÕÍ•È¤ˆù5…¹…”ÁÉ½™¥±”ð½	ÕÑÑ½¸øœ¤(€€€‰½‘äõ‰½‘ä¹É•Á±…” œé‘¥Í…‰±•ô‰É•µ½Ù¥¹mÕÍ•È¹¥‘tñð€¡¥Í1…ÍÑ5•µ‰•È€˜˜ÕÍ•È¹¥€ôôôÕÉÉ•¹ÑUÍ•É%¤ˆœ°€œé‘¥Í…‰±•ôˆ…ÕÍ•É‘µ¥¸ñðÉ•µ½Ù¥¹mÕÍ•È¹¥‘tñðÕÍ•È¹¥€ôôôÕÉÉ•¹ÑUÍ•É%ñð€„…Á•½Á±•I½ÝÌ¹™¥¹¡É½Ü€ôøÉ½Ü¹¥€ôôôÕÍ•È¹¥¤ü¹ÁÉ½Ñ•Ñ•‘}½Ý¹•Èˆœ¤(€€€‰½‘äõ‰½‘ä¹É•Á±…” œ€½¹ÍÐ±½…‘¥¹œ€ôÉ•˜¡ÑÉÕ”¤ìœ°€œ€±•Ðµ•µ‰•ÉI•Ù¥Í¥½¸€ô€Àíq¸€½¹ÍÐ±½…‘¥¹œ€ôÉ•˜¡ÑÉÕ”¤ìœ¤(€€€‰½‘äõ‰½‘ä¹É•Á±…” ½¹ÍÐ±½…‘5•µ‰•ÉÌ€ô…Íå¹Œ€ ¤€ôøìœ°€½¹ÍÐ±½…‘5•µ‰•ÉÌ€ô…Íå¹Œ€ ¤€ôøíq¸€€€½¹ÍÐÉ•Ù¥Í¥½¸€ô€¬­µ•µ‰•ÉI•Ù¥Í¥½¸ìœ¤(€€€‰½‘äõ‰½‘ä¹É•Á±…” ½¹ÍÐÉ•Ì€ô…Ý…¥Ð…Á¤¹É½ÕÀ¹•Ñ5•µ‰•ÉÌ ¤ìœ°€½¹ÍÐÉ•Ì€ô…Ý…¥Ð…Á¤¹É½ÕÀ¹•Ñ5•µ‰•ÉÌ ¤íq¸€€€€€¥˜€¡É•Ù¥Í¥½¸€„ôôµ•µ‰•ÉI•Ù¥Í¥½¸¤É•ÑÕÉ¸ìœ¤(€€€ÍÑ…ÉÐõ‰½‘ä¹¥¹‘•à œ€½¹ÍÐ±½…‘5•µ‰•ÉÌ€ô…Íå¹Œ€ ¤€ôøìœ¤í•¹õ‰½‘ä¹¥¹‘•à œ€½¹ÍÐ¡…¹‘±•I•µ½Ù”œ±ÍÑ…ÉÐ¤(€€€Á…ÉÐõ‰½‘åmÍÑ…ÉÐé•¹‘t¹É•Á±…” œ€€€ô…Ñ €¡”¤ìœ°œ€€€ô…Ñ €¡”¤íq¸€€€€€¥˜€¡É•Ù¥Í¥½¸€„ôôµ•µ‰•ÉI•Ù¥Í¥½¸¤É•ÑÕÉ¸ìœ¤¹É•Á±…” œ€€€€€±½…‘¥¹œ¹Ù…±Õ”€ô™…±Í”ìœ°€œ€€€€€¥˜€¡É•Ù¥Í¥½¸€ôôôµ•µ‰•ÉI•Ù¥Í¥½¸¤±½…‘¥¹œ¹Ù…±Õ”€ô™…±Í”ìœ¤(€€€‰½‘äõ‰½‘åléÍÑ…ÉÑt­Á…ÉÐ­‰½‘åm•¹ét(€€€‰½‘äõ‰½‘ä¹É•Á±…” Ý½É­Í¡½ÁI•Ù¥Í¥½¸¬¬ì¥Ñ•µI•Ù¥Í¥½¸¬¬ìœ°€µ•µ‰•ÉI•Ù¥Í¥½¸¬¬ìÝ½É­Í¡½ÁI•Ù¥Í¥½¸¬¬ì¥Ñ•µI•Ù¥Í¥½¸¬¬ìœ¤(€€€‰½‘äõ‰½‘ä¹É•Á±…” Ý…Ñ ¡Í•±•Ñ•‘%°€ ¤€ôøìÕÍ•É‘µ¥¸¹Ù…±Õ”€ô™…±Í”ìœ°€Ý…Ñ ¡mÍ•±•Ñ•‘%°€ ¤€ôø…ÕÑ ¹ÕÍ•Èü¹¥‘t°€ ¤€ôøìµ•µ‰•ÉÌ¹Ù…±Õ”€ômtìÕÍ•É‘µ¥¸¹Ù…±Õ”€ô™…±Í”ìœ¤(€€€Ñ…É•Ð¹ÝÉ¥Ñ•}Ñ•áÐ¡‰½‘ä¤(€€€¹•ÍÑ}™É½¹Ñ•¹ ¤(€€€‰É…¹‘}™É½¹Ñ•¹ ¤(()‘•˜ÉÕ¹}™É½¹Ñ•¹‘}½µµ…¹¡½µµ…¹°€¨°Ý°•¹Ø¤è(€€€ÁÉ½•ÍÌ€ôÍÕ‰ÁÉ½•ÍÌ¹A½Á•¸ (€€€€€€€½µµ…¹°(€€€€€€€ÝõÝ°(€€€€€€€•¹Øõ•¹Ø°(€€€€€€€ÍÑ‘½ÕÐõÍÕ‰ÁÉ½•ÍÌ¹A%A°(€€€€€€€ÍÑ‘•ÉÈõÍÕ‰ÁÉ½•ÍÌ¹A%A°(€€€€€€€Ñ•áÐõQÉÕ”°(€€€€€€€•¹½‘¥¹œô‰ÕÑ˜´àˆ°(€€€€€€€•ÉÉ½ÉÌô‰É•Á±…”ˆ°(€€€€¤((€€€‘•˜™½ÉÝ…É¡Í½ÕÉ”°‘•ÍÑ¥¹…Ñ¥½¸¤è(€€€€€€€ÑÉäè(€€€€€€€€€€€™½È±¥¹”¥¸Í½ÕÉ”è(€€€€€€€€€€€€€€€±¥¹”€ô™¥±Ñ•É}­¹½Ý¹}Ý…Í¥}Ý…É¹¥¹œ¡±¥¹”¤(€€€€€€€€€€€€€€€¥˜±¥¹”è(€€€€€€€€€€€€€€€€€€€‘•ÍÑ¥¹…Ñ¥½¸¹ÝÉ¥Ñ”¡±¥¹”¤(€€€€€€€€€€€€€€€€€€€‘•ÍÑ¥¹…Ñ¥½¸¹™±ÕÍ  ¤(€€€€€€€™¥¹…±±äè(€€€€€€€€€€€Í½ÕÉ”¹±½Í” ¤((€€€½ÕÑÁÕÑ}Ñ¡É•…‘Ì€ôl(€€€€€€€Ñ¡É•…‘¥¹œ¹Q¡É•…¡Ñ…É•Ðõ™½ÉÝ…É°…ÉÌô¡ÁÉ½•ÍÌ¹ÍÑ‘½ÕÐ°ÍåÌ¹ÍÑ‘½ÕÐ¤¤°(€€€€€€€Ñ¡É•…‘¥¹œ¹Q¡É•…¡Ñ…É•Ðõ™½ÉÝ…É°…ÉÌô¡ÁÉ½•ÍÌ¹ÍÑ‘•ÉÈ°ÍåÌ¹ÍÑ‘•ÉÈ¤¤°(€€€t(€€€™½ÈÑ¡É•…¥¸½ÕÑÁÕÑ}Ñ¡É•…‘Ìè(€€€€€€€Ñ¡É•…¹ÍÑ…ÉÐ ¤(€€€É•ÑÕÉ¹½‘”€ôÁÉ½•ÍÌ¹Ý…¥Ð ¤(€€€™½ÈÑ¡É•…¥¸½ÕÑÁÕÑ}Ñ¡É•…‘Ìè(€€€€€€€Ñ¡É•…¹©½¥¸ ¤(€€€¥˜É•ÑÕÉ¹½‘”è(€€€€€€€ÁÉ¥¹Ð¡˜É½¹Ñ•¹½µµ…¹™…¥±•Ý¥Ñ •á¥Ð½‘”íÉ•ÑÕÉ¹½‘•ô¸œ°™¥±”õÍåÌ¹ÍÑ‘•ÉÈ°™±ÕÍ õQÉÕ”¤(€€€€€€€É…¥Í”ÍÕ‰ÁÉ½•ÍÌ¹…±±•‘AÉ½•ÍÍÉÉ½È¡É•ÑÕÉ¹½‘”°½µµ…¹¤(€€€É•ÑÕÉ¸ÍÕ‰ÁÉ½•ÍÌ¹½µÁ±•Ñ•‘AÉ½•ÍÌ¡½µµ…¹°É•ÑÕÉ¹½‘”¤((()‘•˜‰Õ¥± ¤è(€€€±½‰…°	U%1°Q==1!%9}I==P°UAMQI5}I==P(€€€Á…ÉÍ•È€ô…ÉÁ…ÉÍ”¹ÉÕµ•¹ÑA…ÉÍ•È ¤(€€€Á…ÉÍ•È¹…‘‘}…ÉÕµ•¹Ð œ´µÑ½½±¡…¥¸µÉ½½Ðœ°ÑåÁ”õÁ…Ñ¡±¥ˆ¹A…Ñ °‘•™…Õ±ÐõQ==1!%9}I==P¤(€€€Á…ÉÍ•È¹…‘‘}…ÉÕµ•¹Ð œ´µÕÁÍÑÉ•…´µÉ½½Ðœ°ÑåÁ”õÁ…Ñ¡±¥ˆ¹A…Ñ °‘•™…Õ±ÐõUAMQI5}I==P¤(€€€Á…ÉÍ•È¹…‘‘}…ÉÕµ•¹Ð œ´µ‰Õ¥±µÉ½½Ðœ°ÑåÁ”õÁ…Ñ¡±¥ˆ¹A…Ñ °¡•±ÀôÕÍ”„¹•Ü½È•µÁÑä™É½¹Ñ•¹Ý½É­ÍÁ…”™½È‘¥ÍÁ½Í…‰±”Ù…±¥‘…Ñ¥½¸œ¤(€€€Á…ÉÍ•È¹…‘‘}…ÉÕµ•¹Ð œ´µÁÉ•Á…É”œ°…Ñ¥½¸ôÍÑ½É•}ÑÉÕ”œ°¡•±ÀôÁÉ•Á…É”‘•Á•¹‘•¹¥•ÌÝ¥Ñ¡½ÕÐÉÕ¹¹¥¹œÑåÁ•¡•¬½È‰Õ¥±œ¤(€€€…ÉÌ€ôÁ…ÉÍ•È¹Á…ÉÍ•}…ÉÌ ¤(€€€¥˜…ÉÌ¹‰Õ¥±‘}É½½Ð¥Ì¹½Ð9½¹”…¹…ÉÌ¹‰Õ¥±‘}É½½Ð¹•á¥ÍÑÌ ¤…¹€ (€€€€€€€¹½Ð…ÉÌ¹‰Õ¥±‘}É½½Ð¹¥Í}‘¥È ¤½È…¹ä¡…ÉÌ¹‰Õ¥±‘}É½½Ð¹¥Ñ•É‘¥È ¤¤(€€€€¤è(€€€€€€€Á…ÉÍ•È¹•ÉÉ½È œ´µ‰Õ¥±µÉ½½ÐµÕÍÐ‰”•µÁÑäÍ¼ÍÑ…±”™¥±•Ì…¹¹½Ð½¹Ñ…µ¥¹…Ñ”„‘¥ÍÁ½Í…‰±”‰Õ¥±œ¤(€€€¥˜…ÉÌ¹‰Õ¥±‘}É½½Ð¥Ì¹½Ð9½¹”è(€€€€€€€	U%1€ô…ÉÌ¹‰Õ¥±‘}É½½Ð¹É•Í½±Ù” ¤(€€€Q==1!%9}I==P°UAMQI5}I==P€ô…ÉÌ¹Ñ½½±¡…¥¹}É½½Ð¹É•Í½±Ù” ¤°…ÉÌ¹ÕÁÍÑÉ•…µ}É½½Ð¹É•Í½±Ù” ¤(€€€¹½‘”€ôÁ…Ñ¡±¥ˆ¹A…Ñ  ¡Q==1!%9}I==P¼¹½‘”µÁ…Ñ ¹ÑáÐœ¤¹É•…‘}Ñ•áÐ ¤¹ÍÑÉ¥À ¤¤(€€€•¹Ø€ô‘¥Ð¡½Ì¹•¹Ù¥É½¸°AQ õÍÑÈ¡¹½‘”¼‰¥¸œ¤­½Ì¹Á…Ñ¡Í•À­½Ì¹•¹Ù¥É½¹lAQ t¤(€€€Á¹Á´€ôÉ•Í½±Ù•}Á¹Áµ}±…Õ¹¡•È¡Q==1!%9}I==P¤(€€€ÁÉ¥¹Ð AÉ•Á…É¥¹œ™É½¹Ñ•¹Í½ÕÉ”Ý½É­ÍÁ…”¸¸¸œ°™±ÕÍ õQÉÕ”¤(€€€ÁÉ•Á…É” ¤(€€€¥˜…ÉÌ¹‰Õ¥±‘}É½½Ð¥Ì¹½Ð9½¹”è(€€€€€€€ÁÉ¥¹Ð %¹ÍÑ…±±¥¹œ™É½¹Ñ•¹‘•Á•¹‘•¹¥•Ì¥¸‘¥ÍÁ½Í…‰±”Ý½É­ÍÁ…”¸¸¸œ°™±ÕÍ õQÉÕ”¤(€€€€€€€ÉÕ¹}™É½¹Ñ•¹‘}½µµ…¹¡mÍÑÈ¡Á¹Á´¤°€¥¹ÍÑ…±°œ°€œ´µ™É½é•¸µ±½­™¥±”œ°€œ´µ¥¹½É”µÍÉ¥ÁÑÌt°Ýõ	U%1°•¹Øõ•¹Ø¤(€€€€€€€ÁÉ¥¹Ð É½¹Ñ•¹‘•Á•¹‘•¹¥•Ì¥¹ÍÑ…±±•¸œ°™±ÕÍ õQÉÕ”¤(€€€€Œ½áŒµÁ…ÉÍ•È€À¸ÜÈÌ¹…Ñ¥Ù”I4‰¥¹‘¥¹œÉ•ÅÕ¥É•Ì¥¹ÍÑÉÕÑ¥½¹Ì…‰Í•¹Ð½¸Ñ¡¥ÌA¤¸(€€€€ŒUÍ”Ñ¡”Í…µ”Ù•ÉÍ¥½¸ÌÕÁÍÑÉ•…´]M$‰¥¹‘¥¹œ½¹±ä™½ÈÑ¡¥Ì‰Õ¥±‘•Á•¹‘•¹ä¸(€€€Ý…Í¤€ôQ==1!%9}I==P¼½áŒµÝ…Í¤½¹½‘•}µ½‘Õ±•Ì½½áŒµÁ…ÉÍ•È½‰¥¹‘¥¹œµÝ…Í´ÌÈµÝ…Í¤œ(€€€¥˜Ý…Í¤¹•á¥ÍÑÌ ¤è(€€€€€€€‰¥¹‘¥¹œ€ô	U%1¼¹½‘•}µ½‘Õ±•Ì¼¹Á¹Á´½½áŒµÁ…ÉÍ•É À¸ÜÈ¸Ì½¹½‘•}µ½‘Õ±•Ì½½áŒµÁ…ÉÍ•È½‰¥¹‘¥¹Ì¹©Ìœ(€€€€€€€Í½ÕÉ”€ô‰¥¹‘¥¹œ¹É•…‘}Ñ•áÐ ¤(€€€€€€€…¹¡½È€ô€¹…Ñ¥Ù•	¥¹‘¥¹œ€ôÉ•ÅÕ¥É•9…Ñ¥Ù” ¤œ(€€€€€€€¥˜…¹¡½È¥¸Í½ÕÉ”è(€€€€€€€€€€€‰¥¹‘¥¹œ¹ÝÉ¥Ñ•}Ñ•áÐ¡Í½ÕÉ”¹É•Á±…”¡…¹¡½È°€¹…Ñ¥Ù•	¥¹‘¥¹œ€ôÉ•ÅÕ¥É” œ­É•ÁÈ¡ÍÑÈ¡Ý…Í¤¤¤¬œ¤œ¤¤(€€€ÁÉ¥¹Ð AÉ•Á…É¥¹œ9ÕáÐ½µÁ½¹•¹ÑÌ¸¸¸œ°™±ÕÍ õQÉÕ”¤(€€€ÉÕ¹}™É½¹Ñ•¹‘}½µµ…¹¡mÍÑÈ¡Á¹Á´¤°€•á•Œœ°€¹ÕáÐœ°€ÁÉ•Á…É”t°Ýõ	U%1°•¹Øõ•¹Ø¤(€€€ÁÉ¥¹Ð 9ÕáÐÁÉ•Á…É…Ñ¥½¸½µÁ±•Ñ”¸œ°™±ÕÍ õQÉÕ”¤(€€€¥˜¹½Ð…ÉÌ¹ÁÉ•Á…É”è(€€€€€€€ÁÉ¥¹Ð IÕ¹¹¥¹œ™É½¹Ñ•¹ÑåÁ•¡•¬¸¸¸œ°™±ÕÍ õQÉÕ”¤(€€€€€€€É•ÍÕ±Ð€ôÍÕ‰ÁÉ½•ÍÌ¹ÉÕ¸¡mÍÑÈ¡Á¹Á´¤°€•á•Œœ°€¹Õá¤œ°€ÑåÁ•¡•¬t°Ýõ	U%1°•¹Øõ•¹Ø°…ÁÑÕÉ•}½ÕÑÁÕÐõQÉÕ”°Ñ•áÐõQÉÕ”¤(€€€€€€€ÑåÁ•¡•­}½ÕÑÁÕÐ€ôÉ•ÍÕ±Ð¹ÍÑ‘½ÕÐ€¬É•ÍÕ±Ð¹ÍÑ‘•ÉÈ(€€€€€€€ÑåÁ•¡•­}±½œ€ô	U%1¼¡½µ•‰½àµÕ¤µÑåÁ•¡•¬¹±½œœ¥˜…ÉÌ¹‰Õ¥±‘}É½½Ð¥Ì¹½Ð9½¹”•±Í”I==P¼Ý½É¬½¡½µ•‰½àµÕ¤µÑåÁ•¡•¬¹±½œœ(€€€€€€€ÑåÁ•¡•­}±½œ¹ÝÉ¥Ñ•}Ñ•áÐ¡ÑåÁ•¡•­}½ÕÑÁÕÐ¤(€€€€€€€¥˜¡…Í}™É½¹Ñ•¹‘}Ñ½½±}™…¥±ÕÉ”¡ÑåÁ•¡•­}½ÕÑÁÕÐ¤è(€€€€€€€€€€€ÁÉ¥¹Ð¡ÑåÁ•¡•­}½ÕÑÁÕÐ¤(€€€€€€€€€€€ÁÉ¥¹Ð¡˜É½¹Ñ•¹ÑåÁ•¡•¬Ñ½½°™…¥±•Ý¥Ñ •á¥Ð½‘”íÉ•ÍÕ±Ð¹É•ÑÕÉ¹½‘•ô¸œ°™¥±”õÍåÌ¹ÍÑ‘•ÉÈ°™±ÕÍ õQÉÕ”¤(€€€€€€€€€€€É…¥Í”IÕ¹Ñ¥µ•ÉÉ½È É½¹Ñ•¹ÑåÁ•¡•¬½Õ±¹½Ð‰”¥¹Ù½­•ÍÕ•ÍÍ™Õ±±ä¸œ¤(€€€€€€€‘¥…¹½ÍÑ¥Ì€ôm±¥ÍÐ¡µ…Ñ ¹É½ÕÁÌ ¤¤™½Èµ…Ñ ¥¸É”¹™¥¹‘¥Ñ•È¡Èx ¸¬ü¥p¡q¬±q­p¤è•ÉÉ½È€¡QMq¬¤è€ ¸¨¤œ°ÑåÁ•¡•­}½ÕÑÁÕÐ°É”¹4¥t(€€€€€€€¥˜É•ÍÕ±Ð¹É•ÑÕÉ¹½‘”è(€€€€€€€€€€€‰…Í•±¥¹”€ô©Í½¸¹±½…‘Ì ¡I==P¼¡½µ•‰½àµÕ¤½ÕÁÍÑÉ•…´µÑåÁ•¡•¬¹©Í½¸œ¤¹É•…‘}Ñ•áÐ ¤¤(€€€€€€€€€€€Á¥¸€ôÍ½ÕÉ•}½µµ¥Ð¡UAMQI5}I==P¼ÕÁÍÑÉ•…´½¡½µ•‰½àœ¤(€€€€€€€€€€€¥˜É•ÍÕ±Ð¹É•ÑÕÉ¹½‘”€„ô€Ä½È¹½Ð¥Í}½¹±å}­¹½Ý¹}ÕÁÍÑÉ•…µ}ÑåÁ•¡•­}™…¥±ÕÉ”¡ÑåÁ•¡•­}½ÕÑÁÕÐ°‰…Í•±¥¹”°Á¥¸¤è(€€€€€€€€€€€€€€€ÁÉ¥¹Ð¡ÑåÁ•¡•­}½ÕÑÁÕÐ¤(€€€€€€€€€€€€€€€ÁÉ¥¹Ð¡˜É½¹Ñ•¹ÑåÁ•¡•¬™…¥±•Ý¥Ñ •á¥Ð½‘”íÉ•ÍÕ±Ð¹É•ÑÕÉ¹½‘•ô¸œ°™¥±”õÍåÌ¹ÍÑ‘•ÉÈ°™±ÕÍ õQÉÕ”¤(€€€€€€€€€€€€€€€É…¥Í”IÕ¹Ñ¥µ•ÉÉ½È É½¹Ñ•¹ÑåÁ•¡•¬¥¹ÑÉ½‘Õ••ÉÉ½ÉÌ½È¥ÑÌÕÁÍÑÉ•…´‰…Í•±¥¹”¡…¹•¸œ¤(€€€€€€€€€€€ÁÉ¥¹Ð¡˜QåÁ•¡•¬è¹¼…‘‘•‘¥…¹½ÍÑ¥Ììí±•¸¡‘¥…¹½ÍÑ¥Ì¥ôÁÉ”µ•á¥ÍÑ¥¹œÕÁÍÑÉ•…´‘¥…¹½ÍÑ¥Ì¸œ°™±ÕÍ õQÉÕ”¤(€€€€€€€•±Í”è(€€€€€€€€€€€ÁÉ¥¹Ð É½¹Ñ•¹ÑåÁ•¡•¬Á…ÍÍ•¸œ°™±ÕÍ õQÉÕ”¤(€€€€€€€ÁÉ¥¹Ð 	Õ¥±‘¥¹œ™É½¹Ñ•¹¸¸¸œ°™±ÕÍ õQÉÕ”¤(€€€€€€€ÉÕ¹}™É½¹Ñ•¹‘}½µµ…¹¡mÍÑÈ¡Á¹Á´¤°€ÉÕ¸œ°€‰Õ¥±t°Ýõ	U%1°•¹Øõ•¹Ø¤(€€€€€€€ÁÉ¥¹Ð É½¹Ñ•¹‰Õ¥±½µÁ±•Ñ•ÍÕ•ÍÍ™Õ±±ä¸œ°™±ÕÍ õQÉÕ”¤()¥˜}}¹…µ•}|€ôô€}}µ…¥¹}|œè(€€€‰Õ¥± ¤(