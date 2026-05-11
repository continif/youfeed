import { onBeforeUnmount, onMounted, type Ref } from "vue";

export function useClickOutside(
  target: Ref<HTMLElement | null>,
  handler: (event: MouseEvent | TouchEvent | KeyboardEvent) => void,
) {
  function onPointer(e: MouseEvent | TouchEvent) {
    const el = target.value;
    if (!el) return;
    const path = (e.composedPath?.() ?? []) as EventTarget[];
    if (path.includes(el)) return;
    handler(e);
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.key === "Escape") handler(e);
  }

  onMounted(() => {
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("touchstart", onPointer, { passive: true });
    document.addEventListener("keydown", onKeydown);
  });

  onBeforeUnmount(() => {
    document.removeEventListener("mousedown", onPointer);
    document.removeEventListener("touchstart", onPointer);
    document.removeEventListener("keydown", onKeydown);
  });
}
