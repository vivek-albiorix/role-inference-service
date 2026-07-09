<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from './api'
import type { UserSummaryOut, RoleOut } from './types'
import UserTable from './components/UserTable.vue'
import IngestForm from './components/IngestForm.vue'
import NewRoleForm from './components/NewRoleForm.vue'
import ToastContainer from './components/ToastContainer.vue'
import Modal from './components/Modal.vue'
import { useToast } from './composables/useToast'

const users = ref<UserSummaryOut[]>([])
const roles = ref<RoleOut[]>([])
const loading = ref(true)
const loadError = ref<string | null>(null)
const showIngest = ref(false)
const showNewRole = ref(false)
const reprocessing = ref(false)
const { showToast } = useToast()

async function loadUsers() {
  loading.value = true
  loadError.value = null
  try {
    users.value = await api.getUsers()
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

async function loadRoles() {
  if (roles.value.length === 0) {
    roles.value = await api.getRoles()
  }
}

async function onIngested() {
  showIngest.value = false
  await loadUsers()
}

async function onRoleCreated() {
  showNewRole.value = false
  roles.value = await api.getRoles()
}

// The job runs on the server in a background task (see
// app/services/reprocess_service.py) -- POST returns immediately, so the
// only way to know it's done is to poll the status endpoint. At this
// dataset size it typically finishes within a poll or two; the loop caps
// out rather than polling forever if something's gone wrong server-side.
async function pollReprocessStatus() {
  for (let attempt = 0; attempt < 30; attempt++) {
    const status = await api.getReprocessStatus()
    if (status.state === 'completed') {
      showToast(`Reprocessed ${status.processed_count}, skipped ${status.skipped_pinned_count} pinned`)
      await loadUsers()
      return
    }
    if (status.state === 'failed') {
      showToast(`Reprocess failed: ${status.error}`, true)
      return
    }
    await new Promise((resolve) => setTimeout(resolve, 400))
  }
  showToast('Reprocess is taking longer than expected -- check back shortly', true)
}

async function onReprocessAll() {
  reprocessing.value = true
  try {
    await api.startReprocess()
    showToast('Reprocessing started…')
    await pollReprocessStatus()
  } catch (err) {
    showToast(err instanceof Error ? err.message : String(err), true)
  } finally {
    reprocessing.value = false
  }
}

onMounted(() => {
  loadUsers()
  loadRoles()
})
</script>

<template>
  <header>
    <div>
      <h1>Role Inference Admin</h1>
      <p>Data model &amp; system behavior</p>
    </div>
    <div class="header-actions">
      <button @click="showIngest = true">Ingest new profile</button>
      <button @click="showNewRole = true">New role</button>
      <button :disabled="reprocessing" @click="onReprocessAll">
        {{ reprocessing ? 'Reprocessing…' : 'Reprocess all' }}
      </button>
      <a href="/docs" target="_blank" rel="noopener"><button type="button">API docs</button></a>
    </div>
  </header>

  <Modal v-if="showIngest" title="Ingest a profile" @close="showIngest = false">
    <IngestForm @ingested="onIngested" />
  </Modal>

  <Modal v-if="showNewRole" title="Create a new role" @close="showNewRole = false">
    <NewRoleForm @created="onRoleCreated" />
  </Modal>

  <main>
    <table v-if="loading || loadError || users.length === 0">
      <thead>
        <tr>
          <th>User</th>
          <th>Title / Department</th>
          <th>Effective role</th>
          <th>Confidence</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td colspan="5" class="empty-state">
            <span v-if="loading">Loading&hellip;</span>
            <span v-else-if="loadError">Failed to load users: {{ loadError }}</span>
            <span v-else>No users yet. Ingest a profile to get started.</span>
          </td>
        </tr>
      </tbody>
    </table>
    <UserTable v-else :users="users" :roles="roles" @changed="loadUsers" />
  </main>

  <ToastContainer />
</template>
