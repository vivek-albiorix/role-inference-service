<script setup lang="ts">
import { useToast } from '../composables/useToast'

const { toast } = useToast()
</script>

<template>
  <div class="toast" :class="{ visible: toast !== null, error: toast?.isError }">
    {{ toast?.message ?? '' }}
  </div>
</template>
