<script setup lang="ts">
  import { Camera, Copy, Minus, ScanText, X } from "lucide-vue-next";
  import { recognizeTextFromImage } from "~/lib/local-ocr";

  const props = defineProps<{ launcherTarget: string }>();
  const open = ref(false), minimized = ref(false), cameraBusy = ref(false), cameraActive = ref(false), scanning = ref(false), copying = ref(false);
  const video = ref<HTMLVideoElement | null>(null), result = ref(""), error = ref(""), imageURL = ref("");
  const position = ref({ left: 0, top: 64 });
  let stream: MediaStream | null = null, image: Blob | null = null, drag: { x: number; y: number; left: number; top: number } | null = null;
  let cameraGeneration = 0, scanGeneration = 0, disposed = false;

  function stopCamera() {
    cameraGeneration++;
    stream?.getTracks().forEach(track => track.stop());
    stream = null;
    cameraActive.value = false;
    if (video.value) video.value.srcObject = null;
    cameraBusy.value = false;
  }
  function show() {
    open.value = true;
    minimized.value = false;
    position.value.left = Math.max(0, window.innerWidth - 416);
    position.value.top = 64;
  }
  function close() { stopCamera(); open.value = false; minimized.value = false; }
  function minimize() { stopCamera(); minimized.value = true; }
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
      requestedStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
      if (disposed || generation !== cameraGeneration || !open.value || minimized.value) {
        requestedStream.getTracks().forEach(track => track.stop());
        return;
      }
      stream = requestedStream;
      cameraActive.value = true;
      if (video.value) {
        video.value.srcObject = stream;
        await video.value.play();
      }
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
    const canvas = document.createElement("canvas");
    canvas.width = source.videoWidth;
    canvas.height = source.videoHeight;
    canvas.getContext("2d")?.drawImage(source, 0, 0);
    const photo = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, "image/jpeg", 0.9));
    if (disposed) return;
    if (!photo) { error.value = "Could not capture a photo. Try again."; return; }
    scanGeneration++;
    scanning.value = false;
    if (imageURL.value) URL.revokeObjectURL(imageURL.value);
    image = photo;
    imageURL.value = URL.createObjectURL(photo);
    error.value = "";
    stopCamera();
  }
  async function scan() {
    if (!image) return;
    const generation = ++scanGeneration, scannedImage = image;
    scanning.value = true;
    error.value = "";
    try {
      const text = await recognizeTextFromImage(scannedImage);
      if (generation !== scanGeneration || image !== scannedImage) return;
      if (!text?.trim()) error.value = "No text was recognized. Retake the photo or adjust it and scan again.";
      else result.value = text;
    } catch (cause) {
      if (generation === scanGeneration && image === scannedImage) {
        error.value = `OCR could not read this photo: ${(cause as Error)?.message || "unknown error"}. You can retry the scan.`;
      }
    } finally { if (generation === scanGeneration) scanning.value = false; }
  }
  async function copy() {
    copying.value = true;
    error.value = "";
    try { await navigator.clipboard.writeText(result.value); }
    catch { error.value = "Could not copy text. Select it in the text box and copy it manually."; }
    finally { copying.value = false; }
  }
  function retake() {
    scanGeneration++;
    scanning.value = false;
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
    position.value = {
      left: Math.min(Math.max(0, drag.left + event.clientX - drag.x), Math.max(0, window.innerWidth - rect.width)),
      top: Math.min(Math.max(0, drag.top + event.clientY - drag.y), Math.max(0, window.innerHeight - Math.min(rect.height, 56))),
    };
  }
  function endDrag() { drag = null; }
  onBeforeUnmount(() => {
    disposed = true;
    stopCamera();
    if (imageURL.value) URL.revokeObjectURL(imageURL.value);
  });
</script>

<template>
  <Teleport defer :to="props.launcherTarget">
    <button
      v-if="!open"
      type="button"
      class="inline-flex h-9 shrink-0 items-center gap-2 rounded-md border border-border bg-card px-3 text-sm font-medium text-foreground shadow-sm hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      aria-label="Open ORC camera and text tool"
      @click="show"
    >
      <ScanText class="size-4" /> ORC
    </button>
  </Teleport>
  <Teleport to="body">
    <section
      v-if="open"
      class="fixed z-50 flex max-h-[calc(100vh-1rem)] w-[min(24rem,calc(100vw-1rem))] flex-col overflow-hidden rounded-lg border border-border bg-card text-card-foreground shadow-xl"
      :style="{ left: `${position.left}px`, top: `${position.top}px`, maxHeight: `calc(100vh - ${position.top}px - 1rem)` }"
      aria-label="ORC camera and text tool"
    >
      <header
        class="flex shrink-0 cursor-move touch-none items-center justify-between border-b border-border bg-muted/60 px-3 py-2"
        @pointerdown="startDrag"
        @pointermove="moveDrag"
        @pointerup="endDrag"
        @pointercancel="endDrag"
      >
        <div class="flex items-center gap-2 text-sm font-semibold"><ScanText class="size-4 text-primary" /> ORC <span class="text-xs font-normal text-muted-foreground">· C-Crate</span></div>
        <div class="flex items-center gap-1">
          <button type="button" class="rounded p-1 hover:bg-accent" aria-label="Minimize ORC" @click="minimize"><Minus class="size-4" /></button>
          <button type="button" class="rounded p-1 hover:bg-accent" aria-label="Close ORC" @click="close"><X class="size-4" /></button>
        </div>
      </header>
      <div v-if="!minimized" class="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
        <div class="relative flex aspect-[4/3] items-center justify-center overflow-hidden rounded-md bg-muted">
          <img v-if="imageURL" :src="imageURL" alt="Captured image for OCR" class="h-full w-full object-contain" />
          <video v-else ref="video" autoplay muted playsinline class="h-full w-full object-cover" />
          <span v-if="!imageURL && !cameraActive" class="absolute text-sm text-muted-foreground">Camera is off</span>
        </div>
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
          Recognized text
          <textarea v-model="result" rows="5" class="w-full resize-y rounded-md border border-input bg-background px-3 py-2 text-sm font-normal text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" placeholder="Scan a photo to recognize text" />
        </label>
        <div class="flex justify-end">
          <button type="button" class="rounded-md border border-border px-3 py-2 text-sm disabled:opacity-50" :disabled="!result || copying" @click="copy"><Copy class="mr-1 inline size-4" /> {{ copying ? "Copying…" : "Copy text" }}</button>
        </div>
      </div>
      <button v-else type="button" class="w-full px-3 py-2 text-left text-sm text-muted-foreground hover:bg-accent" @click="minimized = false">ORC minimized · click to restore</button>
    </section>
  </Teleport>
</template>
