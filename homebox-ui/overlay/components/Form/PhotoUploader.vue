<template>
  <div class="w-full">
    <div class="flex w-full flex-col gap-1.5">
      <Label for="photo-uploader" class="flex w-full px-1">{{ label }}</Label>
      <div class="flex flex-wrap gap-2">
        <Button type="button" variant="outline" @click="openFilePicker">{{ buttonLabel }}</Button>
        <input
          id="photo-uploader"
          ref="fileInput"
          class="sr-only"
          type="file"
          accept="image/png,image/jpeg,image/gif,image/avif,image/webp,android/force-camera-workaround"
          multiple
          @change="onFilesSelected"
        />
        <Button type="button" variant="outline" @click="startCamera">Take photo</Button>
      </div>
      <p v-if="uploadError" role="alert" class="text-sm text-destructive">{{ uploadError }}</p>

      <div v-if="cameraOpen" class="mt-2 space-y-2" role="group" aria-label="Camera capture">
        <p v-if="cameraError" role="alert" class="text-sm text-destructive">{{ cameraError }}</p>
        <template v-if="capturedPhoto">
          <img :src="capturedUrl" alt="Captured photo preview" class="max-h-64 rounded object-contain" />
          <div class="flex flex-wrap gap-2">
            <Button type="button" variant="outline" @click="retake">Retake</Button>
            <Button type="button" :disabled="attaching" @click="usePicture">Use photo</Button>
            <Button type="button" variant="outline" @click="closeCamera">Cancel</Button>
          </div>
        </template>
        <template v-else>
          <p v-if="!stream && !cameraError" role="status" class="text-sm text-muted-foreground">Opening camera…</p>
          <video ref="video" autoplay muted playsinline class="max-h-64 w-full rounded bg-black object-contain" />
          <div class="flex flex-wrap gap-2">
            <Button type="button" :disabled="!stream || capturing" @click="capture">{{ capturing ? "Capturing…" : "Capture" }}</Button>
            <Button type="button" variant="outline" @click="closeCamera">Cancel</Button>
          </div>
        </template>
      </div>
      <canvas ref="canvas" class="hidden" />
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed, onBeforeUnmount, ref, watch } from "vue";
  import { useI18n } from "vue-i18n";
  import { Label } from "~/components/ui/label";
  import { Button } from "~/components/ui/button";
  import { filesToPhotoPreviews, type PhotoPreview } from "./photo-uploader";

  const props = withDefaults(
    defineProps<{ label?: string; buttonLabel?: string; existingCount?: number }>(),
    { label: undefined, buttonLabel: undefined, existingCount: 0 }
  );
  const emit = defineEmits<{ (e: "selected", photos: PhotoPreview[]): void }>();
  const { t } = useI18n();
  const label = computed(() => props.label || t("components.entity.create_modal.item_photo"));
  const buttonLabel = computed(() => props.buttonLabel || t("components.entity.create_modal.upload_photos"));
  const fileInput = ref<HTMLInputElement | null>(null);
  const video = ref<HTMLVideoElement | null>(null);
  const canvas = ref<HTMLCanvasElement | null>(null);
  const cameraOpen = ref(false);
  const cameraError = ref("");
  const stream = ref<MediaStream | null>(null);
  const capturedPhoto = ref<File | null>(null);
  const capturedUrl = ref("");
  const capturing = ref(false);
  const attaching = ref(false);
  const uploadError = ref("");
  let requestId = 0;

  watch([video, stream], ([videoElement, mediaStream]) => {
    if (videoElement && mediaStream) videoElement.srcObject = mediaStream;
  });

  function openFilePicker() {
    fileInput.value?.click();
  }

  async function onFilesSelected(event: Event) {
    const input = event.target as HTMLInputElement;
    if (!input.files?.length) return;
    uploadError.value = "";
    try {
      emit("selected", await filesToPhotoPreviews(input.files, props.existingCount));
    } catch (error) {
      uploadError.value = error instanceof Error ? error.message : "Could not read the selected photos.";
    } finally {
      input.value = "";
    }
  }

  function stopStream(mediaStream: MediaStream | null) {
    mediaStream?.getTracks().forEach(track => track.stop());
  }

  function clearCaptured() {
    if (capturedUrl.value) URL.revokeObjectURL(capturedUrl.value);
    capturedUrl.value = "";
    capturedPhoto.value = null;
  }

  function closeCamera() {
    requestId++;
    capturing.value = false;
    cameraOpen.value = false;
    cameraError.value = "";
    stopStream(stream.value);
    stream.value = null;
    if (video.value) video.value.srcObject = null;
    clearCaptured();
  }

  async function startCamera() {
    closeCamera();
    cameraOpen.value = true;
    cameraError.value = "";
    const thisRequest = ++requestId;
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error("Camera access is unavailable in this browser.");
      const nextStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false });
      if (thisRequest !== requestId || !cameraOpen.value) {
        stopStream(nextStream);
        return;
      }
      stream.value = nextStream;
    } catch (error) {
      if (thisRequest === requestId && cameraOpen.value) {
        cameraError.value = error instanceof Error ? error.message : "Could not open the camera.";
      }
    }
  }

  function capture() {
    if (capturing.value) return;
    const videoElement = video.value;
    const output = canvas.value;
    if (!videoElement || !output || !stream.value || !videoElement.videoWidth || !videoElement.videoHeight) {
      cameraError.value = "The camera is not ready yet.";
      return;
    }
    capturing.value = true;
    const width = videoElement.videoWidth;
    const height = videoElement.videoHeight;
    output.width = width;
    output.height = height;
    const context = output.getContext("2d");
    if (!context) {
      capturing.value = false;
      cameraError.value = "Could not capture an image from the camera.";
      return;
    }
    const thisRequest = requestId;
    try {
      context.drawImage(videoElement, 0, 0, width, height);
      output.toBlob(blob => {
        if (thisRequest !== requestId) return;
        capturing.value = false;
        if (!blob || !cameraOpen.value) {
          cameraError.value = "Could not capture an image from the camera.";
          return;
        }
        capturedPhoto.value = new File([blob], `camera-${Date.now()}.jpg`, { type: "image/jpeg" });
        capturedUrl.value = URL.createObjectURL(capturedPhoto.value);
        stopStream(stream.value);
        stream.value = null;
        if (video.value) video.value.srcObject = null;
      }, "image/jpeg", 0.92);
    } catch (error) {
      capturing.value = false;
      cameraError.value = error instanceof Error ? error.message : "Could not capture an image from the camera.";
    }
  }

  function retake() {
    clearCaptured();
    void startCamera();
  }

  async function usePicture() {
    const photo = capturedPhoto.value;
    if (!photo || attaching.value) return;
    attaching.value = true;
    const thisRequest = requestId;
    try {
      const photos = await filesToPhotoPreviews([photo], props.existingCount);
      if (thisRequest !== requestId || !cameraOpen.value || capturedPhoto.value !== photo) return;
      emit("selected", photos);
      closeCamera();
    } catch (error) {
      if (thisRequest === requestId && cameraOpen.value) {
        cameraError.value = error instanceof Error ? error.message : "Could not attach the captured photo.";
      }
    } finally {
      attaching.value = false;
    }
  }

  onBeforeUnmount(() => {
    closeCamera();
  });
</script>
