import { ref } from 'vue'

interface ToastState {
  message: string
  isError: boolean
}

// Module-level (not per-component) state -- one toast, shared across the
// whole app, mirroring the single <div id="toast"> the vanilla page used.
const toast = ref<ToastState | null>(null)
let timer: ReturnType<typeof setTimeout> | undefined

function showToast(message: string, isError = false) {
  toast.value = { message, isError }
  clearTimeout(timer)
  timer = setTimeout(() => {
    toast.value = null
  }, 3000)
}

export function useToast() {
  return { toast, showToast }
}
