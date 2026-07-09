<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const open = ref(false)
const menuRef = ref<HTMLElement | null>(null)

function toggle() {
  open.value = !open.value
}
function close() {
  open.value = false
}

function onClickOutside(e: MouseEvent) {
  if (menuRef.value && !menuRef.value.contains(e.target as Node)) close()
}
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') close()
}

onMounted(() => {
  window.addEventListener('click', onClickOutside)
  window.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  window.removeEventListener('click', onClickOutside)
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div ref="menuRef" class="actions-menu">
    <button type="button" class="meatball-btn" aria-label="Actions" aria-haspopup="true" :aria-expanded="open" @click.stop="toggle">
      &#8942;
    </button>
    <!-- Clicking any menu item bubbles here and closes the menu, without
         needing each caller to remember to close it themselves. -->
    <div v-if="open" class="actions-dropdown" @click="close">
      <slot />
    </div>
  </div>
</template>
