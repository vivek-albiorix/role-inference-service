<script setup lang="ts">
import { reactive } from 'vue'
import type { RoleOut } from '../types'
import { api } from '../api'
import { useToast } from '../composables/useToast'

const props = defineProps<{ userId: string; roles: RoleOut[] }>()
const emit = defineEmits<{ saved: []; cancel: [] }>()
const { showToast } = useToast()

const form = reactive({
  role_id: props.roles[0]?.role_id ?? '',
  reason: '',
  pinned: true,
})

async function onSubmit() {
  try {
    await api.setOverride(props.userId, {
      role_id: form.role_id,
      reason: form.reason || null,
      pinned: form.pinned,
      created_by: 'admin',
    })
    emit('saved')
  } catch (err) {
    showToast(err instanceof Error ? err.message : String(err), true)
  }
}
</script>

<template>
  <form class="override-form" @submit.prevent="onSubmit">
    <h4>Set override</h4>
    <div class="field-row">
      <div class="field">
        <label>Role</label>
        <select v-model="form.role_id">
          <option v-for="role in roles" :key="role.role_id" :value="role.role_id">{{ role.role_name }}</option>
        </select>
      </div>
      <div class="field">
        <label>Reason</label>
        <input v-model="form.reason" type="text" placeholder="Why is this being overridden?" />
      </div>
    </div>
    <div class="field">
      <label><input v-model="form.pinned" type="checkbox" /> Pinned (survives bulk reprocess)</label>
    </div>
    <button type="submit" class="primary">Save override</button>
    <button type="button" @click="emit('cancel')">Cancel</button>
  </form>
</template>
