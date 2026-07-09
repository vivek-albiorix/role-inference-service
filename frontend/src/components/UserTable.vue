<script setup lang="ts">
import type { UserSummaryOut, RoleOut } from '../types'
import UserRow from './UserRow.vue'

defineProps<{ users: UserSummaryOut[]; roles: RoleOut[] }>()
defineEmits<{ changed: [] }>()
</script>

<template>
  <table>
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
      <UserRow v-for="user in users" :key="user.user_id" :user="user" :roles="roles" @changed="$emit('changed')" />
    </tbody>
  </table>
</template>
