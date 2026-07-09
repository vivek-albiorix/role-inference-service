<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'

withDefaults(defineProps<{ title?: string; size?: 'md' | 'lg' }>(), {
  size: 'md',
})
const emit = defineEmits<{ close: [] }>()

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  document.body.style.overflow = 'hidden'
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  document.body.style.overflow = ''
})
</script>

<template>
  <Teleport to="body">
    <div class="modal-backdrop" @click.self="emit('close')">
      <div class="modal-dialog" :class="{ 'modal-lg': size === 'lg' }" role="dialog" aria-modal="true">
        <div class="modal-header">
          <h3>{{ title }}</h3>
          <button class="modal-close" type="button" aria-label="Close" @click="emit('close')">&times;</button>
        </div>
        <div class="modal-body">
          <slot />
        </div>
      </div>
    </div>
  </Teleport>
</template>
