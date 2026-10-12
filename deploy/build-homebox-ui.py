#!/usr/bin/env python3
"""Build a native Homebox frontend overlay without modifying the upstream checkout.

Install the pinned frontend dependencies in work/homebox-ui-build first. Output
stays staged until a verified release is selected by work/homebox-ui-current.
"""
import argparse
import os
import json
import pathlib
import shutil
import subprocess
import sys
import re
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
BUILD = ROOT / 'work/homebox-ui-build'
TOOLCHAIN_ROOT = ROOT / 'work/toolchains'
UPSTREAM_ROOT = ROOT


def replace(path, old, new):
    target = BUILD / path
    source = target.read_text()
    if source.count(old) != 1:
        raise RuntimeError(f'Upstream changed: expected one patch anchor in {path}')
    target.write_text(source.replace(old, new))


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
        path.write_text(json.dumps(values(json.loads(path.read_text())), ensure_ascii=False, indent=2)+'\n')
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
    replace(path, details_anchor, '          </DetailsSection>\n        </BaseCard>\n\n        <WorkshopItemLog v-if="!hasNested" :item-id="itemId" />\n\n        <!-- anything in this is not rendered if on another page -->')


def nest_frontend():
    replace('lib/api/classes/items.ts', '  orderBy?: string;', '  orderBy?: string;\n  isLocation?: boolean;')
    replace('components/ui/dialog-provider/utils.ts', '[DialogID.CreateEntity]: { baseType: "item"; product?: BarcodeProduct; subItem?: true } | { baseType: "location" };', '[DialogID.CreateEntity]: ({ baseType: "item"; product?: BarcodeProduct; subItem?: true } | { baseType: "location" }) & { parentId?: string };')
    path = 'components/Entity/CreateModal.vue'
    replace(path, ':entity-types="subItemCreate ? entityTypes.filter(t => !t.isLocation) : entityTypes"', ':entity-types="entityTypes"')
    target = BUILD/path
    text = target.read_text()
    start = text.index('      <ItemSelector\n'); end = text.index('      <FormTextField', start)
    text = text[:start]+text[end:]
    text = text.replace('    EntityCreate,', '    EntityCreate,\n    EntitySummary,')
    text = text.replace('const found = locations.value.find(l => l.id === data.defaultLocation!.id);', 'const { data: found } = await api.items.get(data.defaultLocation.id);')
    text = text.replace('location: locations.value && locations.value.length > 0 ? locations.value[0] : ({} as EntityOut)', 'location: null as EntitySummary | null')
    text = text.replace('      form.parentId = null;', '      form.parentId = null;\n      form.location = null;')
    text = text.replace('            parent.value = data;', '            parentItemLocationId = data.id;')
    start = text.index('          if (data.parent) {'); end = text.index('\n        }', start)
    text = text[:start]+text[end:]
    start = text.index('      const locId = locationId.value ? locationId.value : parentItemLocationId;'); end = text.index('\n      if (tagId.value)', start)
    text = text[:start]+'''      const locId = params.parentId || locationId.value || parentItemLocationId;
      if (locId) {
        const { data } = await api.items.get(String(locId));
        if (data) form.location = data;
      }
'''+text[end:]
    start = text.index('    // Items must live somewhere'); end = text.index('    if (loading.value)', start)
    text = text[:start]+text[end:]
    text = text.replace('parentId: form.location.id as string', 'parentId: form.location?.id || null').replace('parentId: form.parentId || (form.location.id as string)', 'parentId: form.location?.id || null')
    target.write_text(text)
    path = 'pages/item/[id]/index/edit.vue'; target=BUILD/path; text=target.read_text()
    start=text.index('    if (data.parent && data.parent.entityType'); end=text.index('\n    return data;',start)
    text=text[:start]+text[end:]
    guard='''    if (!item.value.parent?.id && !parent.value?.id) {
      toast.error(t("items.toast.failed_save_no_location"));
      return;
    }
'''
    assert text.count(guard)==2; text=text.replace(guard,'')
    text=text.replace('parent.value?.id || item.value.parent?.id || null','item.value.parent?.id || null')
    text=text.replace('<LocationSelector v-model="item.parent" @update:model-value="informAboutDesyncingLocationFromParent()" />','<LocationSelector v-model="item.parent" :current-location="item" />')
    start=text.index('            <ItemSelector\n'); end=text.index('            <TagSelector',start)
    text=text[:start]+'            <p class="text-sm text-muted-foreground">Contents stay inside this item when it moves.</p>\n'+text[end:]
    start=text.index('  async function maybeSyncWithParentLocation()');end=text.index('  onMounted(() => {',start)
    text=text[:start]+text[end:]
    text=text.replace('  const { query, results, isLoading, triggerSearch } = useItemSearch(api, { immediate: false });\n  const parent = ref();\n','')
    target.write_text(text)
    replace('pages/location/[id]/index/edit.vue', '<LocationSelector v-model="parent" label="Parent Location" :current-location="item" />', '<LocationSelector v-model="parent" :current-location="item" />')
    for path, model in [('pages/item/[id]/index.vue','item'),('pages/location/[id]/index/index.vue','location')]:
        replace(path, '  import LabelMaker from', '  import InsideActions from "@/components/Workshop/InsideActions.vue";\n  import LabelMaker from')
        replace(path, '            <div class="ml-auto mt-2 flex flex-wrap items-center justify-between gap-2">', '            <div class="ml-auto mt-2 flex flex-wrap items-center justify-between gap-2">\n              <InsideActions :entity-id="'+model+'.id" :archived="'+model+'.archived" />')
    replace('pages/item/[id]/index.vue', '  import ItemViewSelectable from', '  import LocationCard from "@/components/Location/Card.vue";\n  import ItemViewSelectable from')
    replace('pages/item/[id]/index.vue', '<section v-if="items && items.length > 0" class="mt-6">', '<section v-if="item?.children?.length || (items && items.length > 0)" class="mt-6">')
    replace('pages/item/[id]/index.vue', '      <ItemViewSelectable :items="items" @refresh="refreshItemList" />', '''      <section v-if="item?.children?.length" class="mt-6">
        <h2 class="mb-3 text-xl font-semibold">Locations inside</h2>
        <div class="grid grid-cols-1 gap-2 sm:grid-cols-3"><LocationCard v-for="child in item.children" :key="child.id" :location="child" /></div>
      </section>
      <ItemViewSelectable v-if="items && items.length" :items="items || []" @refresh="refreshItemList" />''')

    path='lib/api/types/data-contracts.ts';target=BUILD/path;text=target.read_text();text=text.replace('export interface EntityPatch {','export interface EntityPatch {\n  clearParent?: boolean;')
    start=text.index('export interface EntityTemplateCreateItemRequest {');end=text.index('\n}',start)
    text=text[:start]+text[start:end].replace('parentId: string;','parentId: string | null;')+text[end:];target.write_text(text)
    replace('composables/use-barcode-detector.ts','api.items.getAll({ locations: [id] })','api.items.getAll({ parentIds: [id] })')
    path='components/Item/View/ItemChangeDetails.vue';target=BUILD/path;text=target.read_text()
    text=text.replace('item.location','item.parent').replace(']!.location',']!.parent')
    text=text.replace('      items.value = params.items;', '      items.value = params.items;\n      newLocation.value = null;')
    text=text.replace('!items.value.length || (enabled.changeLocation && !location)', '!items.value.length')
    text=text.replace('patch.parentId = location!.id;', 'if (location) patch.parentId = location.id; else patch.clearParent = true;')
    text=text.replace('v-model="newLocation" />','v-model="newLocation" :exclude-ids="items.map(item => item.id)" />')
    text=text.replace('saving || (enabled.changeLocation && !newLocation)','saving')
    target.write_text(text)
    path='components/Location/Tree/tree-state.ts';target=BUILD/path;text=target.read_text()
    text+='\nexport function containsLocation(node: import("@/lib/api/types/data-contracts").TreeItem): boolean { const todo = [node]; while (todo.length) { const current = todo.pop()!; if (current.type === "location") return true; todo.push(...(current.children || [])); } return false; }\n';target.write_text(text)
    replace('components/Location/Tree/Node.vue','import { useTreeState }','import { useTreeState, containsLocation }')
    replace('components/Location/Tree/Node.vue','children.filter(child => child.type === "location")','children.filter(containsLocation)')
    replace('components/Location/Tree/Root.vue','  import type { TreeItem }','  import { containsLocation } from "./tree-state";\n  import type { TreeItem }')
    replace('components/Location/Tree/Root.vue','const list = props.locs ?? [];','const list = (props.locs ?? []).filter(node => props.showItems !== false || containsLocation(node));')
    replace('pages/locations.vue','@click="openAll"','@click="openAll" :aria-label="$t(\'locations.expand_tree\')"')
    replace('pages/locations.vue','@click="closeAll"','@click="closeAll" :aria-label="$t(\'locations.collapse_tree\')"')
    replace('pages/locations.vue','@click="showItems = !showItems"','@click="showItems = !showItems" :aria-label="showItems ? $t(\'locations.hide_items\') : $t(\'locations.show_items\')"')
    # Mixed ancestors link to their actual native item/location pages.
    path='pages/location/[id]/index/index.vue'
    target=BUILD/path; text=target.read_text()
    text=text.replace('  const confirm = useConfirm();', '  const fullpath = computedAsync(async () => location.value ? (await api.items.fullpath(location.value.id)).data || [] : []);\n\n  const confirm = useConfirm();')
    start=text.index('              <Breadcrumb v-if="location?.parent">');end=text.index('              </Breadcrumb>',start)+len('              </Breadcrumb>')
    text=text[:start]+'''              <Breadcrumb v-if="fullpath && fullpath.length > 1">
                <BreadcrumbList><template v-for="(part, idx) in fullpath" :key="part.id">
                  <BreadcrumbItem><BreadcrumbLink v-if="idx < fullpath.length - 1" as-child><NuxtLink :to="`/${part.type}/${part.id}`">{{ part.name }}</NuxtLink></BreadcrumbLink><span v-else>{{ part.name }}</span></BreadcrumbItem>
                  <BreadcrumbSeparator v-if="idx < fullpath.length - 1" />
                </template></BreadcrumbList>
              </Breadcrumb>'''+text[end:]
    target.write_text(text)


def navigation_frontend():
    replace('layouts/default.vue', '      <Sidebar collapsible="icon">', '      <Sidebar side="left" collapsible="icon">')
    replace('layouts/default.vue', '<Collapsible v-else default-open', '<Collapsible v-else :default-open="n.name.value !== \'More\'"')
    replace('layouts/default.vue', '<SidebarMenuLink\n                        :href="n.to"', '<CollapsibleTrigger v-if="n.name.value === \'More\'" as-child><SidebarMenuButton :tooltip="n.name.value" class="flex gap-2"><component :is="n.icon" /><span>{{ n.name.value }}</span><MdiChevronRight class="ml-auto transition-transform duration-200 group-data-[state=open]/collapsible:rotate-90" /></SidebarMenuButton></CollapsibleTrigger>\n                      <SidebarMenuLink v-else\n                        :href="n.to"')
    replace('layouts/default.vue', '<CollapsibleTrigger as-child>\n                        <SidebarMenuButton class="flex size-12', '<CollapsibleTrigger v-if="n.name.value !== \'More\'" as-child>\n                        <SidebarMenuButton class="flex size-12')
    replace('layouts/default.vue', '    collapsible?: {\n      active: ComputedRef<boolean>;', '    collapsible?: {\n      action?: () => void;\n      active: ComputedRef<boolean>;')
    replace('layouts/default.vue', '<SidebarMenuLink\n                            :href="c.to"', '<SidebarMenuLink v-if="!c.action"\n                            :href="c.to"')
    replace('layouts/default.vue', '                          </SidebarMenuLink>\n                        </SidebarMenuSubItem>', '                          </SidebarMenuLink>\n                          <SidebarMenuButton v-else @click.prevent="c.action?.()"><span>{{ c.name.value }}</span></SidebarMenuButton>\n                        </SidebarMenuSubItem>')
    layout = BUILD/'layouts/default.vue'
    source = layout.read_text()
    start = source.index('              <!-- makes scanner accessible easily if using legacy header -->')
    end = source.index('              </SidebarMenuItem>', start) + len('              </SidebarMenuItem>\n')
    layout.write_text(source[:start] + source[end:])
    replace('layouts/default.vue', 'const nav: {', 'const baseNav: {')
    replace('layouts/default.vue', '  const quickMenuActions = reactive([', '''  const workshop = useWorkshop();
  const { selectedId: workshopGroup } = useCollections();
  const workshopLinks = computed(() => [
    ["loans", "Loans & notes"], ["map", "Workshop & storage"],
    ...(workshop.manager.value ? [["imports", "Imports"], ["labels", "Label queue"], ["recovery", "Recovery"], ["system", "System"]] : []),
  ]);
  const nav = computed<typeof baseNav>(() => [
    baseNav[0]!,
    { ...baseNav[3]!, id: 1, name: computed(() => "Inventory") },
    { id: 8, icon: MdiWrench, name: computed(() => "Workshop"), to: "/workshop/map", active: computed(() => route.path === "/workshop/map") },
    { id: 9, icon: MdiTagMultiple, name: computed(() => "Label"), to: "/workshop/labels", active: computed(() => route.path === "/workshop/labels") },
    { ...baseNav[7]!, id: 10, name: computed(() => "Users"), to: "/collection/members", active: computed(() => route.path === "/collection/members"), collapsible: undefined },
    {
      id: 11, icon: MdiFileDocumentMultiple, name: computed(() => "More"), to: "",
      active: computed(() => false),
      collapsible: [
        ...baseNav.slice(1, 3), baseNav[4]!, baseNav[5]!, baseNav[6]!,
        ...baseNav[7]!.collapsible!.filter(item => item.to !== "/collection/members"),
        ...workshopLinks.value.filter(([id]) => id !== "map" && id !== "labels").map(([id, name], index) => ({ id: 80 + index, name: computed(() => name!), to: `/workshop/${id}`, active: computed(() => route.path === `/workshop/${id}`) })),
        { id: 90, name: computed(() => "Equipment Terminal"), to: terminalURL.value, active: computed(() => false) },
        { id: 91, name: computed(() => t("menu.scanner")), to: "", active: computed(() => false), action: openScanner },
      ],
    },
  ]);
  watch([workshopGroup, () => useAuthContext().user?.id], () => { workshop.context.value = null; workshop.refresh().catch(() => {}); }, { immediate: true });

  const quickMenuActions = computed(() => [''')
    replace('layouts/default.vue', '...nav.map(v => ({', '...nav.value.filter(v => v.name.value !== "More").map(v => ({')
    target = BUILD/'layouts/default.vue'
    target.write_text(target.read_text().replace('text: computed(() => v.name.value),', 'text: v.name.value,'))


def shell_frontend():
    layout = BUILD/'layouts/default.vue'
    source = layout.read_text()
    start = source.index('<SidebarHeader class="items-center">')
    selector = '          <CollectionSelector />'
    end = source.index(selector, start) + len(selector)
    source = source[:start] + '''<SidebarHeader class="items-stretch gap-2 p-3">
          <NuxtLink to="/home" aria-label="C-Crate home" class="flex h-10 w-full items-center gap-3 rounded-md px-2 text-sidebar-foreground hover:bg-sidebar-accent group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0">
            <AppLogo aria-hidden="true" class="size-7 shrink-0" />
          </NuxtLink>

          <CollectionSelector />'''+source[end:]
    layout.write_text(source)
    replace('layouts/default.vue', '    SidebarGroupLabel,\n', '')
    replace('layouts/default.vue', 'drop-shadow-md hover:bg-primary/90', 'hover:bg-primary/90')
    replace('layouts/default.vue', 'class="flex justify-center group-data-[collapsible=icon]:justify-start group-data-[collapsible=icon]:bg-destructive group-data-[collapsible=icon]:text-destructive-foreground group-data-[collapsible=icon]:shadow-sm group-data-[collapsible=icon]:hover:bg-destructive/90"', 'class="flex justify-center rounded-md text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground group-data-[collapsible=icon]:justify-start"')
    replace('layouts/default.vue', 'class="sticky top-0 z-20 flex h-[var(--header-height-mobile)] translate-y-[-0.5px] flex-col bg-secondary p-2 shadow-md sm:h-[var(--header-height)] sm:flex-row"', 'class="sticky top-0 z-20 flex min-h-[var(--header-height-mobile)] flex-col gap-1 border-b border-border bg-card px-3 py-2 sm:min-h-[var(--header-height)] sm:flex-row"')
    replace('layouts/default.vue', '            <div class="flex h-1/2 grow items-center justify-end gap-2 sm:h-auto">', '            <div class="flex min-w-0 grow items-center justify-end gap-2">\n              <DeviceStatus v-if="!preferences.displayLegacyHeader || !terminalHeader" :enabled="!preferences.displayLegacyHeader || !terminalHeader" class="shrink-0" />')
    replace('layouts/default.vue', '        <AppHeaderDecor class="-mt-10 hidden lg:block" />', '''        <AppHeaderDecor class="-mt-10 hidden lg:block" />
            <DeviceStatus v-if="preferences.displayLegacyHeader && terminalHeader" :enabled="preferences.displayLegacyHeader && terminalHeader" class="absolute right-6 top-3 z-30 hidden lg:flex" />''')
    replace('layouts/default.vue', '<Button size="icon" @click="triggerSearch">', '<Button size="icon" :aria-label="$t(\'global.search\')" @click="triggerSearch">')
    replace('layouts/default.vue', '<Button size="icon" @click="openScanner">', '<Button size="icon" :aria-label="$t(\'menu.scanner\')" @click="openScanner">')
    replace('layouts/default.vue', '  const search = ref("");', '''  const terminalHeader = ref(false);
  let desktopHeaderMedia: MediaQueryList | null = null;
  const updateDesktopHeader = () => { terminalHeader.value = desktopHeaderMedia?.matches || false; };
  onMounted(() => { desktopHeaderMedia = window.matchMedia("(min-width: 1024px)"); updateDesktopHeader(); desktopHeaderMedia.addEventListener("change", updateDesktopHeader); });
  onBeforeUnmount(() => desktopHeaderMedia?.removeEventListener("change", updateDesktopHeader));
  const terminalURL = computed(() => { const url = new URL(window.location.href); url.port = "17749"; url.pathname = "/"; url.search = "?mode=editor"; url.hash = ""; return url.href; });
  const search = ref("");''')
    replace('layouts/default.vue', '  import AppHeaderDecor from "~/components/App/HeaderDecor.vue";', '  import DeviceStatus from "~/components/Workshop/DeviceStatus.vue";\n  import AppHeaderDecor from "~/components/App/HeaderDecor.vue";')


def prepare():
    shutil.copytree(UPSTREAM_ROOT/'upstream/homebox/frontend', BUILD, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('node_modules', '.nuxt', '.output'))
    shutil.copytree(ROOT/'homebox-ui/overlay', BUILD, dirs_exist_ok=True)
    shutil.copy2(ROOT/'kiosk/member-avatar.js', BUILD/'lib/member-avatar.js')
    shutil.copy2(ROOT/'kiosk/label-editor.js', BUILD/'lib/label-editor.js')
    package = json.loads((BUILD/'package.json').read_text())
    package['pnpm'] = {'overrides': {name: '3.5.20' for name in ('vue', '@vue/runtime-core', '@vue/runtime-dom', '@vue/reactivity', '@vue/shared', '@vue/compiler-sfc', '@vue/compiler-core', '@vue/compiler-dom', '@vue/compiler-ssr', '@vue/server-renderer')}}
    (BUILD/'package.json').write_text(json.dumps(package, indent=2)+'\n')
    if (ROOT/'homebox-ui/pnpm-lock.yaml').exists():
        shutil.copy2(ROOT/'homebox-ui/pnpm-lock.yaml', BUILD/'pnpm-lock.yaml')
    replace('nuxt.config.ts', 'css: ["@/assets/css/main.css"],', 'css: ["@/assets/css/main.css", "@/assets/css/workshop.css", "@/assets/css/ccrate.css"],')
    # The Home dashboard shows the same current custody as the equipment terminal.
    replace('pages/home/index.vue', '  import BaseCard from', '  import CheckedOutItems from "@/components/Workshop/CheckedOutItems.vue";\n  import BaseCard from')
    replace('pages/home/index.vue', '      <section>\n        <Subtitle> {{ $t("home.recently_added") }}', '      <CheckedOutItems />\n\n      <section>\n        <Subtitle> {{ $t("home.recently_added") }}')
    # Native sidebar and quick menu, with manager-only entries hidden for members.
    navigation_frontend()
    shell_frontend()
    replace('layouts/default.vue', 'class="h-9 grow sm:max-w-sm"', 'class="h-9 min-w-0 grow sm:max-w-sm"')
    # Put badges on the actual existing Collection members table.
    path = 'pages/collection/index/members.vue'
    replace(path, '  const loading = ref(true);', '''  const workshop = useWorkshop();
  const { selectedId } = useCollections();
  const badgeRows = ref<any[]>([]), peopleRows = ref<any[]>([]), workshopError = ref("");
  const memberLoans = ref<WorkshopLoan[] | null>(null), itemLoading = ref(true), itemError = ref("");
  let itemRevision = 0, memberTimer: ReturnType<typeof setInterval> | null = null;
  async function loadMemberLoans() {
    const revision = ++itemRevision;
    itemLoading.value = true; itemError.value = "";
    try {
      const rows = await workshop.request<WorkshopLoan[]>("loans");
      if (revision === itemRevision) memberLoans.value = rows;
    } catch (cause) { if (revision === itemRevision) itemError.value = (cause as Error).message; }
    finally { if (revision === itemRevision) itemLoading.value = false; }
  }
  function refreshVisibleItems() { if (document.visibilityState === "visible" && !itemLoading.value) void loadMemberLoans(); }
  function refreshMembers() { void loadMembers(); void loadBadges(); void loadMemberLoans(); }
  let workshopRevision = 0;
  async function loadBadges() {
    const revision = ++workshopRevision;
    badgeRows.value = []; peopleRows.value = []; workshopError.value = "";
    try {
      await workshop.refresh();
      if (!workshop.manager.value) return;
      const [badges, people] = await Promise.all([workshop.request<any[]>("badges"), workshop.request<any[]>("people")]);
      if (revision === workshopRevision) { badgeRows.value = badges; peopleRows.value = people; }
    } catch (cause) { if (revision === workshopRevision) workshopError.value = (cause as Error).message; }
  }
  watch(selectedId, () => { memberLoans.value = null; refreshMembers(); }, { flush: "sync" });
  onMounted(() => {
    void loadMemberLoans();
    window.addEventListener("focus", refreshVisibleItems);
    document.addEventListener("visibilitychange", refreshVisibleItems);
    memberTimer = setInterval(refreshVisibleItems, 30000);
  });
  onBeforeUnmount(() => {
    workshopRevision++; itemRevision++; memberLoans.value = null;
    if (memberTimer) clearInterval(memberTimer);
    window.removeEventListener("focus", refreshVisibleItems);
    document.removeEventListener("visibilitychange", refreshVisibleItems);
  });

  const loading = ref(true);''')
    replace(path, '<TableCell>{{ user.name }}</TableCell>', '<TableCell><div class="flex items-center gap-3"><MemberAvatar :member-id="user.id" :name="user.name" /><span class="font-medium">{{ user.name }}</span></div></TableCell>')
    replace(path, '  import { Button }', '  import MemberAvatar from "@/components/Workshop/MemberAvatar.vue";\n  import MemberItems from "@/components/Workshop/MemberItems.vue";\n  import type { WorkshopLoan } from "@/lib/workshop-loans";\n  import BadgeActions from "@/components/Workshop/BadgeActions.vue";\n  import { Button }')
    replace(path, '    loadMembers();\n  });', '    loadMembers();\n    loadBadges();\n  });')
    replace(path, '  <div class="space-y-4">', '''  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <p class="text-sm text-muted-foreground">Members, kiosk badges and the items each person has checked out.</p>
      <Button variant="outline" size="sm" :disabled="loading || itemLoading" @click="refreshMembers">Refresh members &amp; items</Button>
    </div>
    <p v-if="itemError" role="alert" class="text-sm text-destructive">Could not load checked-out items. {{ itemError }}</p>
    <p v-if="workshopError" role="alert" class="text-sm text-destructive">Badge management: {{ workshopError }} <Button variant="link" @click="loadBadges">Reload badge management</Button></p>''')
    replace(path, '<TableHead>{{ $t("collection.members.name") }}</TableHead>', '<TableHead>User</TableHead>')
    replace(path, '              <TableHead class="w-32', '              <TableHead v-if="workshop.manager.value">Kiosk Badge</TableHead>\n              <TableHead>Items</TableHead>\n              <TableHead class="w-32')
    replace(path, '              <TableCell>\n                <div class="ml-auto">', '''              <TableCell v-if="workshop.manager.value">
                <BadgeActions :member="user" :badges="badgeRows.filter(row => row.user_id === user.id)" :can-manage="!!peopleRows.find(row => row.id === user.id)?.workshop_manager" :protected-owner="!!peopleRows.find(row => row.id === user.id)?.protected_owner" @changed="loadBadges" />
              </TableCell>
              <TableCell><MemberItems :member-id="user.id" :loans="memberLoans" :loading="itemLoading" :error="itemError" /></TableCell>
              <TableCell>
                <div class="ml-auto">''')
    # Item loans sit alongside native Details/Maintenance/Edit; details show status.
    path = 'pages/item/[id]/index.vue'
    item_log_frontend()
    replace(path, '        id: "edit",', '        id: "loans", name: "Loans & return notes", to: `/item/${itemId.value}/loans`,\n      },\n      {\n        id: "edit",')
    replace(path, '{{ $t(tab.name) }}', '{{ tab.id === "loans" ? tab.name : $t(tab.name) }}')
    replace(path, ':id="item.assetId"\n                type="asset"', ':id="item.assetId"\n                :entity-id="item.id"\n                type="asset"')
    replace(path, '<NuxtPage :item="item" :page-key="itemId" />', '<NuxtPage :item="item" :page-key="itemId" />\n        <ItemLoans v-if="!hasNested" :item-id="itemId" compact />')
    # Extend the existing label dialog; browser printing remains native.
    path = 'components/global/LabelMaker.vue'
    replace(path, '  import PageQRCode', '  import PiPrint from "@/components/Workshop/PiPrint.vue";\n  import PageQRCode')
    replace(path, '    id: string;', '    id: string;\n    entityId?: string;')
    replace(path, '        <img :src="getLabelUrl(false)" />', '<img :src="getLabelUrl(false)" alt="Homebox label preview" />\n        <PiPrint :id="id" :entity-id="entityId" />')
    replace(path, '<Button size="icon" @click="openDialog(DialogID.PrintLabel)">', '<Button size="icon" :aria-label="$t(\'components.global.label_maker.browser_print\')" @click="openDialog(DialogID.PrintLabel)">')
    # Manage native people beside badges and custody, with collection-owner access.
    contract=BUILD/'lib/api/types/data-contracts.ts';body=contract.read_text()
    start=body.index('export interface UserSummary {');end=body.index('\n}',start)
    body=body[:end]+'\n  avatar?: string;'+body[end:];contract.write_text(body)
    path='pages/collection/index/members.vue';target=BUILD/path;body=target.read_text()
    body=body.replace('  import MemberAvatar from', '  import UserManager from "@/components/Workshop/UserManager.vue";\n  import MemberAvatar from')
    body=body.replace('  const workshop = useWorkshop();', '  const workshop = useWorkshop();\n  const userAdmin = ref(false), userManager = ref<InstanceType<typeof UserManager> | null>(null);')
    body=body.replace('const [badges, people] = await Promise.all([workshop.request<any[]>("badges"), workshop.request<any[]>("people")]);','const [badges, people, administration] = await Promise.all([workshop.request<any[]>("badges"), workshop.request<any[]>("people"), workshop.request<{ canManage: boolean }>("users/administration")]);')
    body=body.replace('badgeRows.value = badges; peopleRows.value = people;', 'badgeRows.value = badges; peopleRows.value = people; userAdmin.value = administration.canManage;')
    body=body.replace('if (!workshop.manager.value) return;', 'if (!workshop.manager.value) { userAdmin.value = false; return; }')
    body=body.replace('watch(selectedId, () => { memberLoans.value = null;', 'watch(selectedId, () => { userAdmin.value = false; memberLoans.value = null;')
    body=body.replace('      <Button variant="outline" size="sm" :disabled="loading || itemLoading"', '      <Button v-if="userAdmin" variant="outline" size="sm" @click="userManager?.show()">Manage users</Button>\n      <Button variant="outline" size="sm" :disabled="loading || itemLoading"')
    body=body.replace('    <p v-if="itemError"', '    <UserManager v-if="userAdmin" ref="userManager" :members="members" @changed="refreshMembers" />\n    <p v-if="itemError"')
    body=body.replace('<MemberAvatar :member-id="user.id" :name="user.name" /><span class="font-medium">{{ user.name }}</span>', '<MemberAvatar :member-id="user.id" :name="user.name" :picture="user.avatar" /><span><span class="block font-medium">{{ user.name }}</span><span class="block text-xs text-muted-foreground">ID {{ user.id.slice(0,8) }}</span></span>')
    body=body.replace('<TableCell>{{ user.email }}</TableCell>', '<TableCell>{{ user.email || "—" }}</TableCell>')
    body=body.replace('                <div class="ml-auto">','                <div class="ml-auto flex items-center justify-end gap-2">\n                  <Button v-if="userAdmin" variant="outline" size="sm" :aria-label="\'Manage profile: \' + user.name" @click="userManager?.show(user)">Manage profile</Button>')
    body=body.replace(':disabled="removing[user.id] || (isLastMember && user.id === currentUserId)"', ':disabled="!userAdmin || removing[user.id] || user.id === currentUserId || !!peopleRows.find(row => row.id === user.id)?.protected_owner"')
    body=body.replace('  const loading = ref(true);', '  let memberRevision = 0;\n  const loading = ref(true);')
    body=body.replace('const loadMembers = async () => {', 'const loadMembers = async () => {\n    const revision = ++memberRevision;')
    body=body.replace('const res = await api.group.getMembers();', 'const res = await api.group.getMembers();\n      if (revision !== memberRevision) return;')
    start=body.index('  const loadMembers = async () => {');end=body.index('  const handleRemove',start)
    part=body[start:end].replace('    } catch (e) {','    } catch (e) {\n      if (revision !== memberRevision) return;').replace('      loading.value = false;', '      if (revision === memberRevision) loading.value = false;')
    body=body[:start]+part+body[end:]
    body=body.replace('workshopRevision++; itemRevision++;', 'memberRevision++; workshopRevision++; itemRevision++;')
    body=body.replace('watch(selectedId, () => { userAdmin.value = false;', 'watch([selectedId, () => auth.user?.id], () => { members.value = []; userAdmin.value = false;')
    target.write_text(body)
    nest_frontend()
    brand_frontend()


def build():
    global TOOLCHAIN_ROOT, UPSTREAM_ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument('--toolchain-root', type=pathlib.Path, default=TOOLCHAIN_ROOT)
    parser.add_argument('--upstream-root', type=pathlib.Path, default=UPSTREAM_ROOT)
    parser.add_argument('--prepare', action='store_true', help='prepare dependencies without running typecheck or build')
    args = parser.parse_args()
    TOOLCHAIN_ROOT, UPSTREAM_ROOT = args.toolchain_root.resolve(), args.upstream_root.resolve()
    prepare()
    node = pathlib.Path((TOOLCHAIN_ROOT/'node-path.txt').read_text().strip())
    env = dict(os.environ, PATH=str(node/'bin')+os.pathsep+os.environ['PATH'])
    # oxc-parser 0.72's native ARM binding requires instructions absent on this Pi.
    # Use the same version's upstream WASI binding only for this build dependency.
    wasi = TOOLCHAIN_ROOT/'oxc-wasi/node_modules/@oxc-parser/binding-wasm32-wasi'
    if wasi.exists():
        binding = BUILD/'node_modules/.pnpm/oxc-parser@0.72.3/node_modules/oxc-parser/bindings.js'
        source = binding.read_text()
        anchor = 'nativeBinding = requireNative()'
        if anchor in source:
            binding.write_text(source.replace(anchor, 'nativeBinding = require('+repr(str(wasi))+')'))
    pnpm = TOOLCHAIN_ROOT/'pnpm/node_modules/.bin/pnpm'
    subprocess.run([str(pnpm), 'exec', 'nuxt', 'prepare'], cwd=BUILD, env=env, check=True)
    if not args.prepare:
        result = subprocess.run([str(pnpm), 'exec', 'nuxi', 'typecheck'], cwd=BUILD, env=env, capture_output=True, text=True)
        (ROOT/'work/homebox-ui-typecheck.log').write_text(result.stdout+result.stderr)
        diagnostics = [list(match.groups()) for match in re.finditer(r'^(.+?)\(\d+,\d+\): error (TS\d+): (.*)$', result.stdout+result.stderr, re.M)]
        if result.returncode:
            baseline = json.loads((ROOT/'homebox-ui/upstream-typecheck.json').read_text())
            pin = subprocess.check_output(['git', '-C', str(UPSTREAM_ROOT/'upstream/homebox'), 'rev-parse', 'HEAD'], text=True).strip()
            additional = Counter(map(tuple, diagnostics))-Counter(map(tuple, baseline['diagnostics']))
            if baseline['pin'] != pin or not diagnostics or additional:
                print(result.stdout+result.stderr)
                raise RuntimeError('Frontend typecheck introduced errors or its upstream baseline changed.')
            print(f'Typecheck: no added diagnostics; {len(diagnostics)} pre-existing upstream diagnostics.', flush=True)
        subprocess.run([str(pnpm), 'run', 'build'], cwd=BUILD, env=env, check=True)


if __name__ == '__main__':
    build()
