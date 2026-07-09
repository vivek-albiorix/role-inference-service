<script setup lang="ts">
import { computed } from 'vue'
import type { InferenceResultOut } from '../types'

const props = defineProps<{ inference: InferenceResultOut }>()

const stageEntries = computed(() =>
  Object.entries(props.inference.stage_timings_ms).sort(([a], [b]) => a.localeCompare(b)),
)
const totalMs = computed(() => stageEntries.value.reduce((sum, [, ms]) => sum + ms, 0))
</script>

<template>
  <div class="human-readable">{{ inference.explanation }}</div>
  <div>
    <h4>Signals used</h4>
    <ul>
      <li v-for="(s, i) in inference.signals" :key="i">{{ s }}</li>
      <li v-if="inference.signals.length === 0" class="muted">none</li>
    </ul>
  </div>
  <div>
    <h4>Alternatives considered</h4>
    <ul>
      <li v-for="alt in inference.alternative_roles" :key="alt.role_id">
        <strong>{{ alt.role }}</strong> ({{ alt.confidence.toFixed(2) }}) &mdash; {{ alt.why_lost || '' }}
      </li>
      <li v-if="inference.alternative_roles.length === 0" class="muted">none</li>
    </ul>
  </div>
  <div>
    <h4>Negative evidence</h4>
    <ul>
      <li v-for="(s, i) in inference.negative_evidence" :key="i">{{ s }}</li>
      <li v-if="inference.negative_evidence.length === 0" class="muted">none</li>
    </ul>
  </div>
  <div>
    <h4>Missing information</h4>
    <ul>
      <li v-for="(s, i) in inference.missing_information" :key="i">{{ s }}</li>
      <li v-if="inference.missing_information.length === 0" class="muted">none</li>
    </ul>
  </div>
  <div>
    <h4>Performance (stage timings)</h4>
    <ul>
      <li v-for="[stage, ms] in stageEntries" :key="stage">{{ stage }}: {{ ms.toFixed(2) }}ms</li>
    </ul>
    <div class="muted">total: {{ totalMs.toFixed(2) }}ms</div>
  </div>
  <div class="muted run-meta">
    run #{{ inference.run_id }} &middot; engine {{ inference.engine_version }} &middot;
    catalog v{{ inference.catalog_version }} &middot;
    llm_used={{ inference.llm_used }} &middot; llm_degraded={{ inference.llm_degraded }} &middot;
    llm_cached={{ inference.llm_cached }}
  </div>
</template>
