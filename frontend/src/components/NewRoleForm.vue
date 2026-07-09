<script setup lang="ts">
import { reactive } from 'vue'
import { api } from '../api'
import { useToast } from '../composables/useToast'

const emit = defineEmits<{ created: [roleId: string] }>()
const { showToast } = useToast()

const form = reactive({
  role_name: '',
  department: '',
  job_family: '',
  seniority: '',
  skills: '',
  keywords: '',
})

function splitList(value: string): string[] {
  return value
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
}

async function onSubmit() {
  if (!form.role_name.trim() || !form.department.trim() || !form.job_family.trim() || !form.seniority.trim()) {
    showToast('role_name, department, job_family, and seniority are required', true)
    return
  }
  try {
    // role_id is server-generated (see services/catalog.py::create_role) --
    // it's an internal catalog key with no external meaning, unlike a
    // user's user_id, so there's nothing for the admin to type here.
    const created = await api.createRole({
      role_name: form.role_name.trim(),
      department: form.department.trim(),
      job_family: form.job_family.trim(),
      seniority: form.seniority.trim(),
      skills: splitList(form.skills),
      keywords: splitList(form.keywords),
    })
    showToast(`Role ${created.role_id} (${created.role_name}) created`)
    emit('created', created.role_id)
  } catch (err) {
    showToast(err instanceof Error ? err.message : String(err), true)
  }
}
</script>

<template>
  <form @submit.prevent="onSubmit">
    <div class="field-row">
      <div class="field">
        <label for="role-name">role_name *</label>
        <input id="role-name" v-model="form.role_name" type="text" required placeholder="Staff Engineer" />
      </div>
      <div class="field">
        <label for="role-department">department *</label>
        <input id="role-department" v-model="form.department" type="text" required placeholder="Engineering" />
      </div>
    </div>
    <div class="field-row">
      <div class="field">
        <label for="role-job-family">job_family *</label>
        <input id="role-job-family" v-model="form.job_family" type="text" required placeholder="Engineering" />
      </div>
      <div class="field">
        <label for="role-seniority">seniority *</label>
        <input id="role-seniority" v-model="form.seniority" type="text" required placeholder="Staff" />
      </div>
    </div>
    <div class="field-row">
      <div class="field">
        <label for="role-skills">skills (comma-separated)</label>
        <input id="role-skills" v-model="form.skills" type="text" placeholder="Architecture, Mentorship" />
      </div>
      <div class="field">
        <label for="role-keywords">keywords (comma-separated)</label>
        <input id="role-keywords" v-model="form.keywords" type="text" placeholder="staff, principal, technical leadership" />
      </div>
    </div>
    <button type="submit" class="primary">Create role</button>
  </form>
</template>
