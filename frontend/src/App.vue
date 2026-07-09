<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from './api'
import type { UserSummaryOut, RoleOut } from './types'
import UserTable from './components/UserTable.vue'
import IngestForm from './components/IngestForm.vue'
import ToastContainer from './components/ToastContainer.vue'
import Modal from './components/Modal.vue'
import { useToast } from './composables/useToast'

const users = ref<UserSummaryOut[]>([])
const roles = ref<RoleOut[]>([])
const loading = ref(true)
const loadError = ref<string | null>(null)
const showIngest = ref(false)
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

async function onReprocessAll() {
  try {
    const result = await api.reprocessAll()
    showToast(`Reprocessed ${result.processed_count}, skipped ${result.skipped_pinned_count} pinned`)
    await loadUsers()
  } catch (err) {
    showToast(err instanceof Error ? err.message : String(err), true)
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
      <p>Data model &amp; system behavior demo &mdash; not a polished UI by design.</p>
    </div>
    <div class="header-actions">
      <button @click="showIngest = true">Ingest new profile</button>
      <button @click="onReprocessAll">Reprocess all</button>
      <a href="/docs" target="_blank" rel="noopener"><button type="button">API docs</button></a>
    </div>
  </header>

  <Modal v-if="showIngest" title="Ingest an SSO profile" @close="showIngest = false">
    <IngestForm @ingested="onIngested" />
  </Modal>

  <main>
    <table v-if="loading || loadError || users.length === 0">
      <thead>
        <tr>
          <th>User</th>
          <th>Title / Department</th>
          <th>Effective role</th>
          <th>Confidence</th>
          <th></th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td colspan="6" class="empty-state">
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
