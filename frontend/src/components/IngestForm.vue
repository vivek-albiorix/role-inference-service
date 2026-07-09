<script setup lang="ts">
import { reactive } from 'vue'
import { api } from '../api'
import { useToast } from '../composables/useToast'

const emit = defineEmits<{ ingested: [userId: string] }>()
const { showToast } = useToast()

const form = reactive({
  user_id: '',
  display_name: '',
  title: '',
  department: '',
  manager_title: '',
  location: '',
  notes: '',
  skills: '',
  groups: '',
})

function splitList(value: string): string[] {
  return value
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
}

async function onSubmit() {
  const userId = form.user_id.trim()
  if (!userId) {
    showToast('user_id is required', true)
    return
  }
  try {
    await api.ingestProfile({
      user_id: userId,
      display_name: form.display_name.trim() || null,
      title: form.title.trim() || null,
      department: form.department.trim() || null,
      manager_title: form.manager_title.trim() || null,
      location: form.location.trim() || null,
      notes: form.notes.trim() || null,
      skills: splitList(form.skills),
      groups: splitList(form.groups),
    })
    showToast(`Ingested ${userId}`)
    Object.assign(form, {
      user_id: '',
      display_name: '',
      title: '',
      department: '',
      manager_title: '',
      location: '',
      notes: '',
      skills: '',
      groups: '',
    })
    emit('ingested', userId)
  } catch (err) {
    showToast(err instanceof Error ? err.message : String(err), true)
  }
}
</script>

<template>
  <form @submit.prevent="onSubmit">
    <div class="field-row">
      <div class="field">
        <label for="ingest-user-id">user_id *</label>
        <input id="ingest-user-id" v-model="form.user_id" type="text" required placeholder="usr_009" />
      </div>
      <div class="field">
        <label for="ingest-display-name">display_name</label>
        <input id="ingest-display-name" v-model="form.display_name" type="text" placeholder="Jane Doe" />
      </div>
    </div>
    <div class="field-row">
      <div class="field">
        <label for="ingest-title">title</label>
        <input id="ingest-title" v-model="form.title" type="text" placeholder="Sr BI Analyst" />
      </div>
      <div class="field">
        <label for="ingest-department">department</label>
        <input id="ingest-department" v-model="form.department" type="text" placeholder="Data & Insights" />
      </div>
    </div>
    <div class="field-row">
      <div class="field">
        <label for="ingest-manager-title">manager_title</label>
        <input
          id="ingest-manager-title"
          v-model="form.manager_title"
          type="text"
          placeholder="Director of Analytics"
        />
      </div>
      <div class="field">
        <label for="ingest-location">location</label>
        <input id="ingest-location" v-model="form.location" type="text" placeholder="New York" />
      </div>
    </div>
    <div class="field-row">
      <div class="field">
        <label for="ingest-skills">skills (comma-separated)</label>
        <input id="ingest-skills" v-model="form.skills" type="text" placeholder="SQL, Python, Looker" />
      </div>
      <div class="field">
        <label for="ingest-groups">groups (comma-separated)</label>
        <input id="ingest-groups" v-model="form.groups" type="text" placeholder="tableau-users, data-team" />
      </div>
    </div>
    <div class="field">
      <label for="ingest-notes">notes</label>
      <input id="ingest-notes" v-model="form.notes" type="text" placeholder="Optional free text" />
    </div>
    <button type="submit" class="primary">Ingest &amp; infer</button>
  </form>
</template>
