<script setup lang="ts">
import { ref } from 'vue'
import type { UserSummaryOut, RoleOut, InferenceResultOut } from '../types'
import { api } from '../api'
import { useToast } from '../composables/useToast'
import InferenceDetail from './InferenceDetail.vue'
import OverrideForm from './OverrideForm.vue'
import Modal from './Modal.vue'

const props = defineProps<{ user: UserSummaryOut; roles: RoleOut[] }>()
const emit = defineEmits<{ changed: [] }>()
const { showToast } = useToast()

type PanelMode = 'none' | 'detail' | 'override'
const panel = ref<PanelMode>('none')
const inference = ref<InferenceResultOut | null>(null)
const inferenceError = ref<string | null>(null)
const loadingInference = ref(false)

async function toggleDetails() {
  if (panel.value === 'detail') {
    panel.value = 'none'
    return
  }
  panel.value = 'detail'
  loadingInference.value = true
  inferenceError.value = null
  try {
    inference.value = await api.getInference(props.user.user_id)
  } catch (err) {
    inferenceError.value = err instanceof Error ? err.message : String(err)
  } finally {
    loadingInference.value = false
  }
}

function openOverrideForm() {
  panel.value = 'override'
}

function onOverrideSaved() {
  panel.value = 'none'
  showToast(`Override set for ${props.user.user_id}`)
  emit('changed')
}

async function onReset() {
  try {
    await api.resetOverride(props.user.user_id)
    showToast(`Override reset for ${props.user.user_id}`)
    emit('changed')
  } catch (err) {
    showToast(err instanceof Error ? err.message : String(err), true)
  }
}

async function onReinfer() {
  try {
    await api.reinfer(props.user.user_id)
    showToast(`Re-inferred ${props.user.user_id}`)
    emit('changed')
  } catch (err) {
    showToast(err instanceof Error ? err.message : String(err), true)
  }
}
</script>

<template>
  <tr class="user-row">
    <td>
      <strong>{{ user.user_id }}</strong><br />
      <span class="muted">{{ user.display_name || '' }}</span>
    </td>
    <td>
      {{ user.title || '—' }}<br />
      <span class="muted">{{ user.department || '—' }}</span>
    </td>
    <td>
      <span v-if="user.effective_role.role_name">{{ user.effective_role.role_name }}</span>
      <span v-else class="muted">unassigned</span>
      <br />
      <span class="badge" :class="`source-${user.effective_role.source}`">{{ user.effective_role.source }}</span>
      <span v-if="user.override_pinned" class="badge pinned">pinned</span>
    </td>
    <td>
      {{ user.effective_role.confidence != null ? user.effective_role.confidence.toFixed(2) : '—' }}
      <span v-if="user.effective_role.band" class="badge" :class="`band-${user.effective_role.band}`">
        {{ user.effective_role.band.replace('_', ' ') }}
      </span>
    </td>
    <td><button @click="toggleDetails">Details</button></td>
    <td class="actions-cell">
      <button @click="openOverrideForm">Override</button>
      <button :disabled="!user.override_active" @click="onReset">Reset</button>
      <button @click="onReinfer">Re-infer</button>
    </td>
  </tr>

  <Modal v-if="panel === 'detail'" :title="`Inference details — ${user.user_id}`" size="lg" @close="panel = 'none'">
    <p v-if="loadingInference">Loading&hellip;</p>
    <p v-else-if="inferenceError" class="muted">No inference yet ({{ inferenceError }}).</p>
    <div v-else-if="inference" class="detail-content">
      <InferenceDetail :inference="inference" />
    </div>
  </Modal>

  <Modal v-if="panel === 'override'" :title="`Set override — ${user.user_id}`" @close="panel = 'none'">
    <OverrideForm :roles="roles" :user-id="user.user_id" @saved="onOverrideSaved" @cancel="panel = 'none'" />
  </Modal>
</template>
