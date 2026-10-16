<script setup lang="ts">
  import { Camera, Copy, Minus, ScanText, X } from "lucide-vue-next";
  import { applyCameraControl, cameraControlReadback, cameraControlSessionState, captureCameraFrame, digitalZoomDrawArgs, isCameraControlRequestCurrent, watchCameraTrackEnd } from "~/lib/ocr-camera-controls";
  import { applyRecognizedTextWithoutOverwritingEdits, recognizeStructuredTextFromImage } from "~/lib/local-ocr";
  import { clampOcrPopoverPosition, isOcrCaptureCurrent, isOcrScanCurrent, nextOcrPopoverState } from "~/lib/orc-popover-state";

  const props = defineProps<{ launcherTarget: string }>();
  const enabled = ref(false), open = ref(false), minimized = ref(false), cameraBusy = ref(false), cameraActive = ref(false), scanning = ref(false), copying = ref(false);
  const video = ref<HTMLVideoElement | null>(null), preview = ref<HTMLCanvasElement | null>(null), result = ref(""), resultRevision = ref(0), error = ref(""), imageURL = ref("");
  const controls = ref<ReturnType<typeof cameraControlSessionState>["controls"]>(null);
  const digitalZoom = ref(1), hardwareZoom = ref(1), focusMode = ref(""), focusDistance = ref(0);
  const controlsBusy = ref(false), controlStatus = ref(""), controlError = ref("");
  const recognizedLines = ref<Array<{ text: string; bbox: { x0: number; y0: number; x1: number; y1: number }; confidence: number }>>([]);
  const recognizedImageSize = ref({ width: 0, height: 0 });
  const lineColors = ["#b91c1c", "#1d4ed8", "#047857", "#7e22ce", "#c2410c", "#0e7490"];
  const position = ref({ left: 0, top: 64 });
  let stream: MediaStream | null = null, image: Blob | null = null, drag: { x: number; y: number; left: number; top: number } | null = null;
  let cameraGeneration = 0, scanGeneration = 0, copyGeneration = 0, disposed = false;
  let activeTrack: MediaStreamTrack | null = null, previewFrame = 0;
  let unwatchActiveTrack: (() => void) | null = null;
  let defaultZoom: number | undefined, defaultFocusMode: string | undefined, defaultFocusDistance: number | undefined;

  function currentTrack(track: MediaStreamTrack, generation: number) {
    return !disposed && stream?.getVideoTracks()[0] === track && isCameraControlRequestCurrent(track, generation, activeTrack, cameraGeneration);
  }
  function settings(track: MediaStreamTrack) {
    try { return track.getSettings() as MediaTrackSettings & { focusMode?: string; zoom?: number; focusDistance?: number }; }
    catch { return {}; }
  }
  function readControls(track: MediaStreamTrack) {
    const reported = settings(track);
    if (Number.isFinite(reported.zoom)) hardwareZoom.value = reported.zoom!;
    if (typeof reported.focusMode === "string") focusMode.value = reported.focusMode;
    if (Number.isFinite(reported.focusDistance)) focusDistance.value = reported.focusDistance!;
    return reported;
  }
  function drawDigitalFrame(context: CanvasRenderingContext2D, source: HTMLVideoElement, width: number, height: number) {
    const [x, y, cropWidth, cropHeight, dx, dy, destWidth, destHeight] = digitalZoomDrawArgs(width, height, digitalZoom.value);
    context.drawImage(source, x, y, cropWidth, cropHeight, dx, dy, destWidth, destHeight);
  }
  function drawPreview(track: MediaStreamTrack, generation: number) {
    if (!currentTrack(track, generation)) return;
    const source = video.value, canvas = preview.value;
    if (source?.videoWidth && source.videoHeight && canvas) {
      if (canvas.width !== source.videoWidth) canvas.width = source.videoWidth;
      if (canvas.height !== source.videoHeight) canvas.height = source.videoHeight;
      const context = canvas.getContext("2d");
      if (context) drawDigitalFrame(context, source, canvas.width, canvas.height);
    }
    previewFrame = requestAnimationFrame(() => drawPreview(track, generation));
  }
  async function changeControl(name: "zoom" | "focusMode" | "focusDistance", value: number | string) {
    const track = activeTrack, generation = cameraGeneration;
    if (!track || !currentTrack(track, generation) || controlsBusy.value) return;
    controlsBusy.value = true;
    controlError.value = "";
    try {
      await applyCameraControl(track, name, value);
      if (!currentTrack(track, generation)) return;
      const reported = readControls(track);
      const readback = cameraControlReadback(track, name, value, reported);
      if (readback.state === "unreported") {
        controlStatus.value = "The camera did not report the updated setting.";
      } else if (readback.state === "mismatch") {
        controlStatus.value = `The camera reports ${name === "focusMode" ? "focus mode" : name === "focusDistance" ? "focus distance" : "zoom"} ${readback.actual}; the requested change was not confirmed.`;
      } else {
        controlStatus.value = `${name === "focusMode" ? "Focus mode" : name === "focusDistance" ? "Focus distance" : "Zoom"} set to ${readback.actual}.`;
      }
    } catch (cause) {
      if (currentTrack(track, generation)) {
        readControls(track);
        controlError.value = `Camera control could not be changed: ${(cause as Error)?.message || "unknown error"}`;
      }
    } finally {
      if (currentTrack(track, generation)) controlsBusy.value = false;
    }
  }
  function requestControl(event: Event, name: "zoom" | "focusMode" | "focusDistance") {
    const target = event.target as HTMLInputElement | HTMLSelectElement;
    const requested = name === "focusMode" ? target.value : Number(target.value);
    target.value = String(name === "zoom" ? hardwareZoom.value : name === "focusDistance" ? focusDistance.value : focusMode.value);
    void changeControl(name, requested);
  }

  function transitionVisibility(action: "toggle-enabled" | "open" | "close") {
    const next = nextOcrPopoverState({ enabled: enabled.value, open: open.value }, action);
    enabled.value = next.enabled;
    open.value = next.open;
    if (!next.enabled) {
      stopCamera();
      cancelPendingScan();
      cancelPendingCopy();
      minimized.value = false;
    }
    if (action === "open" && next.open) {
      minimized.value = false;
      position.value.left = Math.max(0, window.innerWidth - 416);
      position.value.top = 64;
      clampPosition();
    }
  }

  function stopCamera() {
    cameraGeneration++;
    cancelAnimationFrame(previewFrame);
    unwatchActiveTrack?.();
    unwatchActiveTrack = null;
    stream?.getTracks().forEach(track => track.stop());
    stream = null;
    activeTrack = null;
    const reset = cameraControlSessionState(null);
    controls.value = reset.controls;
    hardwareZoom.value = reset.hardwareZoom;
    focusMode.value = reset.focusMode;
    focusDistance.value = reset.focusDistance;
    defaultZoom = reset.defaultZoom;
    defaultFocusMode = reset.defaultFocusMode;
    defaultFocusDistance = reset.defaultFocusDistance;
    controlsBusy.value = false;
    controlError.value = "";
    controlStatus.value = "";
    digitalZoom.value = 1;
    cameraActive.value = false;
    if (video.value) video.value.srcObject = null;
    cameraBusy.value = false;
  }
  function cancelPendingScan() {
    scanGeneration++;
    scanning.value = false;
  }
  function cancelPendingCopy() {
    copyGeneration++;
    copying.value = false;
  }
  function show() { transitionVisibility("open"); }
  function close() { stopCamera(); cancelPendingScan(); cancelPendingCopy(); minimized.value = false; transitionVisibility("close"); }
  function toggleEnabled() { transitionVisibility("toggle-enabled"); }
  function minimize() { stopCamera(); cancelPendingScan(); cancelPendingCopy(); minimized.value = true; }
  async function startCamera() {
    if (cameraBusy.value || cameraActive.value) return;
    error.value = "";
    if (!navigator.mediaDevices?.getUserMedia) {
      error.value = "This browser does not support camera access.";
      return;
    }
    const generation = ++cameraGeneration;
    let requestedStream: MediaStream | null = null;
    cameraBusy.value = true;
    try {
      requestedStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false });
      if (disposed || generation !== cameraGeneration || !open.value || minimized.value) {
        requestedStream.getTracks().forEach(track => track.stop());
        return;
      }
      stream = requestedStream;
      if (video.value) {
        video.value.srcObject = stream;
        await video.value.play();
      }
      if (disposed || generation !== cameraGeneration || stream !== requestedStream || !open.value || minimized.value) {
        requestedStream.getTracks().forEach(track => track.stop());
        return;
      }
      const track = requestedStream.getVideoTracks()[0];
      if (!track || track.readyState === "ended") {
        stopCamera();
        error.value = "The camera connection ended. Start the camera again.";
        return;
      }
      cameraActive.value = true;
      activeTrack = track;
      unwatchActiveTrack = watchCameraTrackEnd(track,
        () => !disposed && generation === cameraGeneration && activeTrack === track && stream?.getVideoTracks()[0] === track,
        () => {
          stopCamera();
          error.value = "The camera connection ended. Start the camera again.";
        });
      const initial = cameraControlSessionState(track);
      controls.value = initial.controls;
      hardwareZoom.value = initial.hardwareZoom;
      focusMode.value = initial.focusMode;
      focusDistance.value = initial.focusDistance;
      defaultZoom = initial.defaultZoom;
      defaultFocusMode = initial.defaultFocusMode;
      defaultFocusDistance = initial.defaultFocusDistance;
      controlStatus.value = `${controls.value.zoom ? "Camera zoom is available." : "Digital zoom crops and enlarges the image without adding detail."} ${controls.value.focusModes.length ? "Focus modes are available." : "Focus adjustment is unavailable on this camera."}`;
      drawPreview(track, generation);
    } catch (cause) {
      requestedStream?.getTracks().forEach(track => track.stop());
      if (!disposed && generation === cameraGeneration) {
        stopCamera();
        const name = (cause as DOMException)?.name;
        error.value = name === "NotAllowedError" || name === "SecurityError"
          ? "Camera access was denied. Allow camera permission in your browser and try again."
          : `Could not start the camera: ${(cause as Error)?.message || "unknown error"}`;
      }
    } finally {
      if (generation === cameraGeneration) cameraBusy.value = false;
    }
  }
  async function capture() {
    const source = video.value;
    if (!source?.videoWidth || !source.videoHeight) { error.value = "The camera is not ready yet. Start it and try again."; return; }
    const generation = cameraGeneration;
    const photo = await captureCameraFrame(source, digitalZoom.value) as Blob | null;
    if (!isOcrCaptureCurrent(generation, cameraGeneration, {
      enabled: enabled.value,
      open: open.value,
      minimized: minimized.value,
      cameraActive: cameraActive.value,
      disposed,
    })) return;
    if (!photo) { error.value = "Could not capture a photo. Try again."; return; }
    scanGeneration++;
    scanning.value = false;
    clearRecognizedLines();
    if (imageURL.value) URL.revokeObjectURL(imageURL.value);
    image = photo;
    imageURL.value = URL.createObjectURL(photo);
    error.value = "";
    stopCamera();
  }
  function clearRecognizedLines() {
    recognizedLines.value = [];
    recognizedImageSize.value = { width: 0, height: 0 };
  }
  async function scan() {
    if (!image) return;
    const generation = ++scanGeneration, scannedImage = image;
    clearRecognizedLines();
    scanning.value = true;
    error.value = "";
    let recognized: Awaited<ReturnType<typeof recognizeStructuredTextFromImage>> | null = null;
    try {
      const outcome = await applyRecognizedTextWithoutOverwritingEdits({
        getText: () => result.value,
        getRevision: () => resultRevision.value,
        setText: (text: string) => { result.value = text; },
        recognize: async source => {
          recognized = await recognizeStructuredTextFromImage(source);
          return recognized;
        },
        isCurrent: () => image === scannedImage && isOcrScanCurrent(generation, scanGeneration, {
          enabled: enabled.value,
          open: open.value,
          minimized: minimized.value,
          disposed,
        }),
        image: scannedImage,
      });
      if (outcome === "stale") return;
      const lineResult = recognized as Awaited<ReturnType<typeof recognizeStructuredTextFromImage>> | null;
      if (outcome === "applied" && lineResult && generation === scanGeneration && image === scannedImage) {
        recognizedLines.value = lineResult.lines.filter(line => {
          const { x0, y0, x1, y1 } = line.bbox;
          return [x0, y0, x1, y1].every(Number.isFinite) && x1 > x0 && y1 > y0;
        });
        recognizedImageSize.value = { width: lineResult.imageWidth, height: lineResult.imageHeight };
      }
      else if (outcome === "empty") error.value = "No text was recognized. Retake the photo or adjust it and scan again.";
      else if (outcome === "edited-during-recognition") error.value = "Your text changed while scanning. Your edits were kept.";
    } catch (cause) {
      if (generation === scanGeneration && image === scannedImage) {
        error.value = `OCR could not read this photo: ${(cause as Error)?.message || "unknown error"}. You can retry the scan.`;
      }
    } finally { if (generation === scanGeneration) scanning.value = false; }
  }
  async function copy() {
    const generation = ++copyGeneration;
    copying.value = true;
    error.value = "";
    try { await navigator.clipboard.writeText(result.value); }
    catch { if (isOcrScanCurrent(generation, copyGeneration, { enabled: enabled.value, open: open.value, minimized: minimized.value, disposed })) error.value = "Could not copy text. Select it in the text box and copy it manually."; }
    finally { if (generation === copyGeneration) copying.value = false; }
  }
  function retake() {
    cancelPendingScan();
    clearRecognizedLines();
    error.value = "";
    if (imageURL.value) URL.revokeObjectURL(imageURL.value);
    imageURL.value = "";
    image = null;
  }
  function startDrag(event: PointerEvent) {
    if ((event.target as HTMLElement).closest("button")) return;
    const rect = (event.currentTarget as HTMLElement).closest("section")?.getBoundingClientRect();
    if (!rect) return;
    drag = { x: event.clientX, y: event.clientY, left: rect.left, top: rect.top };
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
  }
  function moveDrag(event: PointerEvent) {
    if (!drag) return;
    const rect = (event.currentTarget as HTMLElement).closest("section")?.getBoundingClientRect();
    if (!rect) return;
    position.value = clampOcrPopoverPosition(
      { left: drag.left + event.clientX - drag.x, top: drag.top + event.clientY - drag.y },
      window.innerWidth,
      window.innerHeight,
      rect.width,
    );
  }
  function clampPosition() {
    const rect = panel.value?.getBoundingClientRect();
    const width = rect?.width ?? Math.min(384, window.innerWidth - 16);
    position.value = clampOcrPopoverPosition(position.value, window.innerWidth, window.innerHeight, width);
  }
  function moveByKeyboard(event: KeyboardEvent) {
    if (event.target !== event.currentTarget) return;
    const directions: Record<string, [number, number]> = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
    const direction = directions[event.key];
    if (!direction) return;
    event.preventDefault();
    position.value = { left: position.value.left + direction[0] * 24, top: position.value.top + direction[1] * 24 };
    clampPosition();
  }
  function endDrag() { drag = null; }
  const panel = ref<HTMLElement | null>(null);
  onMounted(() => window.addEventListener("resize", clampPosition));
  onBeforeUnmount(() => {
    disposed = true;
    stopCamera();
    cancelPendingCopy();
    window.removeEventListener("resize", clampPosition);
    if (imageURL.value) URL.revokeObjectURL(imageURL.value);
  });
</script>

<template>
  <Teleport defer :to="props.launcherTarget">
    <button
      type="button"
      class="inline-flex h-9 shrink-0 items-center gap-2 rounded-md border px-3 text-sm font-medium shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      :class="enabled ? 'border-primary/40 bg-primary/10 text-primary hover:bg-primary/15' : 'border-border bg-card text-foreground hover:bg-accent'"
      :aria-label="enabled ? 'Disable text capture' : 'Enable text capture'"
      :aria-pressed="enabled"
      @click="toggleEnabled"
    >
      <ScanText class="size-4" /> Text capture {{ enabled ? "on" : "off" }}
    </button>
  </Teleport>
  <Teleport to="body">
    <button
      v-if="enabled && !open"
      type="button"
      class="fixed bottom-5 right-5 z-40 inline-flex size-12 items-center justify-center rounded-full border border-primary/40 bg-primary text-primary-foreground shadow-lg hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      aria-label="Open text capture"
      title="Open text capture"
      @click="show"
    >
      <ScanText class="size-5" />
    </button>
    <section
      v-if="open"
      ref="panel"
      class="fixed z-50 flex max-h-[calc(100vh-1rem)] w-[min(24rem,calc(100vw-1rem))] flex-col overflow-hidden rounded-lg border border-border bg-card text-card-foreground shadow-xl"
      :style="{ left: `${position.left}px`, top: `${position.top}px`, maxHeight: `calc(100vh - ${position.top}px - 1rem)` }"
      aria-label="Text capture"
    >
      <header
        class="flex shrink-0 cursor-move touch-none items-center justify-between border-b border-border bg-muted/60 px-3 py-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
        tabindex="0"
        aria-label="Move text capture window. Use arrow keys to reposition."
        @pointerdown="startDrag"
        @pointermove="moveDrag"
        @pointerup="endDrag"
        @pointercancel="endDrag"
        @keydown="moveByKeyboard"
      >
        <div class="flex items-center gap-2 text-sm font-semibold"><ScanText class="size-4 text-primary" /> Text capture <span class="text-xs font-normal text-muted-foreground">· C-Crate</span></div>
        <div class="flex items-center gap-1">
          <button type="button" class="rounded p-1 hover:bg-accent" aria-label="Minimize text capture" @click="minimize"><Minus class="size-4" /></button>
          <button type="button" class="rounded p-1 hover:bg-accent" aria-label="Close text capture" @click="close"><X class="size-4" /></button>
        </div>
      </header>
      <p role="status" aria-atomic="true" :class="controlStatus ? 'px-3 pt-2 text-xs text-muted-foreground' : 'sr-only'">{{ controlStatus }}</p>
      <div v-if="!minimized" class="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
        <p class="text-xs text-muted-foreground">Photos stay on this device. OCR runs in this browser. On first scan, the OCR code and English model download here.</p>
        <div class="relative flex aspect-[4/3] items-center justify-center overflow-hidden rounded-md bg-muted">
          <img v-if="imageURL" :src="imageURL" alt="Captured image for OCR" class="h-full w-full object-contain" />
          <svg v-if="imageURL && recognizedImageSize.width && recognizedImageSize.height && recognizedLines.length" class="pointer-events-none absolute h-full w-full" :viewBox="`0 0 ${recognizedImageSize.width} ${recognizedImageSize.height}`" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
            <rect v-for="(line, index) in recognizedLines" :key="`box-${index}`" :x="line.bbox.x0" :y="line.bbox.y0" :width="line.bbox.x1 - line.bbox.x0" :height="line.bbox.y1 - line.bbox.y0" :stroke="lineColors[index % lineColors.length]" fill="none" stroke-width="3" />
          </svg>
          <video v-if="!imageURL" ref="video" autoplay muted playsinline class="hidden" />
          <canvas v-if="!imageURL" ref="preview" class="h-full w-full object-contain" aria-label="Live camera preview" />
          <span v-if="!imageURL && !cameraActive" class="absolute text-sm text-muted-foreground">Camera is off</span>
        </div>
        <div v-if="cameraActive && controls" class="space-y-2 rounded-md border border-border p-2 text-sm">
          <div v-if="controls.zoom" class="space-y-1">
            <label for="ocr-hardware-zoom" class="block font-medium">Camera zoom <span class="font-normal">{{ hardwareZoom }}×</span></label>
            <div class="flex items-center gap-2">
              <input id="ocr-hardware-zoom" type="range" class="min-w-0 flex-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" :min="controls.zoom.min" :max="controls.zoom.max" :step="controls.zoom.step || 'any'" :value="hardwareZoom" :disabled="controlsBusy" @change="requestControl($event, 'zoom')" />
              <button type="button" class="rounded border border-border px-2 py-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50" :disabled="controlsBusy || defaultZoom === undefined" @click="changeControl('zoom', defaultZoom!)">Reset zoom</button>
            </div>
          </div>
          <div v-else class="space-y-1">
            <label for="ocr-digital-zoom" class="block font-medium">Digital zoom <span class="font-normal">{{ digitalZoom }}×</span></label>
            <div class="flex items-center gap-2">
              <input id="ocr-digital-zoom" v-model.number="digitalZoom" type="range" class="min-w-0 flex-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" min="1" max="4" step="0.1" />
              <button type="button" class="rounded border border-border px-2 py-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" @click="digitalZoom = 1">Reset zoom</button>
            </div>
            <p class="text-xs text-muted-foreground">Digital zoom crops and enlarges the image without adding detail.</p>
          </div>
          <div v-if="controls.focusModes.length" class="space-y-1">
            <label for="ocr-focus-mode" class="block font-medium">Focus mode</label>
            <div class="flex items-center gap-2">
              <select id="ocr-focus-mode" class="min-w-0 flex-1 rounded border border-input bg-background px-2 py-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" :value="focusMode" :disabled="controlsBusy" @change="requestControl($event, 'focusMode')">
                <option v-if="!controls.focusModes.includes(focusMode)" value="" disabled>Current mode unknown</option>
                <option v-for="mode in controls.focusModes" :key="mode" :value="mode">{{ mode }}</option>
              </select>
              <button type="button" class="rounded border border-border px-2 py-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50" :disabled="controlsBusy || !defaultFocusMode || !controls.focusModes.includes(defaultFocusMode)" @click="changeControl('focusMode', defaultFocusMode!)">Reset focus</button>
            </div>
            <p v-if="focusMode === 'continuous' || focusMode === 'single-shot'" class="text-xs text-muted-foreground">Focus is automatic.</p>
            <p v-else-if="focusMode === 'none'" class="text-xs text-muted-foreground">This camera does not offer adjustable focus.</p>
          </div>
          <p v-else class="text-xs text-muted-foreground">Focus adjustment is unavailable on this camera.</p>
          <div v-if="controls.focusDistance" class="space-y-1">
            <label for="ocr-focus-distance" class="block font-medium">Manual focus distance <span class="font-normal">{{ focusDistance }}</span></label>
            <div class="flex items-center gap-2">
              <input id="ocr-focus-distance" type="range" class="min-w-0 flex-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" :min="controls.focusDistance.min" :max="controls.focusDistance.max" :step="controls.focusDistance.step || 'any'" :value="focusDistance" :disabled="controlsBusy || focusMode !== 'manual'" @change="requestControl($event, 'focusDistance')" />
              <button type="button" class="rounded border border-border px-2 py-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50" :disabled="controlsBusy || focusMode !== 'manual' || defaultFocusDistance === undefined" @click="changeControl('focusDistance', defaultFocusDistance!)">Reset distance</button>
            </div>
            <p v-if="focusMode !== 'manual'" class="text-xs text-muted-foreground">Select manual focus mode to adjust distance.</p>
          </div>
          <p v-if="controlError" role="alert" class="text-xs text-destructive">{{ controlError }}</p>
        </div>
        <ol v-if="recognizedLines.length" aria-label="Recognized lines with matching image box colors" class="space-y-1 text-sm">
          <li v-for="(line, index) in recognizedLines" :key="`line-${index}`" class="flex items-start gap-2">
            <span class="mt-1 size-3 shrink-0 rounded-sm" :style="{ backgroundColor: lineColors[index % lineColors.length] }" aria-hidden="true" />
            <span :style="{ color: lineColors[index % lineColors.length] }"><span class="sr-only">Line {{ index + 1 }}: </span>{{ line.text }}</span>
          </li>
        </ol>
        <div class="flex flex-wrap gap-2">
          <button type="button" class="rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground disabled:opacity-50" :disabled="cameraBusy || !!imageURL" @click="startCamera">
            <Camera class="mr-1 inline size-4" /> {{ cameraBusy ? "Starting…" : "Start camera" }}
          </button>
          <button type="button" class="rounded-md border border-border px-3 py-2 text-sm disabled:opacity-50" :disabled="!cameraActive" @click="capture">Capture photo</button>
          <button v-if="cameraActive" type="button" class="rounded-md border border-border px-3 py-2 text-sm" @click="stopCamera">Stop camera</button>
          <button type="button" class="rounded-md border border-border px-3 py-2 text-sm disabled:opacity-50" :disabled="!image || scanning" @click="scan">{{ scanning ? "Scanning…" : image ? "Scan / retry" : "Scan photo" }}</button>
          <button v-if="imageURL" type="button" class="rounded-md border border-border px-3 py-2 text-sm" @click="retake">Retake</button>
        </div>
        <p v-if="error" role="alert" class="text-sm text-destructive">{{ error }}</p>
        <label class="block space-y-1 text-sm font-medium">
          Editable recognized text
          <textarea v-model="result" @input="resultRevision++" rows="5" class="w-full resize-y rounded-md border border-input bg-background px-3 py-2 text-sm font-normal text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" placeholder="Scan a photo to recognize text" />
        </label>
        <div class="flex justify-end">
          <button type="button" class="rounded-md border border-border px-3 py-2 text-sm disabled:opacity-50" :disabled="!result || copying" @click="copy"><Copy class="mr-1 inline size-4" /> {{ copying ? "Copying…" : "Copy text" }}</button>
        </div>
      </div>
      <button v-else type="button" class="w-full px-3 py-2 text-left text-sm text-muted-foreground hover:bg-accent" @click="minimized = false">Text capture minimized · click to restore</button>
    </section>
  </Teleport>
</template>
